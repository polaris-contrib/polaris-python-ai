# A2A State Resume 测试

```bash
./integration/verify.sh --only agentscope/a2a/state_resume
./integration/verify_e2e.sh --only agentscope/a2a/state_resume
```

## 进程与组件

`runner.py` 启动一个 `scenarios.py --demo state-resume` 子进程，真实模式追加
`--real`。子进程中启动 Streaming Provider/Uvicorn 任务和独立 Probe，再顺序
调用 `state_resume/main.py` 两次；每次新建客户端及 SDK Context，但不是启动
两个 OS 进程。离线 RegistryStub 同进程运行，真实 Polaris/Pushgateway 外部提供。

## 注册服务与实例

创建 `agentscope-a2a-state-resume-<20位微秒时间戳>` 服务的 1 个实例。
真实默认命名空间 `polaris-python-ai-integration`，host 为本机连接源 IP
（离线 `127.0.0.1`），port `1`、空 protocol、version `1.0.0`、TTL `1`。
metadata 为 `ai-agent-name`、`ai-agent-card`、`ai-a2a-version=1.0`，卡片的
JSONRPC URL 指向动态业务端口。两次 Consumer 和 Probe 不注册实例；离线
注册仅存在于 Stub，恢复对话不会增加服务或实例。

## 访问与验证链路

Provider 注册 → Probe 等待健康实例 → 第一次客户端发现卡片并发送
`remember first turn` → 保存 `work/a2a-state.json` → 关闭第一次客户端 →
第二次客户端读取同一文件、重新发现并发送 `continue same context`。
两次都按卡片 URL 访问同一个 HTTP Provider，服务端按 context_id 复用 Agent。

断言两次 `context_id` 非空且相同，回复分别含 `first turn` / `same context`，
状态文件存在。当前不模拟客户端进程重启、SIGKILL 或服务端状态恢复。
最后取消 Provider、等待实例反注册并关闭 Context；真实服务对象可能保留。
产物包括状态文件、`console.log`、`verification.log`、`result.json` 和 AI a2a 日志。

源码：`integration/scenarios.py::verify_state_resume`。
