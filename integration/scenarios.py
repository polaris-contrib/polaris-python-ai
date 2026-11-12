# Tencent is pleased to support the open source community by making polaris-python-ai available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# Licensed under the BSD 3-Clause License (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# https://opensource.org/licenses/BSD-3-Clause
#
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.

"""Run AgentScope integration cases against local or real Polaris services."""

# Direct script execution adds the checkout before importing local modules.
# ruff: noqa: E402

import argparse
import asyncio
import contextlib
import json
import os
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "src"), str(REPO)]

import httpx
import psutil
from a2a.client import ClientConfig, ClientFactory
from a2a.types import AgentCard
from agentscope.agent import A2AAgent
from agentscope.message import UserMsg
from agentscope.tool import Toolkit
from polaris.api.consumer import ConsumerAPI
from polaris.api.skill import SkillAPI
from polaris.pkg.model.error import SDKError
from polaris.pkg.model.service import GetAllInstancesRequest
from polaris.pkg.model.skill import SkillListRequest

from examples._support import get_local_host
from examples.agentscope import _common
from examples.agentscope.a2a.console_consumer import main as console_consumer_demo
from examples.agentscope.a2a.consumer import main as consumer_demo
from examples.agentscope.a2a.provider import main as provider_demo
from examples.agentscope.a2a.state_resume import main as state_resume_demo
from examples.agentscope.a2a.streaming_provider import main as streaming_provider_demo
from examples.agentscope.agent_service import main as agent_service_demo
from examples.agentscope.mcp import main as mcp_demo
from examples.agentscope.mcp.agent import main as mcp_agent_demo
from examples.agentscope.runtime import main as runtime_demo
from examples.agentscope.runtime.multi_agent import main as runtime_multi_demo
from examples.agentscope.skill.console_agent import main as skill_console_demo
from examples.agentscope.skill.mounted import main as mounted_demo
from examples.agentscope.skill.published import main as published_demo
from integration.stub import RegistryStub, offline_registry
from integration.support import e2e_namespace, record_external_process, verification_directory
from polaris_ai.a2a._card import decode_card
from polaris_ai.agentscope import PolarisSkillLoader

RETAIN_ENV = "POLARIS_E2E_RETAIN"


def required_environment(demo):
    address = (
        os.getenv("POLARIS_SERVER_ADDRESS") or os.getenv("POLARIS_SERVER_ADDRESSES", "")
    ).strip()
    if not address:
        raise ValueError("POLARIS_SERVER_ADDRESS is required for real-service verification")
    address = address.split(",", 1)[0].strip()
    token = os.getenv("POLARIS_E2E_SERVICE_TOKEN") or os.getenv("POLARIS_SERVICE_TOKEN", "")
    if demo == "mounted" and not os.getenv("POLARIS_AGENT_SERVICE"):
        raise ValueError("POLARIS_AGENT_SERVICE must identify a service with mounted Skills")
    if demo == "mcp" and not os.getenv("POLARIS_MCP_SERVICE"):
        raise ValueError("POLARIS_MCP_SERVICE must identify an MCP Server")
    return address, token


def scenario_environment(address):
    from polaris.pkg.model.util import get_ip_from_int_with_port

    host, _ = get_ip_from_int_with_port(address)
    host = f"[{host}]" if ":" in host else host
    return {
        "POLARIS_E2E": "1",
        "POLARIS_DEMO_OFFLINE": "0",
        "POLARIS_SERVER_ADDRESS": address,
        "POLARIS_SERVER_ADDRESSES": address,
        "POLARIS_SERVER": address,
        "POLARIS_EVENT_REPORTER_ENABLE": "1",
        "POLARIS_EVENT_REPORTER_ADDRESS": f"{host}:9091",
        "POLARIS_EVENT_REPORTER_PUSH_INTERVAL": "250",
        "POLARIS_EVENT_REPORTER_MAX_RETRIES": "3",
        "POLARIS_EVENT_REPORTER_RETRY_INTERVAL": "100",
    }


def service_name(kind="a2a"):
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    return f"agentscope-{kind}-{timestamp}"


def sdk_arguments(address, namespace):
    arguments = ["--address", address, "--namespace", namespace, "--timeout", "5000"]
    if os.getenv("POLARIS_DEMO_OFFLINE") != "1" and (configured := os.getenv("POLARIS_E2E_CONFIG")):
        arguments += ["--config", configured]
    return arguments


