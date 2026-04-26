# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.2.4] - 2026-04-26

### Added
- **限流自动检测与指数退避重试**：ds_core 在发送流给 adapter 前先消费前两个 SSE 事件，
  检测到 `hint` + `rate_limit_reached` 时返回 `CoreError::Overloaded`，
  `try_chat()` 以 1s→2s→4s→8s→16s 指数间隔自动重试（最多 6 次），session 状态不受污染
- **`stop_stream` 端点集成**：添加 `DsClient::stop_stream()` 方法，在 `GuardedStream` 的
  `PinnedDrop` 中当流被提前丢弃时自动调用，通知 DeepSeek 端停止生成
- **动态 message_id 追踪**：从 SSE `ready` 事件中解析 `request_message_id` 和
  `response_message_id`，支持同一 session 内多次编辑，替代硬编码值
- **SessionInfo 结构**：将 `sessions` 从 `HashMap<String, String>` 升级为
  `RwLock<HashMap<String, SessionInfo>>`，每个 session 独立追踪 `next_message_id`
- **`finished` 标记**：`GuardedStream` 仅在流未自然完成时触发 `stop_stream`，
  正常完成不再发送停止信号
- **工具调用自修复（live model fallback）**：当 tool_calls XML 解析失败时，
  使用 DeepSeek 模型自身修复损坏的 JSON，提升工具调用稳定性
- **e2e 测试按阶段重组**：`smoke` → `protocol` → `tools` → `stress` 渐进式流程，
  支持 `just e2e-smoke` / `e2e-protocol` / `e2e-tools` / `e2e-stress`
- **注册 pytest `requires_server` 标记**：消除自定义 mark 警告

### Changed
- `Account::session_id()` 返回 `Option<String>` 替代 `Option<&str>`，适配内部锁
- 账号分配日志从 `info` 降为 `debug` 级别
- SSE trace 日志精简为单行 `<event> <data>` 格式
- 空内容警告不再误报工具调用场景（`has_tool_calls=true` 时跳过）
- `justfile` 中 e2e 各阶段统一使用 `-n 4` 并发
- 更新中英文 README，增加限流处理与并发策略说明
- 更新 `docs/deepseek-api-reference.md`：添加 `stop_stream` 端点及 message_id 实际模式

### Removed
- 移除 `examples/adapter_cli/` 中冗余的 allow 注释

### Stress Test Results
- **4 账号 + 4 并发**：58 个 e2e 测试全部通过，耗时 83s
- **1 账号 + 1 并发**：指数退避机制下同样 58/58 全部通过（耗时 323s）

## [0.2.3] - 2026-04-24

### Added
- Tool call XML 解析增强：增加 `repair_invalid_backslashes` 与 `repair_unquoted_keys`
  宽松修复，当模型输出的 JSON 包含未引号 key 或无效转义时自动修复后重试
- 增加 `is_inside_code_fence` 检查：跳过 markdown 代码块中的工具示例，防止误解析
- 新增 Anthropic 协议压测脚本 `stress_test_tools_anthropic.py`，与 OpenAI 版对称
- 示例文件正交化：`examples/adapter_cli/` 下按功能拆分为
  `basic_chat`/`stream`/`stop`/`reasoning`/`web_search`/`reasoning_search`/`tool_call` 等独立文件
- 默认 adapter-cli 配置文件路径指向 `py-e2e-tests/config.toml`

### Changed
- 账号池选择策略：从**轮询线性探测**改为**空闲最久优先**，最大化账号复用间隔
- 移除固定的冷却时间常量，选择算法天然避免账号被过快重用
- 同步更新中英文 README，增加并发经验说明

### Stress Test Results

针对 4 账号池的 70 请求压测（7 场景 × 2 模型 × 5 迭代）：

| 策略 | 并发 | 成功率 | 平均耗时 |
|------|------|--------|----------|
| 轮询 + 无冷却 | 3 | 25.7% | 2.57s |
| 轮询 + 2s 冷却 | 3 | 97.1% | 10.46s |
| **空闲最久优先 + 无冷却** | **2** | **100%** | **10.14s** |
| **空闲最久优先 + 无冷却 (Anthropic)** | **2** | **100%** | **11.31s** |

结论：稳定安全并发 ≈ 账号数 ÷ 2，空闲最久优先策略可在不设冷却的前提下实现 100% 成功率。

## [0.2.2] - 2026-04-22

### Added
- Anthropic Messages API 兼容层：
  - `/anthropic/v1/messages` streaming + non-streaming 端点
  - `/anthropic/v1/models` list/get 端点（Anthropic 格式）
  - 请求映射：Anthropic JSON → OpenAI ChatCompletion
  - 响应映射：OpenAI SSE/JSON → Anthropic Message SSE/JSON
- OpenAI adapter 向后兼容：
  - 已弃用的 `functions`/`function_call` 自动映射为 `tools`/`tool_choice`
  - `response_format` 降级：在 ChatML prompt 中注入 JSON/Schema 约束（`text` 类型为 no-op）
- CI 发布流程改进：
  - tag 触发 release（`push.tags v*`）
  - CHANGELOG 自动提取版本说明
  - 发布前校验 Cargo.toml 版本与 tag 一致

### Changed
- Rust toolchain 升级到 1.95.0，CI workflow 同步更新
- justfile 添加 `set positional-arguments`，安全传递带空格的参数
- Python E2E 测试套件重组为 `openai_endpoint/` 和 `anthropic_endpoint/`
- 启动日志显示 OpenAI 和 Anthropic base URLs
- README/README.en.md 添加 SVG 图标、GitHub badges、同步文档
- LICENSE 添加版权声明 `Copyright 2026 NIyueeE`
- CLAUDE.md/AGENTS.md 同步更新

### Fixed
- Anthropic 流式工具调用协议：使用 `input_json_delta` 事件逐步传输工具参数
- Tool use ID 映射一致性：`call_{suffix}` → `toolu_{suffix}`
- Anthropic 工具定义兼容：处理缺少 `type` 字段的情况（Claude Code 客户端）

## [0.2.1] - 2026-04-15

### Added
- 默认开启深度思考：`reasoning_effort` 默认设为 `high`，搜索默认关闭。
- WASM 动态探测：`pow.rs` 改为基于签名的动态 export 探测，不再硬编码 `__wbindgen_export_0`，降低 DeepSeek 更新 WASM 后启动失败的风险。
- 新增 Python E2E 测试套件：覆盖 auth、models、chat completions、tool calling 等场景。
- 新增 `tiktoken-rs` 依赖，用于服务端 prompt token 计算。
- CI 新增 `cargo audit` 与 `cargo machete` 检查。

### Changed
- 账号初始化优化：日志在手机号为空时自动回退显示邮箱。
- 更新 `axum`、`cranelift` 等核心依赖至最新 patch 版本。
- Client Version 保持与网页端一致的 `1.8.0`。

### Removed
- 移除未使用的 `tower` 依赖。

## [0.2.0] - 2026-04-13

### Added
- 项目从 Python 全面重构到 Rust，带来原生高性能和跨平台支持。
- OpenAI 兼容 API（`/v1/chat/completions`、`/v1/models`）。
- 账号池轮转 + PoW 求解 + SSE 流式响应。
- 深度思考和智能搜索支持。
- Tool calling（XML 解析）。
- GitHub CI + 多平台 Release（8 目标平台）。
- 兼容最新 DeepSeek Web 后端接口。
