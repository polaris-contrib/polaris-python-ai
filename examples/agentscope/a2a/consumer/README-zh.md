# consumer 示例

发现 AgentCard 并通过 AgentScope A2AAgent 发送消息，预期回复 Echo: Hello Polaris。

```bash
python -m examples.agentscope.a2a.consumer.main --address <host>:8091 --service echo-agent --message 'Hello Polaris'
make -C examples/agentscope/a2a/consumer verify
```

安装依赖后从项目根目录执行。YAML 启动传
`--config examples/agentscope/polaris.yaml`，纯代码启动传 `--address`。
重复传入 `--message` 即可多轮对话；这些轮次复用同一个原生 A2A 客户端。
`make build` 生成 `bin`；`make package` 生成带共享脚手架的
`.build/consumer.tar.gz`；`make clean` 清理构建产物。
日志和备份按运行保留；验证条件见 [test.md](test.md)。
