# MCP 分组测试说明

离线：

```bash
./integration/verify.sh --only agentscope/mcp
```

真实注册中心：

```bash
./integration/verify_e2e.sh --only agentscope/mcp
```

## 进程与组件

本页命令依次启动两个 `scenarios.py` 验证子进程：`--demo mcp` 和
`--demo mcp-agent`，真实模式追加 `--real`。解析 case 只执行
`examples/agentscope/mcp/main.py` 的客户端逻辑，不启动 MCP Server；
Agent case 在同一子进程启动 MCP/Uvicorn 服务、MCP Client 和本地 Agent。
这三个组件不是三个 OS 进程。离线 RegistryStub 同进程运行；真实 Polaris、
Pushgateway 和解析 case 需要的前置 MCP 服务不由验证器拉起。

## 注册服务与实例

- 解析 case 不创建服务或实例。离线 Stub 提供 `offline-mcp` 的固定实例
  `offline-mcp-1`：`127.0.0.1:18080`、protocol `mcp-streamable-http`、
  version `mcp-v1`、健康、weight `100`；metadata 声明协议版本 `2025-06-18`
  与路径 `/mcp`。该地址只是解析 fixture，没有监听进程。
- 真实解析 case 只读 `POLARIS_MCP_SERVICE` 的已有候选实例，至少需 1 个
  健康实例，数量、地址、version 和 TTL 由外部服务决定，不补注册也不删除。
- Agent case 新建 `agentscope-mcp-agent-<20位微秒时间戳>`，真实默认命名空间
  `polaris-python-ai-integration`，其下 1 个实例；host 为本机源 IP
  （离线 `127.0.0.1`），port 为实际动态监听端口，protocol
  `mcp-streamable-http`、version `1.0.0`、TTL `1`。metadata 为
  `mcp-server-name`、`mcp-protocol-version=2025-06-18`、`mcp-endpoint-path=/mcp`
  和 `mcp-scheme=http`。离线仅注册到 Stub。

Agent case 的本地 Agent 不注册 caller 实例。结束时反注册自建 MCP 实例、
关闭 Client/Server/Context；真实服务对象可能保留，前置服务不变。

## 访问与验证链路

1. 解析 case：Consumer Discover 已有 MCP 实例 → 根据实例与 metadata 解析
   `/mcp` URL → 契约 API 获取禁用 Tool 列表。断言候选非空、URL 以 `/mcp`
   结尾、protocol 正确且禁用列表为 list；离线还断言 `disabled_tool`。
   未传 `--connect`，不访问 fixture 的 HTTP 地址，不实际调用 MCP Tool。
2. Agent case：自建 Server 监听 → Provider 注册 → Resolver 发现 → MCP
   初始化、`tools/list` → Agent 经 MCP `tools/call echo_text` 发送
   `hello over MCP` → 断言回复含 `MCP echo: hello over MCP`。
   Tool 调用是本机真实 HTTP，不由 Polaris 代理。

解析 case 真实需要 `POLARIS_MCP_SERVICE`；Agent case 无外部 MCP fixture
依赖。全分组运行需同时满足两者的前置条件。结果保留 `console.log`、
`verification.log`、`result.json` 和 AI mcp 分类日志。
具体自建服务链路见 [MCP Agent 用例](agent/test.md)。