async def real_skill_reference(address, namespace, *, entry, service_name=""):
    """Resolve the published Skill selected for a real E2E scenario."""
    configured = os.getenv("POLARIS_SKILL_NAME", "").strip()
    if configured:
        return configured, os.getenv("POLARIS_SKILL_VERSION", "").strip()
    args = _common.parser("Skill probe").parse_args(sdk_arguments(address, namespace))
    sdk = _common.context(args, entry=entry, component="skill-probe")
    try:
        if service_name:
            async with PolarisSkillLoader(
                sdk,
                namespace,
                service_name=service_name,
            ) as loader:
                skills = await loader.list_skills()
            if not skills:
                raise AssertionError(f"No mounted Skill is available on {namespace}/{service_name}")
            return skills[0].name, ""
        response = await SkillAPI(sdk).async_list_skills(
            SkillListRequest(
                namespace=namespace,
                offset=0,
                limit=50,
                timeout=5000,
            )
        )
    finally:
        await asyncio.to_thread(sdk.destroy)
    resources = [item for item in (response.resources or ()) if item.name.strip()]
    if not resources:
        raise AssertionError(f"No published Skill is available in {namespace}")
    selected = resources[0]
    version = selected.version_info.active_version if selected.version_info is not None else ""
    return selected.name, version


def assert_ai_logs(*categories):
    run = Path(os.environ["POLARIS_DEMO_RUN_DIR"])
    root = run / "polaris" / "log" / "ai"
    files = {}
    for category in categories:
        category_files = sorted(
            path for path in (root / category).glob("polaris-ai-*.log") if path.is_file()
        )
        assert category_files, f"No AI {category} log under {root}"
        files[category] = [str(path.relative_to(run)) for path in category_files]
    return files


async def eventually(callback, *, timeout=20, task=None):
    deadline = asyncio.get_running_loop().time() + timeout
    last_error = None
    while asyncio.get_running_loop().time() < deadline:
        if task is not None and task.done():
            await task
            raise AssertionError("Provider exited before verification completed")
        try:
            result = await callback()
            if result:
                return result
        except SDKError as error:
            last_error = error
        await asyncio.sleep(0.2)
    raise AssertionError(f"Timed out waiting for verification condition: {last_error}")


def assert_instance_agent_card(instance, name, host, *, registration_port=1):
    """Assert the instance-level AgentCard registration contract."""
    assert instance.get_host() == host
    assert instance.get_port() == registration_port
    assert instance.get_protocol() == ""
    metadata = instance.get_metadata()
    required_keys = {
        "ai-agent-name",
        "ai-agent-card",
        "ai-a2a-version",
    }
    # Discovery expands server-side location/version fields into metadata.
    assert required_keys <= set(metadata)
    assert not {"a2a.agent.card", "a2a.transport", "a2a.path"} & set(metadata)
    card_payload = json.loads(metadata["ai-agent-card"])
    assert card_payload["name"] == name
    assert instance.get_version() == card_payload["version"]
    assert metadata["ai-a2a-version"] == "1.0"
    interfaces = card_payload["supportedInterfaces"]
    assert interfaces and all(urlsplit(item["url"]).hostname == host for item in interfaces)
    return card_payload, interfaces


def retain_requested():
    return os.getenv(RETAIN_ENV, "").lower() in ("1", "true", "yes", "on")


def start_retained_provider(arguments):
    entry = REPO / "examples/agentscope/a2a/provider/main.py"
    run_dir = Path(os.environ["POLARIS_DEMO_RUN_DIR"])
    case_dir = Path(os.environ["POLARIS_DEMO_DIRECTORY"])
    work_dir = run_dir / "work"
    log_path = run_dir / "provider.log"
    process_options = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    output = log_path.open("w", encoding="utf-8")
    try:
        process = subprocess.Popen(
            [sys.executable, str(entry), *arguments],
            cwd=work_dir,
            env=os.environ.copy(),
            stdout=output,
            stderr=subprocess.STDOUT,
            text=True,
            **process_options,
        )
    finally:
        output.close()
    try:
        record = record_external_process(case_dir, psutil.Process(process.pid), entry)
    except BaseException:
        stop_retained_provider(process, None)
        raise
    return process, record, log_path


def stop_retained_provider(process, record):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    if record is not None:
        record.unlink(missing_ok=True)


