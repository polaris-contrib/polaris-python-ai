# published 示例

加载已发布 Skill 的 ZIP、说明和资源；可通过 --name 跳过列表，通过 --version 固定版本。

```bash
python -m examples.agentscope.skill.published.main --address <host>:8091 --name weather --version v1
make -C examples/agentscope/skill/published verify
```

安装依赖后从项目根目录执行。YAML 启动传
`--config examples/agentscope/polaris.yaml`，纯代码启动传 `--address`。
`make build` 生成 `bin`；`make package` 生成带共享脚手架的
`.build/published.tar.gz`；`make clean` 清理构建产物。
日志和备份按运行保留；验证条件见 [test.md](test.md)。
