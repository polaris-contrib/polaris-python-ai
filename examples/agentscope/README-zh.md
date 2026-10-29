# AgentScope 示例

支持已发布 Skill、挂载 Skill 和无需模型密钥的 A2A Echo 服务。
依赖安装和统一脚本见 [examples](../README-zh.md)。

`agentscope/a2a/skill` 使用已发布和挂载两种 Skill 运行无模型完整链路：
加载 AgentScope `Agent`，通过 A2A 暴露，发现后完成两轮调用。

`agentscope/mcp` 离线验证 MCP 实例解析和契约过滤。对 MCP 示例增加 `--connect` 后，
会连接真实 MCP Server 并执行 `tools/list`。

```bash
./examples/verify.sh --only agentscope
./examples/verify_e2e.sh --only agentscope
make -C examples/agentscope verify
```

所有示例支持 `--config`、`--address`、`--skill-address`、`--namespace`
和 `--timeout`。不传文件时通过环境变量和代码配置启动；
Skill 地址未显式指定时由 SDK 从普通服务地址推导。
SDK 日志和缓存按运行、组件隔离，关闭扩展不销毁借用的 Context。

手动 A2A Provider 可指定 `--host`、`--port` 和 `--ttl`；未指定 host
时使用连接 Polaris 的本机源 IP。自动心跳复用 ProviderAPI。
Consumer 调用官方 A2AAgent，预期输出 `Echo: Hello Polaris`。
Provider 可用 `--skill-source published|mounted` 切换 Skill 驱动模式，
支持 `/skill-list`、`/skill <name>`，其他输入回显。

已发布 Skill 通过 `--name` 和 `--version` 筛选；挂载 Skill 通过
`--service` 读取服务元数据。临时资源在 loader 关闭时删除。
各目录的 `test.md` 记录验证条件与产物。
