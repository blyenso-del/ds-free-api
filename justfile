# Justfile for ai-free-api

set positional-arguments

# Run all checks: type check, lint, format, audit, unused deps
# 前置: cargo install cargo-audit && cargo install cargo-machete
check:
  cargo check
  cargo clippy -- -D warnings
  cargo fmt --check
  cargo audit
  cargo machete

# Run unified protocol debug CLI (replaces ds-core-cli / openai-adapter-cli)
# 默认使用 py-e2e-tests/config.toml，可通过 -c <path> 覆盖
adapter-cli *ARGS:
  cargo run --example adapter_cli -- -c py-e2e-tests/config.toml "$@"

# Run openai_adapter/request submodule tests
test-adapter-request *ARGS:
  cargo test openai_adapter::request -- "$@"

# Run openai_adapter/response submodule tests
test-adapter-response *ARGS:
  cargo test openai_adapter::response -- "$@"

# Run HTTP server
serve *ARGS:
  cargo run -- "$@"

# Run Python e2e tests (requires server running on port 5317; will skip with hint if not)
# -n 4: 稳定并发（已验证 4 账号 + 指数退避重试可稳定通过）
# 按文件过滤：just e2e openai_endpoint/test_smoke.py
e2e *ARGS:
  cd py-e2e-tests && uv run python -m pytest -n 4 "$@"

# Stage 1 — Smoke: 服务在线、认证、模型列表、基础对话
e2e-smoke:
  cd py-e2e-tests && uv run python -m pytest openai_endpoint/test_smoke.py anthropic_endpoint/test_smoke.py -n 4 -v

# Stage 2 — Protocol: reasoning/search/stop/system/stream/兼容字段
e2e-protocol:
  cd py-e2e-tests && uv run python -m pytest openai_endpoint/test_protocol.py anthropic_endpoint/test_protocol.py -n 4 -v

# Stage 3 — Tools: 工具调用全路径 + 自修复注入
e2e-tools:
  cd py-e2e-tests && uv run python -m pytest openai_endpoint/test_tools.py anthropic_endpoint/test_tools.py -n 4 -v

# Stress: 多场景多轮压测（merge gate，push 前可选）
e2e-stress *ARGS:
  uv run python py-e2e-tests/stress_test_tools_openai.py "$@"
  uv run python py-e2e-tests/stress_test_tools_anthropic.py "$@"

# Full: 所有阶段（pytest + 压测）
e2e-full *ARGS:
  just e2e
  just e2e-stress "$@"

# Start server with e2e test config
e2e-serve:
  cargo run -- -c py-e2e-tests/config.toml
