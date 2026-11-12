# provider 示例

启动 Echo HTTP 端点，注册普通实例并开启自动心跳；退出时反注册和关闭监听器。

```bash
python -m examples.agentscope.a2a.provider.main \
  --address <host>:8091 \
  --service order-agent \
  --host <reachable-ip> \
  --multi-protocol \
  --agent-version 2.1.0
./integration/verify.sh --only agentscope/a2a/provider
```

安装依赖后从项目根目录执行。YAML 启动传
`--config examples/agentscope/polaris.yaml`，纯代码启动传 `--address`。
使用 `--skill-source published --skill-name weather` 或
`--skill-source mounted --skill-service weather-agent` 可暴露无模型且由 Skill
驱动的 Agent，支持 `/skill-list`、`/skill <name>`，其他输入回显。
`make build` 生成 `bin`；`make package` 生成带共享脚手架的
`.build/provider.tar.gz`；`make clean` 清理构建产物。
`--registration-port` 是 Polaris 实例身份端口，不是 AgentCard URL 中的真实监听端口。
`--multi-interface` 在同一监听端口同时暴露 JSONRPC 和 HTTP+JSON 接口，
仍只注册一个 Polaris 实例。
`--multi-protocol` 在同一监听端口暴露三个可调用接口：JSONRPC 1.0
`/a2a/v1`、JSONRPC 0.3 `/a2a/legacy` 和 HTTP+JSON 1.0 `/rest`。三者使用
同一实例 IP，只注册一个实例；GRPC 尚未声明，避免登记不可调用的地址。

验证完成后需要保留该进程时执行：

```bash
./integration/verify_e2e.sh --only agentscope/a2a/provider --retain
./integration/cleanup.sh --dry-run
./integration/cleanup.sh --force
```

`--retain` 会把 Provider 作为独立进程启动并登记 PID；验证成功后进程继续心跳，
直到 cleanup 按记录终止进程。正常退出会反注册实例。

同 IP 部署 v1/v2 并行实例时，需要为两个进程使用不同注册端口，例如
第一个省略参数使用默认端口 `1`，第二个指定 `--registration-port 18080`。注册端口只用于
实例身份和覆盖规则，不改变 AgentCard 中的调用端口。
日志和备份按运行保留；验证条件见 [test.md](/integration/cases/agentscope/a2a/provider/test.md)。
