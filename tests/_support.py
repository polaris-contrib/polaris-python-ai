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

import io
import zipfile

from polaris.pkg.model.core import ServiceKey
from polaris.pkg.model.server import InstanceRegisterResponse
from polaris.pkg.model.service import Instance, ServiceInstances
from polarismesh_specification.api.v1.service_manage import service_pb2


class FakeContext:
    def __init__(self, engine):
        self.engine = engine
        self.destroyed = False

    def get_engine(self):
        return self.engine

    def is_destroy(self):
        return self.destroyed

    def destroy(self):
        self.destroyed = True


class FakeEngine:
    def __init__(self):
        self.pages = []
        self.downloads = {}
        self.snapshot = snapshot()
        self.skill_calls = []
        self.discovery_calls = []
        self.register_calls = []
        self.deregister_calls = []
        self.register_failure_at = None
        self.deregister_failures = set()
        self.discovery_error = None

    async def async_skill_call(self, method, request):
        self.skill_calls.append((method, request))
        if method == "list_skills":
            result = self.pages.pop(0)
        else:
            result = self.downloads[(request.name, request.version)]
        if isinstance(result, BaseException):
            raise result
        return result

    async def async_get_all_instances(self, request):
        self.discovery_calls.append(request)
        return self.snapshot

    def sync_get_healthy_instances(self, request):
        self.discovery_calls.append(request)
        if self.discovery_error:
            raise self.discovery_error
        return self.snapshot

    def sync_register(self, request):
        self.register_calls.append(request)
        if len(self.register_calls) == self.register_failure_at:
            raise RuntimeError("registration failed")
        return InstanceRegisterResponse(f"id-{len(self.register_calls)}")

    def sync_deregister(self, request):
        self.deregister_calls.append(request)
        if request.instance_id in self.deregister_failures:
            raise RuntimeError("deregistration failed")


def snapshot(instances=(), mounts=(), *, offline=False):
    service = service_pb2.Service(service_status=service_pb2.OFFLINE if offline else service_pb2.NORMAL)
    service.namespace.value = "default"
    service.name.value = "weather-agent"
    for name, version, identity in mounts:
        meta = service.extended_metadata.add(type=service_pb2.ExtendedMetadata.EXTENDED_METADATA_SKILL)
        meta.agent_skill.name = name
        meta.agent_skill.version = version
        meta.agent_skill.id = identity
    return ServiceInstances(service=service, instances=list(instances))


def instance(host, payload, *, healthy=True, isolated=False):
    raw = service_pb2.Instance()
    raw.id.value = host
    raw.host.value = host
    raw.port.value = 8080
    raw.healthy.value = healthy
    raw.isolate.value = isolated
    raw.metadata["a2a.agent.card"] = payload
    return Instance(raw, ServiceKey("default", "weather-agent"))


def skill_zip(root="", *, name="weather", extra=None, markdown=None):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(root + "SKILL.md", markdown or (
            f"---\nname: {name}\ndescription: Weather lookup\n---\nUse weather.txt.\n"
        ))
        archive.writestr(root + "weather.txt", "weather reference")
        if extra:
            archive.writestr(*extra)
    return stream.getvalue()