async def call_card_interface(card_payload, binding, protocol_version, message):
    card = decode_card(card_payload)
    interface = next(
        (
            item
            for item in card.supported_interfaces
            if item.protocol_binding == binding and item.protocol_version == protocol_version
        ),
        None,
    )
    assert interface is not None, f"Missing {binding} {protocol_version} interface"
    selected = AgentCard()
    selected.CopyFrom(card)
    del selected.supported_interfaces[:]
    selected.supported_interfaces.append(interface)
    async with httpx.AsyncClient(timeout=10, trust_env=False) as http_client:
        client = ClientFactory(
            ClientConfig(
                streaming=True,
                polling=False,
                httpx_client=http_client,
                supported_protocol_bindings=[binding],
            )
        ).create(selected)
        async with A2AAgent(selected, client=client) as agent:
            reply = await agent.reply(UserMsg(name="user", content=message))
            return reply.get_text_content()


async def verify_retained_a2a(address, namespace, token):
    name = service_name("a2a-multi-protocol")
    host = get_local_host(address)
    args = sdk_arguments(address, namespace)
    provider, record, log_path = start_retained_provider(
        [
            *args,
            "--service",
            name,
            "--service-token",
            token,
            "--host",
            host,
            "--port",
            "0",
            "--ttl",
            "1",
            "--agent-version",
            "2.1.0",
            "--multi-protocol",
        ]
    )
    probe = None
    try:
        probe = _common.context(
            _common.parser("Retained A2A probe").parse_args(args),
            component="retained-probe",
        )
        consumer = ConsumerAPI(probe)
        request = GetAllInstancesRequest(namespace=namespace, service=name, timeout=1000)

        async def registered():
            if provider.poll() is not None:
                raise AssertionError(
                    f"Retained provider exited with code {provider.returncode}; log={log_path}"
                )
            snapshot = await consumer.async_get_all_instances(request)
            return next(
                (
                    instance
                    for instance in snapshot.get_instances()
                    if instance.is_healthy() and not instance.is_isolated()
                ),
                None,
            )

        instance = await eventually(registered, timeout=30)
        card_payload, interfaces = assert_instance_agent_card(instance, name, host)
        assert instance.get_version() == "2.1.0"
        assert len(interfaces) == 3
        declared = {
            (item["protocolBinding"], item["protocolVersion"], item.get("tenant", ""))
            for item in interfaces
        }
        assert declared == {
            ("JSONRPC", "1.0", name),
            ("JSONRPC", "0.3", ""),
            ("HTTP+JSON", "1.0", ""),
        }
        replies = [
            await call_card_interface(card_payload, "JSONRPC", "1.0", "jsonrpc-1.0"),
            await call_card_interface(card_payload, "JSONRPC", "0.3", "jsonrpc-0.3"),
            await call_card_interface(card_payload, "HTTP+JSON", "1.0", "http-json-1.0"),
        ]
        assert replies == [
            "Echo: jsonrpc-1.0",
            "Echo: jsonrpc-0.3",
            "Echo: http-json-1.0",
        ]
        await asyncio.sleep(3.2)
        assert await registered(), "Retained provider disappeared while heartbeats ran"
    except BaseException:
        stop_retained_provider(provider, record)
        raise
    finally:
        if probe is not None:
            await asyncio.to_thread(probe.destroy)
    return {
        "service": name,
        "instance_id": instance.get_id(),
        "interfaces": interfaces,
        "replies": replies,
        "retained": True,
        "pid": provider.pid,
        "process_record": str(record),
        "provider_log": str(log_path),
    }


