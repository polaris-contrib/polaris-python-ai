# provider 示例

启动 Echo HTTP 端点，注册普通实例并开启自动心跳；退出时反注册和关闭监听器。

```bash
python -m examples.agentscope.a2a.provider.main --address <host>:8091 --service echo-agent --host <reachable-ip>
make -C examples/agentscope/a2a/provider verify
```

安装依赖后从项目根目录执行。YAML 启动传
`--config examples/agentscope/polaris.yaml`，纯代码启动传 `--address`。
使用 `--skill-source published --skill-name weather` 或
`--skill-source mounted --skill-service weather-agent` 可暴露无模型且由 Skill
驱动的 Agent，支持 `/skill-list`、`/skill <name>`，其他输入回显。
`make build` 生成 `bin`；`make package` 生成带共享脚手架的
`.build/provider.tar.gz`；`make clean` 清理构建产物。
日志和备份按运行保留；验证条件见 [test.md](test.md)。
