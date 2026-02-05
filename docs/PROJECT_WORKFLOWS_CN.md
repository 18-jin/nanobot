# nanobot 项目详解（中文）

本文档系统梳理 nanobot 的整体结构与关键工作流程，力求“可追踪到代码”的细致程度。

## 目录
1. 总体架构速览
2. 工作流程 1：初始化（`nanobot onboard`）
3. 工作流程 2：CLI 直接对话（`nanobot agent`）
4. 工作流程 3：Agent 核心循环（最重要）
5. 工作流程 4：上下文与记忆系统
6. 工作流程 5：工具执行系统
7. 工作流程 6：子代理（Subagent）
8. 工作流程 7：Gateway 模式（常驻服务）
9. 工作流程 8：消息总线（Inbound → Agent → Outbound）
10. 工作流程 9：Telegram 通道
11. 工作流程 10：WhatsApp 通道（Node Bridge）
12. 工作流程 11：Feishu 通道
13. 工作流程 12：定时任务 Cron
14. 工作流程 13：Heartbeat 心跳
15. 工作流程 14：配置与持久化
16. 代码细节观察

---

## 1. 总体架构速览
nanobot 是一个极简的“消息总线 + Agent 核心 + 多通道接入 + 工具系统 + 定时/心跳”的框架。

核心模块：
- CLI 命令入口：`nanobot/cli/commands.py`
- Agent 核心循环：`nanobot/agent/loop.py`
- 上下文与记忆：`nanobot/agent/context.py`、`nanobot/agent/memory.py`
- 工具系统：`nanobot/agent/tools/*`
- LLM 适配层（LiteLLM）：`nanobot/providers/litellm_provider.py`
- 消息总线：`nanobot/bus/queue.py`、`nanobot/bus/events.py`
- 会话管理：`nanobot/session/manager.py`
- 通道（Telegram / WhatsApp / Feishu）：`nanobot/channels/*`
- 定时任务与心跳：`nanobot/cron/*`、`nanobot/heartbeat/service.py`
- WhatsApp Node 桥接：`bridge/src/*`

---

## 2. 工作流程 1：初始化（`nanobot onboard`）
入口：`nanobot/cli/commands.py`

流程：
1. CLI 调用 `onboard()`。
2. 检查默认配置路径 `~/.nanobot/config.json`，已有则提示是否覆盖。
3. 生成默认 `Config` 并保存（`nanobot/config/loader.py`）。
4. 创建默认工作区 `~/.nanobot/workspace`（`nanobot/utils/helpers.py`）。
5. 写入工作区模板文件：
   - `AGENTS.md`
   - `SOUL.md`
   - `USER.md`
   - `memory/MEMORY.md`
6. 输出下一步提示（配置 API key、开始聊天）。

代码位置：
- `nanobot/cli/commands.py`
- `nanobot/config/loader.py`
- `nanobot/utils/helpers.py`

---

## 3. 工作流程 2：CLI 直接对话（`nanobot agent`）
入口：`nanobot/cli/commands.py`

流程：
1. 读取配置 `load_config()`。
2. 获取 API key 和模型（`Config.get_api_key()`）。
3. 创建 `MessageBus`、`LiteLLMProvider`、`AgentLoop`。
4. 如果传 `-m`，调用 `AgentLoop.process_direct()` 并输出结果。
5. 未传 `-m` 则进入交互式循环，逐条调用 `process_direct()`。

代码位置：
- `nanobot/cli/commands.py`
- `nanobot/agent/loop.py`
- `nanobot/providers/litellm_provider.py`

---

## 4. 工作流程 3：Agent 核心循环（最重要）
入口：`nanobot/agent/loop.py`

每条消息都会经历完整的“上下文 → LLM → 工具 → 回复”循环：
1. 从 `MessageBus` 取 `InboundMessage`。
2. 根据 `channel:chat_id` 获取或创建会话（`SessionManager`）。
3. `ContextBuilder` 组装系统 prompt：
   - 身份信息 + 当前时间
   - 工作区 bootstrap 文件
   - 记忆（长期 + 今日）
   - 技能（always 技能全文 + 其他技能摘要）
4. 拼接历史消息 + 当前消息。
5. 调用 LLM。
6. 若 LLM 返回 tool calls：
   - 执行工具
   - 将工具结果追加到上下文
   - 继续下一轮
7. 若无 tool calls，生成最终回复。
8. 保存会话（JSONL），输出回复。

代码位置：
- `nanobot/agent/loop.py`
- `nanobot/agent/context.py`
- `nanobot/session/manager.py`

---

## 5. 工作流程 4：上下文与记忆系统
入口：`nanobot/agent/context.py`、`nanobot/agent/memory.py`

流程：
1. 构造系统身份段（包含当前时间、工作区路径等）。
2. 读取工作区 bootstrap 文件：
   - `AGENTS.md`
   - `SOUL.md`
   - `USER.md`
   - `TOOLS.md`（如果存在）
   - `IDENTITY.md`（如果存在）
3. 读取记忆：
   - 长期记忆：`memory/MEMORY.md`
   - 今日笔记：`memory/YYYY-MM-DD.md`
4. 技能系统：
   - always=true 的技能全文载入
   - 其余技能只列摘要，需时再 `read_file` 拉取

代码位置：
- `nanobot/agent/context.py`
- `nanobot/agent/memory.py`
- `nanobot/agent/skills.py`

---

## 6. 工作流程 5：工具执行系统
入口：`nanobot/agent/tools/*`

工具由 `ToolRegistry` 注册，LLM 可直接调用。主要工具：
- 文件工具：`read_file` / `write_file` / `edit_file` / `list_dir`
- Shell 工具：`exec`（带安全 guard）
- Web 工具：`web_search` / `web_fetch`
- 消息工具：`message`
- 子代理：`spawn`