async def verify_a2a(
    address,
    namespace,
    token,
    stub,
    *,
    provider_arguments=(),
    service_kind="a2a",
    messages=("Hello Polaris",),
    expected_reply="Echo: Hello Polaris",
):
    name = service_name(service_kind) if stub is None else "offline-echo-agent"
    host = get_local_host(address) if stub is None else "127.0.0.1"
    args = sdk_arguments(address, namespace)
    initial_counts = (
        (stub.count("register"), stub.count("deregister")) if stub is not None else (0, 0)
    )
    provider = asyncio.create_task(
        provider_demo.main(
            [
                *args,
                "--service",
                name,
                "--service-token",
                token,
                "--host",
                host,
                "--port",
                "0",
                "--ttl",
                "1",
                "--multi-interface",
                *provider_arguments,
            ]
        )
    )
    probe = None
    instance_id = None
    try:
        probe = _common.context(_common.parser("Probe").parse_args(args), component="probe")
        consumer = ConsumerAPI(probe)
        request = GetAllInstancesRequest(namespace=namespace, service=name, timeout=1000)

        async def registered():
            snapshot = await consumer.async_get_all_instances(request)
            return next(
                (
                    i
                    for i in snapshot.get_instances()
                    if i.get_metadata().get("ai-agent-name") == name
                    and i.is_healthy()
                    and not i.is_isolated()
                ),
                None,
            )

        instance = await eventually(registered, task=provider)
        instance_id = instance.get_id()
        assert instance_id
        _, interfaces = assert_instance_agent_card(instance, name, host)
        assert len(interfaces) >= 2
        assert {"JSONRPC", "HTTP+JSON"} <= {item["protocolBinding"] for item in interfaces}
        registration_port = instance.get_port()
        business_port = urlsplit(interfaces[0]["url"]).port
        assert business_port and business_port != registration_port
        consumer_arguments = [*args, "--service", name]
        for message in messages:
            consumer_arguments += ["--message", message]
        reply = await consumer_demo.main(consumer_arguments)
        if expected_reply is not None:
            assert reply == expected_reply
        if stub is not None:

            async def heartbeat_seen():
                return stub.count("heartbeat") > 0

            await eventually(heartbeat_seen, timeout=5, task=provider)
        else:
            await asyncio.sleep(3.2)
            assert await registered(), "TTL 1 provider disappeared while automatic heartbeats ran"
    finally:
        provider.cancel()
        try:
            with contextlib.suppress(asyncio.CancelledError):
                await provider
            if probe is not None and instance_id is not None:

                async def deregistered():
                    snapshot = await ConsumerAPI(probe).async_get_all_instances(
                        GetAllInstancesRequest(namespace=namespace, service=name, timeout=1000),
                    )
                    return all(i.get_id() != instance_id for i in snapshot.get_instances())

                await eventually(deregistered)
        finally:
            if probe is not None:
                await asyncio.to_thread(probe.destroy)
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family) as reserved:
        reserved.bind((host, 0))
        control_port = reserved.getsockname()[1]
    with socket.socket(family) as control:
        control.settimeout(1)
        port_probe_available = control.connect_ex((host, control_port)) != 0
    if port_probe_available:
        with socket.socket(family) as client:
            client.settimeout(1)
            assert client.connect_ex((host, business_port)) != 0, (
                "A2A listener remained open after shutdown"
            )
    if stub is not None:
        assert (
            stub.count("register") - initial_counts[0] == 1
            and stub.count("deregister") - initial_counts[1] == 1
        )
        assert not stub.instances
        heartbeats = stub.count("heartbeat")
        await asyncio.sleep(1.2)
        assert stub.count("heartbeat") == heartbeats, "Heartbeat continued after deregistration"
    return {
        "service": name,
        "instance_id": instance_id,
        "host": host,
        "registration_port": registration_port,
        "business_port": business_port,
        "reply": reply,
        "deregistered": True,
    }


async def verify_streaming_provider(address, namespace, token, stub):
    name = service_name("a2a-streaming")
    host = get_local_host(address) if stub is None else "127.0.0.1"
    args = sdk_arguments(address, namespace)
    provider = asyncio.create_task(
        streaming_provider_demo.main(
            [
                *args,
                "--service",
                name,
                "--service-token",
                token,
                "--host",
                host,
                "--port",
                "0",
                "--ttl",
                "1",
            ]
        )
    )
    probe = None
    instance_id = None
    try:
        probe = _common.context(
            _common.parser("Streaming probe").parse_args(args),
            component="streaming-probe",
        )
        consumer = ConsumerAPI(probe)

        async def registered():
            snapshot = await consumer.async_get_all_instances(
                GetAllInstancesRequest(
                    namespace=namespace,
                    service=name,
                    timeout=1000,
                )
            )
            return next(
                (
                    instance
                    for instance in snapshot.get_instances()
                    if instance.is_healthy() and not instance.is_isolated()
                ),
                None,
            )

        instance = await eventually(registered, task=provider)
        instance_id = instance.get_id()
        assert instance_id
        assert_instance_agent_card(instance, name, host)
        replies = await console_consumer_demo.main(
            [
                *args,
                "--service",
                name,
                "--message",
                "weather in Shanghai",
                "--message",
                "12 + 30",
            ]
        )
        assert isinstance(replies, list) and len(replies) == 2
        assert "Sunny" in replies[0] and "Shanghai" in replies[0]
        assert "42" in replies[1]
    finally:
        provider.cancel()
        try:
            with contextlib.suppress(asyncio.CancelledError):
                await provider
            if probe is not None and instance_id is not None:
                consumer = ConsumerAPI(probe)

                async def deregistered():
                    snapshot = await consumer.async_get_all_instances(
                        GetAllInstancesRequest(
                            namespace=namespace,
                            service=name,
                            timeout=1000,
                        )
                    )
                    return all(
                        instance.get_id() != instance_id for instance in snapshot.get_instances()
                    )

                await eventually(deregistered)
        finally:
            if probe is not None:
                await asyncio.to_thread(probe.destroy)
    return {
        "service": name,
        "instance_id": instance_id,
        "replies": replies,
        "streamed_tools": True,
        "deregistered": True,
    }


