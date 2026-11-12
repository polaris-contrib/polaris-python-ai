# MCP Agent 测试

```bash
./integration/verify.sh --only agentscope/mcp/agent
./integration/verify_e2e.sh --only agentscope/mcp/agent
```

## 进程与组件

只启动一个 `scenarios.py --demo mcp-agent` 验证子进程，真实追加 `--real`。
其中调用 `examples/agentscope/mcp/agent/main.py`，以异步任务运行 MCP/Uvicorn
Server，再创建 MCP Client、Toolkit 和本地 Agent；这些组件共享进程，不另起
Server 或模型进程。DemoChatModel 不访问外部模型 API。离线 Stub 同进程，
真实 Polaris 与 Pushgateway 外部提供，不依赖 `POLARIS_MCP_SERVICE`。

## 注册服务与实例

新建 `agentscope-mcp-agent-<20位微秒时间戳>`，真实默认命名空间
`polaris-python-ai-integration`，其下 1 个实例：host 为连接 Polaris 的本机
源 IP（离线 `127.0.0.1`），port 是动态 MCP 监听端口，不是 A2A 注册端口 `1`。
protocol `mcp-streamable-http`、version `1.0.0`、TTL `1`；metadata 声明
`mcp-server-name`、`mcp-protocol-version=2025-06-18`、`mcp-endpoint-path=/mcp`、
`mcp-scheme=http`。离线只写 Stub，本地 Agent 不额外注册 caller 服务。

## 访问与验证链路

MCP Server 先监听 → Provider 注册并启动自动心跳 → Resolver 发现健康候选
→ 根据实例 IP、业务端口与 `/mcp` 路径创建 MCP Client → 完成初始化和
`tools/list` → Toolkit 暴露 Tool → Agent 处理 `hello over MCP` 并实际调用
`tools/call echo_text` → MCP Server 返回文本。

验证 protocol、Tool 列表含 `echo_text`、最终回复含
`MCP echo: hello over MCP`。离线额外断言 1 次注册、1 次反注册且 Stub 无残留实例。
`finally` 关闭 Client、反注册、停止 Server 并销毁 Context；本 case 没有独立
的端口 connect 探测断言，监听关闭由关闭流程完成。真实服务对象可能保留。

每次运行保留 `console.log`、`verification.log`、`result.json`、SDK 日志与
`polaris/log/ai/mcp/` 分类日志。

源码：`integration/scenarios.py::verify_mcp_agent`。
