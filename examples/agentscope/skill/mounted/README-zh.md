# mounted 示例

从服务实例快照中的扩展元数据读取挂载 Skill；挂载版本优先，只读取当前命名空间。

```bash
python -m examples.agentscope.skill.mounted.main --address <host>:8091 --service weather-agent
make -C examples/agentscope/skill/mounted verify
```

安装依赖后从项目根目录执行。YAML 启动传
`--config examples/agentscope/polaris.yaml`，纯代码启动传 `--address`。
`make build` 生成 `bin`；`make package` 生成带共享脚手架的
`.build/mounted.tar.gz`；`make clean` 清理构建产物。
日志和备份按运行保留；验证条件见 [test.md](test.md)。
