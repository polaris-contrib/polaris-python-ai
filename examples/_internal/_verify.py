"""Verify AgentScope examples with real local behavior or an explicit Polaris endpoint."""

# Direct script execution adds the checkout before importing local modules.
# ruff: noqa: E402

import argparse
import asyncio
import contextlib
import json
import os
import socket
import sys
import time
import uuid
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "src"), str(REPO)]

from agentscope.tool import Toolkit
from polaris.api.consumer import ConsumerAPI
from polaris.pkg.model.error import SDKError
from polaris.pkg.model.service import GetAllInstancesRequest

from examples._internal._runtime import get_local_host, verification_directory
from examples._internal._stub import RegistryStub, offline_registry
from examples.agentscope import _common
from examples.agentscope.a2a.consumer import main as consumer_demo
from examples.agentscope.a2a.provider import main as provider_demo
from examples.agentscope.mcp import main as mcp_demo
from examples.agentscope.skill.mounted import main as mounted_demo
from examples.agentscope.skill.published import main as published_demo
from polaris_ai.agentscope import PolarisSkillLoader


def required_environment(demo):
    address = (
        os.getenv("POLARIS_SERVER_ADDRESS") or os.getenv("POLARIS_SERVER_ADDRESSES", "")
    ).strip()
    if not address:
        raise ValueError("POLARIS_SERVER_ADDRESS is required for real-service verification")
    address = address.split(",", 1)[0].strip()
    token = os.getenv("POLARIS_E2E_SERVICE_TOKEN") or os.getenv("POLARIS_SERVICE_TOKEN", "")
    if demo in ("a2a", "skill-a2a") and not token:
        raise ValueError("POLARIS_SERVICE_TOKEN or POLARIS_E2E_SERVICE_TOKEN is required")
    if demo in ("published", "skill-a2a") and not os.getenv("POLARIS_SKILL_NAME"):
        raise ValueError("POLARIS_SKILL_NAME must identify a published Skill")
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


def service_name():
    return f"polaris-python-ai-e2e-agentscope-a2a-{time.time_ns()}-{uuid.uuid4().hex[:6]}"


def sdk_arguments(address, namespace):
    arguments = ["--address", address, "--namespace", namespace, "--timeout", "5000"]
    if os.getenv("POLARIS_DEMO_OFFLINE") != "1" and (configured := os.getenv("POLARIS_E2E_CONFIG")):
        arguments += ["--config", configured]
    return arguments


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


async def verify_a2a(
    address,
    namespace,
    token,
    stub,
    *,
    provider_arguments=(),
    messages=("Hello Polaris",),
    expected_reply="Echo: Hello Polaris",
):
    name = service_name() if stub is None else "offline-echo-agent"
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
        assert instance_id and instance.get_host() == host
        port = instance.get_port()
        assert port > 0
        metadata = instance.get_metadata()
        assert metadata["a2a.transport"] == "JSONRPC"
        assert json.loads(metadata["a2a.agent.card"])["name"] == name
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
            assert client.connect_ex((host, port)) != 0, "A2A listener remained open after shutdown"
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
        "port": port,
        "reply": reply,
        "deregistered": True,
    }


async def verify_skill_a2a(address, namespace, token, stub):
    skill_name = os.getenv("POLARIS_SKILL_NAME") if stub is None else "weather"
    skill_version = os.getenv("POLARIS_SKILL_VERSION", "") if stub is None else ""
    mounted_service = os.getenv("POLARIS_AGENT_SERVICE", "") if stub is None else ""

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
    names = [os.environ["POLARIS_SKILL_NAME"]] if stub is None and demo == "published" else []
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
        await asyncio.to_thread(sdk.destroy)
    return {
        "skills": [skill.name for skill in skills],
        "temporary_assets_removed": True,
        "mounted_service": service,
    }


async def verify_mcp(address, namespace, stub):
    service = os.getenv("POLARIS_MCP_SERVICE") if stub is None else "offline-mcp"
    result = await mcp_demo.main([
        *sdk_arguments(address, namespace),
        "--service",
        service,
        "--protocol-version",
        "2025-06-18",
    ])
    assert result["instances"]
    assert result["url"].endswith("/mcp")
    assert result["protocol"] == "mcp-streamable-http"
    assert result["disabled_tools"] == ["disabled_tool"]
    if stub is not None:
        assert stub.count("get_contract") >= 1
    return {
        "mcp_service": service,
        "url": result["url"],
        "disabled_tools": result["disabled_tools"],
    }


async def verify(demo, real):
    namespace = os.getenv("POLARIS_E2E_NAMESPACE", "python-integration")
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
            result = (
                await verify_a2a(address, namespace, token, stub)
                if demo == "a2a"
                else await verify_skill_a2a(address, namespace, token, stub)
                if demo == "skill-a2a"
                else await verify_mcp(address, namespace, stub)
                if demo == "mcp"
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
    result.update(
        demo=demo,
        mode="real" if real else "offline",
        namespace=namespace,
        contexts_stopped=len(contexts),
    )
    print(json.dumps(result), flush=True)


def main():
    arguments = argparse.ArgumentParser(description=__doc__)
    arguments.add_argument(
        "--demo", choices=("a2a", "skill-a2a", "mcp", "published", "mounted"), required=True
    )
    arguments.add_argument("--real", action="store_true")
    args = arguments.parse_args()
    with verification_directory(__file__):
        asyncio.run(verify(args.demo, args.real))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
