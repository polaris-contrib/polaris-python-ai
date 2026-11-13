# Runtime Multi-Agent 测试

```bash
./integration/verify.sh --only agentscope/runtime/multi_agent
./integration/verify_e2e.sh --only agentscope/runtime/multi_agent
```

## 进程与组件

`runner.py` 启动一个 `scenarios.py --demo runtime-multi` 子进程，真实模式
追加 `--real`。子进程调用 `runtime/multi_agent/main.py`，创建一个
PolarisAgentRuntime、一个 Skill loader、共享 Toolkit 和两个本地 Agent
`skill-reader` / `skill-viewer`。Agent 各有对象状态，但不是两个进程或网络服务。
离线 Stub 同进程，真实 Polaris/Skill 服务和 Pushgateway 外部提供。

## 注册服务与实例

不注册任何服务或实例，不启动业务端口；A2A 在此 case 被关闭。
两名 Agent 不对应 Polaris 实例。离线 Skill 为 Stub 的 `weather`；真实为
`POLARIS_SKILL_NAME` 或自动选取的已发布 Skill，默认命名空间
`polaris-python-ai-integration`。只读取和下载，不上传、发布或删除 Skill。

## 访问与验证链路

Runtime 借用 SDKContext → Skill loader 经 Skill RPC 取 ZIP → 动态 middleware
把快照共享给 Toolkit → 第一个 Agent 本地处理 `/skill-list` → 第二个 Agent
本地处理 `/skill <name>`。DemoChatModel 不访问外部模型，也没有两个 Agent
之间的 RPC 或 HTTP 调用。

断言 `agent_count=2`、两个 Agent 共享同一个 Toolkit，第一条回复含 Skill 名称，
第二条以 `<name>\n\n` 开头。当前不做会话串扰或日志隔离的额外故障注入。
最后关闭 Runtime，应用显式销毁借用的 SDKContext，并检查后台线程已停止。
保留 `console.log`、`verification.log`、`result.json` 及 AI base/agentscope/skill 日志。

源码：`integration/scenarios.py::verify_runtime_multi`。