async def verify_state_resume(address, namespace, token, stub):
    name = service_name("a2a-state-resume")
    host = get_local_host(address) if stub is None else "127.0.0.1"
    args = sdk_arguments(address, namespace)
    provider = asyncio.create_task(
        streaming_provider_demo.main(
            [
                *args,
                "--service",
                name,
                "--service-token",
                token,
                "--host",
                host,
                "--port",
                "0",
                "--ttl",
                "1",
            ]
        )
    )
    probe = None
    instance_id = None
    state_file = Path.cwd() / "a2a-state.json"
    try:
        probe = _common.context(
            _common.parser("State probe").parse_args(args),
            component="state-probe",
        )
        consumer = ConsumerAPI(probe)

        async def registered():
            snapshot = await consumer.async_get_all_instances(
                GetAllInstancesRequest(
                    namespace=namespace,
                    service=name,
                    timeout=1000,
                )
            )
            return next(
                (
                    instance
                    for instance in snapshot.get_instances()
                    if instance.is_healthy() and not instance.is_isolated()
                ),
                None,
            )

        instance = await eventually(registered, task=provider)
        instance_id = instance.get_id()
        common = [
            *args,
            "--service",
            name,
            "--state-file",
            str(state_file),
        ]
        first = await state_resume_demo.main(
            [
                *common,
                "--message",
                "remember first turn",
            ]
        )
        second = await state_resume_demo.main(
            [
                *common,
                "--message",
                "continue same context",
            ]
        )
        assert first["context_id"]
        assert first["context_id"] == second["context_id"]
        assert "first turn" in first["replies"][0]
        assert "same context" in second["replies"][0]
        assert state_file.is_file()
    finally:
        provider.cancel()
        try:
            with contextlib.suppress(asyncio.CancelledError):
                await provider
            if probe is not None and instance_id is not None:
                consumer = ConsumerAPI(probe)

                async def deregistered():
                    snapshot = await consumer.async_get_all_instances(
                        GetAllInstancesRequest(
                            namespace=namespace,
                            service=name,
                            timeout=1000,
                        )
                    )
                    return all(
                        instance.get_id() != instance_id for instance in snapshot.get_instances()
                    )

                await eventually(deregistered)
        finally:
            if probe is not None:
                await asyncio.to_thread(probe.destroy)
    return {
        "service": name,
        "context_id": first["context_id"],
        "task_id": second["task_id"],
        "turns": 2,
        "resumed": True,
    }


async def verify_skill_a2a(address, namespace, token, stub):
    mounted_service = os.getenv("POLARIS_AGENT_SERVICE", "") if stub is None else ""
    if stub is None:
        skill_name, discovered_version = await real_skill_reference(
            address,
            namespace,
            entry=__file__,
            service_name=mounted_service,
        )
        skill_version = os.getenv("POLARIS_SKILL_VERSION", "") or discovered_version
    else:
        skill_name, skill_version = "weather", ""

    async def verify_source(source, service=""):
        provider_arguments = [
            "--skill-source",
            source,
            "--skill-version",
            skill_version,
        ]
        if source == "published":
            provider_arguments += ["--skill-name", skill_name]
        if source == "mounted":
            provider_arguments += ["--skill-service", service]
        result = await verify_a2a(
            address,
            namespace,
            token,
            stub,
            provider_arguments=provider_arguments,
            service_kind="a2a-skill",
            messages=("/skill-list", f"/skill {skill_name}"),
            expected_reply=None,
        )
        replies = result["reply"]
        assert isinstance(replies, list) and len(replies) == 2
        assert replies[0] == skill_name
        assert replies[1].startswith(f"{skill_name}\n\n")
        return result

    if stub is None:
        source = "mounted" if mounted_service else "published"
        result = await verify_source(source, mounted_service)
        result["skill_source"] = source
        result["skill_name"] = skill_name
        return result

    published = await verify_source("published")
    stub.mounted_services = {"offline-echo-agent"}
    await verify_source("mounted", "offline-echo-agent")
    published["skill_sources"] = ["published", "mounted"]
    published["skill_name"] = skill_name
    return published


