# OpenClaw ChatGPT OAuth 迁移说明（nanobot）

本文说明：如何让 `nanobot` 复用你已有的 OpenClaw / ChatGPT（OpenAI Codex）登录态来对话。

---

## 1. 背景与核心结论

### 1.1 目标

希望 `nanobot` 不再依赖 OpenAI API Key（`sk-...`），而是复用你已经登录好的 ChatGPT/Codex 账号能力。

### 1.2 为什么不能“直接拿 token 当 apiKey”

我们最初尝试把 OpenClaw 的 OAuth access token 直接塞给 LiteLLM 的 OpenAI provider，结果失败。

原因是两条链路不兼容：

- LiteLLM 的 OpenAI provider 期望的是 OpenAI API Key（`sk-...`）语义。
- OpenClaw 的 `openai-codex` OAuth 实际使用的是 ChatGPT/Codex 登录体系（并非普通 OpenAI API Key 调用路径）。

所以最终采用了**桥接方案**：

> nanobot → 本地 `codex exec` →（Codex CLI 已登录 OAuth）→ 模型

---

## 2. 最终实现架构

```text
nanobot AgentLoop
   └── Provider 选择
       ├── 普通场景: LiteLLMProvider
       └── OpenClaw OAuth 场景: CodexCliProvider（新增）
              └── 调用本地 codex exec
                     └── 使用 codex login 的本地登录态
```

---

## 3. 本次改动点

## 3.1 新增 Provider：`CodexCliProvider`

文件：`nanobot/providers/codex_cli_provider.py`

作用：

- 将消息历史拼成 prompt。
- 异步执行：`codex exec --model ... --output-last-message ... -`
- 从输出文件读取最终回复，转成 `LLMResponse` 返回给 AgentLoop。

关键点：

- 不走 LiteLLM。
- 不依赖 OpenAI API Key。
- 直接复用本机 `codex` CLI 的登录状态。

---

## 3.2 配置模型扩展

文件：`nanobot/config/schema.py`

在 `ProviderConfig` 新增字段：

- `use_openclaw_oauth: bool = False`
- `openclaw_auth_path: str | None = None`
- `use_codex_cli_bridge: bool = False`

含义：

- `use_openclaw_oauth`：启用 OpenClaw OAuth 读取逻辑。
- `openclaw_auth_path`：OpenClaw 的 auth-profiles 文件路径。
- `use_codex_cli_bridge`：启用 Codex CLI 桥接（本方案核心开关）。

---

## 3.3 认证导入命令

文件：`nanobot/cli/commands.py`

新增命令：

```bash
nanobot auth import-openclaw
```

执行后会：

1. 校验 OpenClaw auth 文件是否存在且有 `openai-codex` profile。
2. 写入配置：
   - `providers.openai.useOpenclawOauth = true`
   - `providers.openai.useCodexCliBridge = true`
   - `providers.openai.openclawAuthPath = /config/.openclaw/agents/main/agent/auth-profiles.json`
3. 清空 `providers.openai.apiKey`，避免旧 key 干扰。
4. 默认模型设为 `openai/gpt-5.3-codex`。

---

## 3.4 Provider 选择逻辑调整

文件：`nanobot/cli/commands.py`（`_make_provider`）

新增分支：

- 当 provider 是 `openai` 且开启 `use_openclaw_oauth + use_codex_cli_bridge` 时，直接返回 `CodexCliProvider`。
- 仅在非桥接模式下才走 LiteLLM/OpenAI key 逻辑。

---

## 3.5 文档更新

文件：`README.md`

新增/更新了 OpenClaw OAuth 复用章节，明确说明：

- 该能力会走 `codex exec` 桥接。
- 如果未登录需先执行 `codex login`。

---

## 4. 使用步骤（给操作者）

```bash
# 1) 确保 codex 可用
which codex

# 2) 首次登录（必要时）
codex login

# 3) 导入 OpenClaw OAuth 配置到 nanobot
nanobot auth import-openclaw

# 4) 测试
nanobot agent -m "hello"
```

---

## 5. 故障排查

### 5.1 `Error calling Codex CLI ...`

说明 `codex` 命令不可用或未登录。

处理：

```bash
which codex
codex login
```

### 5.2 仍然走 LiteLLM 报 OpenAI 连接错误

说明桥接开关未生效，检查 `~/.nanobot/config.json`：

```json
{
  "providers": {
    "openai": {
      "useOpenclawOauth": true,
      "useCodexCliBridge": true
    }
  }
}
```

### 5.3 模型权限错误

即使登录成功，不同账号可能对模型有不同可用性。
可临时切为：`openai/gpt-5.1-codex` 进行验证。

---

## 6. 安全与边界

- nanobot 不会在日志中主动打印完整 token。
- OAuth 凭据源头仍在 OpenClaw 的 auth store。
- 桥接执行依赖本机 `codex` CLI，需确保机器环境受信任。

---

## 7. 相关提交

- `57d8407` feat(auth): route OpenClaw OAuth sessions through Codex CLI bridge
- `2da1011` feat(auth): import and reuse OpenClaw openai-codex OAuth in nanobot
- `5bba35d` feat(auth): reload OpenClaw OAuth token dynamically for each request

> 注：前两次提交是探索阶段，最终稳定方案以 `57d8407` 这条桥接路线为准。