代码位置：
- `nanobot/agent/tools/registry.py`
- `nanobot/agent/tools/filesystem.py`
- `nanobot/agent/tools/shell.py`
- `nanobot/agent/tools/web.py`
- `nanobot/agent/tools/message.py`
- `nanobot/agent/tools/spawn.py`

---

## 7. 工作流程 6：子代理（Subagent）
入口：`nanobot/agent/subagent.py`

流程：
1. 主 Agent 调用 `spawn` 工具。
2. `SubagentManager.spawn()` 异步创建子任务。
3. 子代理具备缩减版工具集（无 message、无 spawn）。
4. 子代理完成后通过 `MessageBus` 注入 `system` 消息。
5. 主 Agent 收到后用原上下文生成摘要回复。

代码位置：
- `nanobot/agent/subagent.py`
- `nanobot/agent/tools/spawn.py`

---

## 8. 工作流程 7：Gateway 模式（常驻服务）
入口：`nanobot/cli/commands.py` -> `gateway()`

流程：
1. 加载配置。
2. 创建 `MessageBus`、`LiteLLMProvider`、`AgentLoop`。
3. 初始化 `CronService` 与 `HeartbeatService`。
4. 初始化 `ChannelManager` 并开启所有通道。
5. 并行运行 `agent.run()` 和 `channels.start_all()`。
6. 退出时优雅停止全部服务。

代码位置：
- `nanobot/cli/commands.py`
- `nanobot/channels/manager.py`
- `nanobot/cron/service.py`
- `nanobot/heartbeat/service.py`

---

## 9. 工作流程 8：消息总线（Inbound → Agent → Outbound）
入口：`nanobot/bus/queue.py`

流程：
1. Channel 收到消息后调用 `_handle_message()`。
2. 构建 `InboundMessage` 推入 `MessageBus.inbound`。
3. `AgentLoop` 消费 inbound 并处理。
4. 处理结果推入 `MessageBus.outbound`。
5. `ChannelManager` 将 outbound 分发到对应通道。

代码位置：
- `nanobot/bus/queue.py`
- `nanobot/bus/events.py`
- `nanobot/channels/manager.py`

---

## 10. 工作流程 9：Telegram 通道
入口：`nanobot/channels/telegram.py`

流程：
1. 使用 python-telegram-bot 长轮询。
2. 收到文本/图片/音频/文件：
   - 下载至 `~/.nanobot/media`
   - 语音可选 Groq Whisper 转写
3. 构造 `InboundMessage` 推入 bus。
4. 回复时将 Markdown 转 Telegram HTML。

代码位置：
- `nanobot/channels/telegram.py`
- `nanobot/providers/transcription.py`

---

## 11. 工作流程 10：WhatsApp 通道（Node Bridge）
入口：`nanobot/channels/whatsapp.py` + `bridge/`

流程：
1. Python 端通过 WebSocket 连接 Node Bridge。
2. Bridge 使用 Baileys 连接 WhatsApp Web。
3. 消息从 Bridge → Python → `InboundMessage`。
4. Python 回复时发送 `send` 命令给 Bridge。

代码位置：
- `nanobot/channels/whatsapp.py`
- `bridge/src/index.ts`
- `bridge/src/server.ts`
- `bridge/src/whatsapp.ts`

---

## 12. 工作流程 11：Feishu 通道
入口：`nanobot/channels/feishu.py`

流程：
1. 使用 lark-oapi WebSocket 长连接。
2. 收到消息后做去重。
3. 自动添加“已读”reaction。
4. 构造 `InboundMessage` 推入 bus。
5. 回复时根据 chat_id 或 open_id 发送。

代码位置：
- `nanobot/channels/feishu.py`

---

## 13. 工作流程 12：定时任务 Cron
入口：`nanobot/cron/service.py`

流程：
1. CLI `cron add` 写入 `~/.nanobot/cron/jobs.json`。
2. Gateway 启动后 `CronService` 加载任务。
3. 计算下一次执行时间。
4. 到点调用 `on_job()`：
   - 由 Agent 处理内容
   - 若 `deliver=True` 则发送到通道

代码位置：
- `nanobot/cron/service.py`
- `nanobot/cron/types.py`
- `nanobot/cli/commands.py`

---

## 14. 工作流程 13：Heartbeat 心跳
入口：`nanobot/heartbeat/service.py`

流程：
1. 每隔 30 分钟读取 `HEARTBEAT.md`。
2. 若无任务，则跳过。
3. 若有任务，调用 Agent 处理固定提示词。
4. 若回复 `HEARTBEAT_OK`，视为无事。

代码位置：
- `nanobot/heartbeat/service.py`

---

## 15. 工作流程 14：配置与持久化
配置位置：`~/.nanobot/config.json`

核心点：
- 读取时 camelCase → snake_case
- `Config.get_api_key()` 按优先级挑选 key
- 会话历史存 `~/.nanobot/sessions/*.jsonl`
- 记忆存 `~/.nanobot/workspace/memory/`

代码位置：
- `nanobot/config/loader.py`
- `nanobot/config/schema.py`
- `nanobot/session/manager.py`

---

## 16. 代码细节观察
这些是代码中值得注意的小细节：
- `nanobot/__init__.py` 中 `__version__ = "0.1.0"`，但 `pyproject.toml` 是 `0.1.3.post4`，CLI `--version` 可能会不一致。

---

如需进一步补充（比如时序图、执行链路图、或按模块做更深的“开发者手册级”说明），告诉我就好。
