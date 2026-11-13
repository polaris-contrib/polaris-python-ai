# Skill Console Agent 测试

```bash
./integration/verify.sh --only agentscope/skill/console_agent
./integration/verify_e2e.sh --only agentscope/skill/console_agent
```

## 进程与组件

启动一个 `scenarios.py --demo skill-console` 子进程，真实追加 `--real`。
其中运行 `skill/console_agent/main.py`，创建 Skill loader、Toolkit、动态
middleware 和一个本地 Agent；不启动业务 Server 或独立 Agent 进程。
离线 RegistryStub 同进程，真实 Polaris/Skill 服务与 Pushgateway 外部提供。

## 注册服务与实例

本 case 不注册任何服务或实例，不产生业务 host/port。Agent 名
`polaris-skill-agent` 只是本地对象名。离线读取 Stub 的 `weather`；真实用
`POLARIS_SKILL_NAME` 或自动选择默认命名空间 `polaris-python-ai-integration`
内的已发布 Skill。只读取、下载，不上传、发布或删除资源；默认验证不读取挂载服务。

## 访问与验证链路

验证器选定 Skill → loader 经 Skill RPC 下载 ZIP → middleware 在本地 reply
前读取/复用快照 → Agent 依次处理 `/skill-list`、`/skill <name>` →
DemoChatModel 读取 Skill 名称和正文返回文本，不访问外部模型。

精确断言第一条回复为 Skill 名称，第二条以 `<name>\n\n` 开头。
传入 `--message`，不运行交互 `launch_console`。本 case 不模拟服务端 Skill
更新或断网，不能把通过结果理解为已验证动态版本切换或离线恢复。
结束关闭 loader/Context，保留 `console.log`、`verification.log`、`result.json`
和 AI agentscope/skill 日志。

源码：`integration/scenarios.py::verify_skill_console`。
