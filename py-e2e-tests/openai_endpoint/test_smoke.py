"""Stage 1 — Smoke: 服务在线、认证、模型列表、基础对话"""

import pytest
from openai import OpenAI, APIError

pytestmark = [pytest.mark.requires_server]


DEFAULT_MODEL = "deepseek-default"
EXPERT_MODEL = "deepseek-expert"


def test_server_online(client):
    """服务可访问"""
    client.models.list(timeout=5)


def test_invalid_token(client):
    """认证拒绝返回 401"""
    bad_client = OpenAI(base_url=client.base_url, api_key="sk-wrong")
    with pytest.raises(APIError) as exc_info:
        bad_client.chat.completions.create(
            model=DEFAULT_MODEL,
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
    assert model.object == "model"


@pytest.mark.parametrize("model", [DEFAULT_MODEL, EXPERT_MODEL], ids=["default", "expert"])
def test_non_stream_basic(client, model):
    """基础非流式对话"""
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "你好，请简单回答"}],
        stream=False,
    )
    assert resp.object == "chat.completion"
    assert resp.model == model
    assert resp.choices[0].message.role == "assistant"
    assert resp.choices[0].message.content
    assert resp.choices[0].finish_reason == "stop"
    assert resp.usage.completion_tokens > 0


@pytest.mark.parametrize("model", [DEFAULT_MODEL, EXPERT_MODEL], ids=["default", "expert"])
def test_stream_basic(client, model):
    """基础流式对话"""
    stream = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "你好，请简单回答"}],
        stream=True,
    )
    chunks = list(stream)
    assert chunks
    content = "".join(
        c.choices[0].delta.content or "" for c in chunks if c.choices
    )
    assert content, f"流式响应为空，chunks: {len(chunks)}"
    assert chunks[-1].choices[0].finish_reason == "stop"
