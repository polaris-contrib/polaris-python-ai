# 版本管理与发布

## 1. 单一发布包

`polaris-python-ai` 只发布一个 distribution：

```text
distribution: polaris-python-ai
import:       polaris_ai
```

A2A、AgentScope、MCP 和 LangGraph 都是同一个 wheel 中的可选模块，不再发布
`polaris-python-ai-a2a`、`polaris-python-ai-agentscope` 或
`polaris-python-ai-langgraph`。

可选第三方依赖通过 extras 安装：

| extra | 安装内容 |
| --- | --- |
| `a2a` | `polaris_ai.a2a` 所需的 A2A SDK |
| `agentscope` | AgentScope、A2A SDK 和 AgentScope 适配器 |
| `mcp` | AgentScope 和 MCP 依赖 |
| `langgraph` | LangGraph 和 `RemoteGraph` 适配器 |
| `all` | 全部框架适配能力 |

```bash
pip install polaris-python-ai
pip install "polaris-python-ai[a2a]"
pip install "polaris-python-ai[agentscope]"
pip install "polaris-python-ai[mcp]"
pip install "polaris-python-ai[langgraph]"
pip install "polaris-python-ai[all]"
```

基础包导入不会自动加载 AgentScope、A2A SDK 或 LangGraph。只有显式导入对应模块，
或者使用对应的 `async_` 功能时，才需要安装对应 extra。

## 2. 唯一版本源

唯一需要维护的版本文件：

```text
src/polaris_ai/_version.py
```

```python
__version__ = "0.0.1.dev0"
```

`pyproject.toml` 使用 setuptools 动态版本，不保存具体版本号：

```toml
[project]
name = "polaris-python-ai"
dynamic = ["version"]

[tool.setuptools.dynamic]
version = {attr = "polaris_ai._version.__version__"}
```

运行时版本也从同一文件导入：

```python
from polaris_ai._version import __version__
```

A2A、AgentScope 和 LangGraph 子模块的 `__version__` 同样指向这个文件，不维护第二份
版本常量。

## 3. 发布时需要修改哪些文件

### 3.1 普通版本发布

只修改：

```text
src/polaris_ai/_version.py
```

例如发布第一个正式版本 `0.0.1`：

```python
__version__ = "0.0.1"
```

以下文件不需要仅因版本号变化而修改：

- `pyproject.toml`
- 根目录 `README.md`
- `src/polaris_ai/__init__.py`
- `src/polaris_ai/a2a/__init__.py`
- `src/polaris_ai/agentscope/__init__.py`
- `src/polaris_ai/langgraph/__init__.py`
- `uv.lock`

### 3.2 依赖或 extras 变化

如果本次发布修改了 A2A、AgentScope、MCP、LangGraph 依赖，或增加、删除 extra，
还需要修改：

```text
pyproject.toml
uv.lock
```

提交前执行：

```bash
uv lock
uv lock --check
```

不要在 `pyproject.toml` 中增加静态 `project.version`。

## 4. 兼容版本策略

当前项目仍处于 `0.x` 阶段：

- `patch` 用于兼容性修复。
- `minor` 可能包含 breaking change。
- `major` 用于进入稳定期后的不兼容变化。

依赖 `polaris-python` 时使用兼容范围：

```toml
dependencies = ["polaris-python>=0.0.1.dev0,<0.1"]
```

修改依赖下限或上限时，需要同时更新 `pyproject.toml` 和 `uv.lock`。

## 5. 版本格式

版本必须符合 PEP 440。常规发布使用：

```text
X.Y.Z
```

需要使用 PEP 440 预发布或 post release 时可使用：

```text
X.Y.ZaN
X.Y.ZbN
X.Y.ZrcN
X.Y.Z.postN
```

Snapshot 使用：

```text
X.Y.Z.devN
X.Y.ZaN.devM
X.Y.ZrcN.devM
```

PyPI Snapshot 禁止带 local version label：

```text
X.Y.Z.devN+local    # 不允许
```

## 6. Snapshot

Snapshot workflow：

```text
.github/workflows/python-snapshot.yaml
```

触发条件：