async def verify_skills(demo, address, namespace, stub):
    args = sdk_arguments(address, namespace)
    version = os.getenv("POLARIS_SKILL_VERSION", "") if stub is None else "code-v1"
    names = []
    if stub is None and demo == "published":
        skill_name, discovered_version = await real_skill_reference(
            address,
            namespace,
            entry=__file__,
        )
        names = [skill_name]
        version = version or discovered_version
    service = (
        (os.environ["POLARIS_AGENT_SERVICE"] if stub is None else "mounted-agent")
        if demo == "mounted"
        else ""
    )
    demo_args = [*args, "--version", "" if stub is not None and demo == "published" else version]
    if demo == "published":
        for name in names:
            demo_args += ["--name", name]
        await published_demo.main(demo_args)
    else:
        await mounted_demo.main([*demo_args, "--service", service])
    previous_downloads = stub.count("download_skill") if stub is not None else 0
    sdk = _common.context(_common.parser("Probe").parse_args(args), component="probe")
    log_manager = _common.ai_log_manager(sdk, entry=__file__)
    directories = []
    try:
        if stub is not None and demo == "published":
            stub.failed_downloads.add("weather")
        async with PolarisSkillLoader(
            sdk,
            namespace,
            names=names,
            service_name=service,
            version=version,
            list_limit=1,
            timeout=5000,
            logger=log_manager.get_logger("skill"),
        ) as loader:
            toolkit = Toolkit(skills_or_loaders=[loader])
            instructions = await toolkit.get_skill_instructions()
            skills = await loader.list_skills()
            instructions = await toolkit.get_skill_instructions()
            assert skills and instructions, "No readable Skills were loaded"
            cached = await loader.list_skills()
            assert [id(skill) for skill in skills] == [id(skill) for skill in cached]
            for skill in skills:
                path = Path(skill.dir)
                assert skill.name and skill.description and (path / "SKILL.md").is_file()
                assert skill.name in instructions
                assert skill.markdown.strip(), "Skill instructions were empty"
                directories.append(path)
                if stub is not None:
                    assert (path / "references.txt").read_text() == f"{skill.name} reference"
            if stub is not None:
                expected = ["weather"] if demo == "mounted" else ["weather", "lookup"]
                assert [skill.name for skill in skills] == expected
                downloads = [
                    request for method, request in stub.calls if method == "download_skill"
                ]
                assert all(request.format == "zip" for request in downloads)
                if demo == "mounted":
                    assert not stub.count("list_skills"), "Mounted loader listed unrelated Skills"
                    assert {request.version for request in downloads} == {"mounted-v2"}
                else:
                    assert {request.version for request in downloads[:previous_downloads]} == {
                        "published-v1"
                    }
                    assert {request.version for request in downloads[previous_downloads:]} == {
                        "code-v1"
                    }
                    assert any(
                        method == "list_skills" and request.offset == 1
                        for method, request in stub.calls
                    ), "Pagination was not exercised"
        assert all(not directory.exists() for directory in directories)
        assert not sdk.is_destroy(), "Loader destroyed a borrowed SDKContext"
    finally:
        try:
            await log_manager.async_close()
        finally:
            await asyncio.to_thread(sdk.destroy)
    return {
        "skills": [skill.name for skill in skills],
        "temporary_assets_removed": True,
        "mounted_service": service,
    }


async def verify_mcp(address, namespace, stub):
    service = os.getenv("POLARIS_MCP_SERVICE") if stub is None else "offline-mcp"
    result = await mcp_demo.main(
        [
            *sdk_arguments(address, namespace),
            "--service",
            service,
            "--protocol-version",
            "2025-06-18",
        ]
    )
    assert result["instances"]
    assert result["url"].endswith("/mcp")
    assert result["protocol"] == "mcp-streamable-http"
    assert isinstance(result["disabled_tools"], list)
    if stub is not None:
        assert result["disabled_tools"] == ["disabled_tool"]
    if stub is not None:
        assert stub.count("get_contract") >= 1
    return {
        "mcp_service": service,
        "url": result["url"],
        "disabled_tools": result["disabled_tools"],
    }


