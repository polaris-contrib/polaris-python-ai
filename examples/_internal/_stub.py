"""Replace only specification RPC calls during offline example verification."""

import io
import threading
import zipfile
from contextlib import contextmanager
from unittest.mock import patch

from polaris.plugin.server_connector.grpc_connector.connection import GrpcConnection
from polarismesh_specification.api.v1.service_manage import contract_pb2, response_pb2, service_pb2
from polarismesh_specification.api.v1.skill_manage import skill_service_pb2 as skill_pb2


class RegistryStub:
    def __init__(self, namespace):
        self.namespace = namespace
        self.instances = {}
        self.calls = []
        self.revision = 0
        self.lock = threading.RLock()
        self.failed_downloads = set()
        self.packages = {}
        self.mounted_services = {"mounted-agent"}
        for name in ("weather", "lookup"):
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w") as archive:
                archive.writestr(
                    "SKILL.md",
                    f"---\nname: {name}\ndescription: {name} integration fixture\n"
                    f"---\nUse references.txt for {name}.\n",
                )
                archive.writestr("references.txt", f"{name} reference")
            self.packages[name] = stream.getvalue()

    async def ReportClient(self, request, **kwargs):
        return response_pb2.Response(code={"value": 200000})

    async def RegisterInstance(self, request, **kwargs):
        with self.lock:
            self.calls.append(("register", request))
            self.revision += 1
            instance = service_pb2.Instance()
            instance.CopyFrom(request)
            instance.id.value = f"ai-instance-{self.revision}"
            instance.healthy.value = True
            self.instances[instance.id.value] = instance
            return response_pb2.Response(code={"value": 200000}, instance=instance)

    async def Heartbeat(self, request, **kwargs):
        with self.lock:
            self.calls.append(("heartbeat", request))
        return response_pb2.Response(code={"value": 200000})

    async def DeregisterInstance(self, request, **kwargs):
        with self.lock:
            self.calls.append(("deregister", request))
            self.instances.pop(request.id.value, None)
            self.revision += 1
        return response_pb2.Response(code={"value": 200000})

    async def GetServiceContract(self, request, **kwargs):
        with self.lock:
            self.calls.append(("get_contract", request))
        contract = contract_pb2.ServiceContract(
            namespace=request.namespace,
            service=request.service,
            protocol="mcp-streamable-http",
            version=request.version or "mcp-v1",
            service_features=[
                contract_pb2.ServiceFeature(
                    type=contract_pb2.Service_Feature_Type_MCP_Tool,
                    name="disabled_tool",
                    status=contract_pb2.Service_Feature_Status_Disabled,
                ),
                contract_pb2.ServiceFeature(
                    type=contract_pb2.Service_Feature_Type_MCP_Tool,
                    name="search",
                    status=contract_pb2.Service_Feature_Status_Enabled,
                ),
            ],
        )
        return response_pb2.Response(code={"value": 200000}, serviceContract=contract)

    def Discover(self, requests, **kwargs):
        async def responses():
            async for request in requests:
                with self.lock:
                    self.calls.append(("discover", request))
                    instances = [
                        item
                        for item in self.instances.values()
                        if item.namespace.value == request.service.namespace.value
                        and item.service.value == request.service.name.value
                    ]
                    if request.service.name.value == "offline-mcp":
                        instances = [service_pb2.Instance(
                            id={"value": "offline-mcp-1"},
                            namespace={"value": request.service.namespace.value},
                            service={"value": request.service.name.value},
                            host={"value": "127.0.0.1"},
                            port={"value": 18080},
                            healthy={"value": True},
                            weight={"value": 100},
                            protocol={"value": "mcp-streamable-http"},
                            version={"value": "mcp-v1"},
                            metadata={
                                "mcp-server-name": "offline-mcp",
                                "mcp-protocol-version": "2025-06-18",
                                "mcp-endpoint-path": "/mcp",
                            },
                        )]
                    mounts = (
                        [
                            {
                                "type": service_pb2.ExtendedMetadata.EXTENDED_METADATA_SKILL,
                                "agent_skill": {
                                    "name": f"{self.namespace}:weather",
                                    "version": "mounted-v2",
                                },
                            },
                            {
                                "type": service_pb2.ExtendedMetadata.EXTENDED_METADATA_SKILL,
                                "agent_skill": {
                                    "name": f"{self.namespace}-other:lookup",
                                    "version": "v1",
                                },
                            },
                        ]
                        if request.service.name.value in self.mounted_services
                        else []
                    )
                    response = response_pb2.DiscoverResponse(
                        code={"value": 200000},
                        type=request.type,
                        service=service_pb2.Service(
                            name=request.service.name,
                            namespace=request.service.namespace,
                            revision={"value": str(self.revision)},
                            extended_metadata=mounts,
                        ),
                        instances=instances,
                    )
                yield response

        return responses()

    async def GetSkillList(self, request, **kwargs):
        self.calls.append(("list_skills", request))
        names = list(self.packages)
        return skill_pb2.ListSkillsResponse(
            code=200000,
            total=len(names),
            resources=[
                {
                    "name": name,
                    "namespace": request.namespace,
                    "version_info": {"active_version": "published-v1"},
                }
                for name in names[request.offset : request.offset + request.limit]
            ],
        )

    def DownloadSkill(self, request, **kwargs):
        self.calls.append(("download_skill", request))

        async def responses():
            if request.name in self.failed_downloads:
                self.failed_downloads.remove(request.name)
                yield skill_pb2.DownloadSkillResponse(code=500000)
                return
            package = self.packages[request.name]
            yield skill_pb2.DownloadSkillResponse(
                code=200000,
                version=request.version or "published-v1",
                content_type="application/zip",
                filename=f"{request.name}.zip",
                total_size=len(package),
                zip_chunk=package[:31],
            )
            yield skill_pb2.DownloadSkillResponse(code=0, zip_chunk=package[31:])

        return responses()

    def count(self, method):
        with self.lock:
            return sum(name == method for name, _ in self.calls)


@contextmanager
def offline_registry(stub):
    async def rpc_stub(connection, address):
        return stub

    with (
        patch.object(GrpcConnection, "_stub", rpc_stub),
        patch.dict(
            "os.environ",
            {
                "POLARIS_DEMO_OFFLINE": "1",
                "POLARIS_SERVER_ADDRESS": "offline:8091",
                "POLARIS_SERVER_ADDRESSES": "offline:8091",
                "POLARIS_SERVER": "offline:8091",
                "POLARIS_SKILL_SERVER_ADDRESS": "offline:8094",
            },
        ),
    ):
        yield