- push 到 `main`、`release/*` 或 `develop`。
- 变更包含 `src/**`、`tests/**`、`pyproject.toml`、`uv.lock` 或 Snapshot workflow。
- 也可以在允许分支上手动执行 `workflow_dispatch`。

以下变化单独发生时不触发：

- `src/**.md`
- `tests/**.md`
- 仅 `README`、`docs/**` 或 `examples/**`

即使 workflow 被触发，也只有版本包含 `.dev` 时才构建和发布。

当前首次 Snapshot 的开发基线是：

```python
# src/polaris_ai/_version.py
__version__ = "0.0.1.dev0"
```

workflow 生成：

```text
0.0.1.dev<GITHUB_RUN_NUMBER>
```

例如第 42 次 workflow：

```text
0.0.1.dev42
```

CI 只修改构建工作区，不回写仓库。重跑使用同一个 `GITHUB_RUN_NUMBER`，
PyPI 已存在的文件通过 `skip-existing` 跳过。

如果希望 main 每次合格变更都产生 Snapshot，应让 main 长期维护“下一个未发布版本”
的开发基线：

```text
首次创建项目：
main 设置为 0.0.1.dev0
→ Snapshot 发布 0.0.1.dev<run>
→ 第一次成功后创建 PyPI 项目

正式发布后：
发布 polaris-python-ai==0.0.1
→ main 设置为 0.0.2.dev0
→ 自动发布 0.0.2.dev<run>
→ 正式发布前改为 0.0.2
→ 发布 polaris-python-ai==0.0.2
→ main 再设置为 0.0.3.dev0
```

不能对已经发布的 `0.0.1` 直接生成 `0.0.1.devN`，因为 PEP 440 中
`0.0.1.devN < 0.0.1`。

## 7. Release

Release workflow：

```text
.github/workflows/release.yml
```

Release tag 必须严格使用：

```text
polaris-python-ai==<version>
```

例如：

```text
polaris-python-ai==0.0.1
```

workflow 要求 tag 中的版本与 `src/polaris_ai/_version.py` 完全一致。以下格式不接受：

```text
v0.0.1
0.0.1
polaris-python-ai==0.0.2
```

发布流程：

1. 将 `src/polaris_ai/_version.py` 改为目标正式版本。
2. 如果依赖或 extras 变化，再同步 `pyproject.toml` 和 `uv.lock`。
3. 执行 `uv lock --check`。
4. 构建并安装 wheel。
5. 创建 `polaris-python-ai==<version>` GitHub Release 或手动执行 Release workflow。
6. 验证通过后发布到 PyPI。

## 8. 构建与校验

先构建 sibling `polaris-python`，再构建 AI wheel：

```bash
cd ../polaris-python
uv build

cd ../polaris-python-ai
uv build
```

在干净环境安装后必须满足：

```python
from importlib.metadata import version
import polaris_ai
import polaris_ai.a2a
import polaris_ai.agentscope
import polaris_ai.langgraph

assert version("polaris-python-ai") == polaris_ai.__version__
assert polaris_ai.a2a.__version__ == polaris_ai.__version__
assert polaris_ai.agentscope.__version__ == polaris_ai.__version__
assert polaris_ai.langgraph.__version__ == polaris_ai.__version__
```

Testing workflow 还会验证：

- `uv.lock` 可用。
- wheel metadata 与运行时版本一致。
- 各 extra 能安装对应第三方依赖。
- wheel metadata 不包含本地 editable path。
- 在已安装 wheel 的环境中运行完整测试套件。

## 9. 发布检查清单

- [ ] 只修改了 `src/polaris_ai/_version.py` 的版本号。
- [ ] `pyproject.toml` 没有静态 `project.version`。
- [ ] 所有子模块的 `__version__` 来自同一个文件。
- [ ] 依赖或 extras 变化时已同步 `pyproject.toml` 和 `uv.lock`。
- [ ] `uv lock --check` 通过。
- [ ] wheel metadata 与运行时版本一致。
- [ ] tag 严格等于 `polaris-python-ai==<version>`。
- [ ] 发布的是单个 `polaris-python-ai` distribution。
- [ ] 已发布版本号未被重复使用。