async def verify_mcp_agent(address, namespace, stub):
    host = get_local_host(address) if stub is None else "127.0.0.1"
    result = await mcp_agent_demo.main(
        [
            *sdk_arguments(address, namespace),
            "--service",
            service_name("mcp-agent"),
            "--host",
            host,
            "--port",
            "0",
            "--ttl",
            "1",
            "--message",
            "hello over MCP",
        ]
    )
    assert result["protocol"] == "mcp-streamable-http"
    assert "echo_text" in result["tools"]
    assert "MCP echo: hello over MCP" in result["reply"]
    if stub is not None:
        assert stub.count("register") == 1
        assert stub.count("deregister") == 1
        assert not stub.instances
    return result


async def verify_skill_console(address, namespace, stub):
    if stub is None:
        skill_name, skill_version = await real_skill_reference(
            address,
            namespace,
            entry=__file__,
        )
    else:
        skill_name, skill_version = "weather", ""
    result = await skill_console_demo.main(
        [
            *sdk_arguments(address, namespace),
            "--skill-name",
            skill_name,
            "--skill-version",
            skill_version,
            "--message",
            "/skill-list",
            "--message",
            f"/skill {skill_name}",
        ]
    )
    assert result[0] == skill_name
    assert result[1].startswith(f"{skill_name}\n\n")
    return {
        "skill_name": skill_name,
        "skill_version": skill_version,
        "replies": result,
    }


async def verify_runtime(address, namespace, stub):
    arguments = [*sdk_arguments(address, namespace), "--load-skills"]
    if stub is None:
        skill_name, _ = await real_skill_reference(
            address,
            namespace,
            entry=__file__,
        )
    else:
        skill_name = "weather"
    if skill_name:
        arguments += ["--skill-name", skill_name]
    result = await runtime_demo.main(arguments)
    assert result["borrowed_context"]
    assert result["a2a_resolver"] and result["a2a_registrar"]
    assert result["mcp_resolver"] is False
    assert skill_name in result["skill_names"]
    return result


async def verify_runtime_multi(address, namespace, stub):
    if stub is None:
        skill_name, skill_version = await real_skill_reference(
            address,
            namespace,
            entry=__file__,
        )
    else:
        skill_name, skill_version = "weather", ""
    result = await runtime_multi_demo.main(
        [
            *sdk_arguments(address, namespace),
            "--skill-name",
            skill_name,
            "--skill-version",
            skill_version,
        ]
    )
    assert result["agent_count"] == 2
    assert result["shared_toolkit"]
    assert skill_name in result["first_reply"]
    assert result["second_reply"].startswith(f"{skill_name}\n\n")
    return result


def _json_request(url, *, method="GET", body=None, timeout=10):
    import urllib.request

    headers = {"Content-Type": "application/json"} if body is not None else {}
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        headers=headers,
        method=method,
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


async def verify_agent_service(address, namespace, stub):
    service = service_name("agent-service")
    if stub is None:
        skill_name, skill_version = await real_skill_reference(
            address,
            namespace,
            entry=__file__,
        )
    else:
        skill_name, skill_version = "weather", ""
    ready_file = Path.cwd() / "agent-service-ready.json"
    task = asyncio.create_task(
        agent_service_demo.main(
            [
                *sdk_arguments(address, namespace),
                "--service",
                service,
                "--host",
                "127.0.0.1",
                "--port",
                "0",
                "--ttl",
                "1",
                "--ready-file",
                str(ready_file),
                "--load-skills",
                "--skill-name",
                skill_name,
                "--skill-version",
                skill_version,
            ]
        )
    )
    probe = None
    instance_id = None
    try:

        async def ready():
            if ready_file.is_file():
                return json.loads(ready_file.read_text(encoding="utf-8"))
            return None

        descriptor = await eventually(ready, timeout=20, task=task)
        instance_id = descriptor["instance_id"]
        endpoint = descriptor["endpoint"]
        health = await asyncio.to_thread(_json_request, f"{endpoint}/health")
        assert health["status"] == "ok"
        assert health["skills"]
        first = await asyncio.to_thread(
            _json_request,
            f"{endpoint}/chat",
            method="POST",
            body={"session_id": "first", "message": "/skill-list"},
        )
        second = await asyncio.to_thread(
            _json_request,
            f"{endpoint}/chat",
            method="POST",
            body={"session_id": "second", "message": "plain service message"},
        )
        assert skill_name in first["reply"]
        assert second["reply"] == "Echo: plain service message"
        health = await asyncio.to_thread(_json_request, f"{endpoint}/health")
        assert health["sessions"] == 2
    finally:
        task.cancel()
        try:
            with contextlib.suppress(asyncio.CancelledError):
                await task
            probe = _common.context(
                _common.parser("Service probe").parse_args(sdk_arguments(address, namespace)),
                component="service-probe",
            )
            if instance_id is not None:
                consumer = ConsumerAPI(probe)

                async def deregistered():
                    snapshot = await consumer.async_get_all_instances(
                        GetAllInstancesRequest(
                            namespace=namespace,
                            service=service,
                            timeout=1000,
                        )
                    )
                    return all(
                        instance.get_id() != instance_id for instance in snapshot.get_instances()
                    )

                await eventually(deregistered)
        finally:
            if probe is not None:
                await asyncio.to_thread(probe.destroy)
    if stub is not None:
        assert not stub.instances
    return {
        "service": service,
        "skill_name": skill_name,
        "sessions": 2,
        "http_verified": True,
        "deregistered": True,
    }


