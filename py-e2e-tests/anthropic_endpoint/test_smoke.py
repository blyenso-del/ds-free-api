"""Stage 1 — Smoke: 服务在线、认证、模型列表、基础对话"""

import httpx
import pytest
from anthropic import Anthropic, AuthenticationError

pytestmark = [pytest.mark.requires_server]

DEFAULT_MODEL = "deepseek-default"
EXPERT_MODEL = "deepseek-expert"


def _make_bad_client(base_url: str) -> Anthropic:
    return Anthropic(
        base_url=base_url,
        api_key="sk-wrong",
        http_client=httpx.Client(headers={"Authorization": "Bearer sk-wrong"}),
    )


def test_server_online(client):
    """服务可访问"""
    client.models.list(timeout=5)


def test_invalid_token(client):
    """认证拒绝返回 401"""
    bad_client = _make_bad_client(client.base_url)
    with pytest.raises(AuthenticationError) as exc_info:
        bad_client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": "你好"}],
        )
    assert exc_info.value.status_code == 401


def test_list_models(client):
    """模型列表包含 default 和 expert"""
    models = client.models.list()
    ids = [m.id for m in models.data]
    assert DEFAULT_MODEL in ids
    assert EXPERT_MODEL in ids


def test_get_model(client):
    """查询单个模型"""
    model = client.models.retrieve(DEFAULT_MODEL)
    assert model.id == DEFAULT_MODEL
    assert model.type == "model"


@pytest.mark.parametrize("model", [DEFAULT_MODEL, EXPERT_MODEL], ids=["default", "expert"])
def test_non_stream_basic(client, model):
    """基础非流式对话"""
    msg = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": "你好，请简单回答"}],
    )
    assert msg.type == "message"
    assert msg.role == "assistant"
    assert msg.model == model
    assert msg.content
    assert msg.usage.input_tokens > 0
    assert msg.usage.output_tokens > 0
    assert msg.stop_reason in ("end_turn", "max_tokens")


@pytest.mark.parametrize("model", [DEFAULT_MODEL, EXPERT_MODEL], ids=["default", "expert"])
def test_stream_basic(client, model):
    """基础流式对话"""
    with client.messages.stream(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": "你好，请简单回答"}],
    ) as stream:
        events = list(stream)

    assert events
    assert events[0].type == "message_start"
    assert events[-1].type == "message_stop"

    text_parts = []
    for event in events:
        if event.type == "content_block_delta" and hasattr(event.delta, "text"):
            text_parts.append(event.delta.text)
    assert "".join(text_parts), f"流式响应为空，events: {len(events)}"

    msg_deltas = [e for e in events if e.type == "message_delta"]
    assert len(msg_deltas) == 1
    assert msg_deltas[0].delta.stop_reason in ("end_turn", "max_tokens")