async def verify(demo, real):
    namespace = e2e_namespace()
    stub = None if real else RegistryStub(namespace)
    address, token = required_environment(demo) if real else ("offline:8091", "offline-token")
    contexts = []
    initialize = _common.init_context_by_config

    def tracked_context(*args, **kwargs):
        sdk = initialize(*args, **kwargs)
        contexts.append(sdk)
        return sdk

    boundary = (
        patch.dict("os.environ", scenario_environment(address)) if real else offline_registry(stub)
    )
    with boundary, patch.object(_common, "init_context_by_config", tracked_context):
        try:
            if real and retain_requested():
                if demo != "a2a":
                    raise ValueError("--retain is only supported for the A2A provider case")
                result = await verify_retained_a2a(address, namespace, token)
            else:
                result = (
                    await verify_a2a(address, namespace, token, stub)
                    if demo == "a2a"
                    else await verify_streaming_provider(address, namespace, token, stub)
                    if demo == "streaming-provider"
                    else await verify_state_resume(address, namespace, token, stub)
                    if demo == "state-resume"
                    else await verify_skill_a2a(address, namespace, token, stub)
                    if demo == "skill-a2a"
                    else await verify_mcp(address, namespace, stub)
                    if demo == "mcp"
                    else await verify_mcp_agent(address, namespace, stub)
                    if demo == "mcp-agent"
                    else await verify_runtime(address, namespace, stub)
                    if demo == "runtime"
                    else await verify_runtime_multi(address, namespace, stub)
                    if demo == "runtime-multi"
                    else await verify_skill_console(address, namespace, stub)
                    if demo == "skill-console"
                    else await verify_agent_service(address, namespace, stub)
                    if demo == "agent-service"
                    else await verify_skills(demo, address, namespace, stub)
                )
        finally:
            for sdk in reversed(contexts):
                await asyncio.to_thread(sdk.destroy)
        for sdk in contexts:
            assert sdk.is_destroy() and not sdk.get_engine().thread.is_alive()
            flow = sdk.get_engine().skill_flow
            if flow is not None:
                assert not flow.persistence.write_thread.is_alive()
        assert len({sdk.get_client_id() for sdk in contexts}) == len(contexts)
    expected_ai_categories = {
        "a2a": ("a2a",),
        "streaming-provider": ("a2a",),
        "state-resume": ("a2a",),
        "skill-a2a": ("a2a", "agentscope", "skill"),
        "mcp": ("mcp",),
        "mcp-agent": ("mcp",),
        "published": ("skill",),
        "mounted": ("skill",),
        "runtime": ("base", "skill", "a2a"),
        "runtime-multi": ("base", "agentscope", "skill"),
        "skill-console": ("agentscope", "skill"),
        "agent-service": ("agentscope", "skill"),
    }[demo]
    ai_logs = assert_ai_logs(*expected_ai_categories)
    result.update(
        demo=demo,
        mode="real" if real else "offline",
        namespace=namespace,
        contexts_stopped=len(contexts),
        ai_logs=ai_logs,
    )
    print(json.dumps(result), flush=True)


def main():
    arguments = argparse.ArgumentParser(description=__doc__)
    arguments.add_argument(
        "--demo",
        choices=(
            "a2a",
            "streaming-provider",
            "state-resume",
            "skill-a2a",
            "mcp",
            "mcp-agent",
            "published",
            "mounted",
            "runtime",
            "runtime-multi",
            "skill-console",
            "agent-service",
        ),
        required=True,
    )
    arguments.add_argument("--real", action="store_true")
    args = arguments.parse_args()
    with verification_directory(__file__):
        asyncio.run(verify(args.demo, args.real))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
