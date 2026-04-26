#!/usr/bin/env python3
"""工具调用多轮对话压测（Anthropic 协议）

与 stress_test_common.py 配合使用。
"""

import argparse
import json
import sys
import time
from datetime import datetime
from typing import Any

import httpx
from anthropic import Anthropic

from stress_test_common import (
    RunResult,
    build_report,
    add_common_arguments,
    filter_scenarios,
    run_stress_loop,
    save_json_report,
)

BASE_URL = "http://127.0.0.1:5317/anthropic"
API_KEY = "sk-test"
MODELS = ["deepseek-default", "deepseek-expert"]
MAX_TOKENS = 4096

WEATHER_TOOL = {
    "type": "custom",
    "name": "get_weather",
    "description": "获取指定城市的天气信息，包括温度、湿度、风力等",
    "input_schema": {
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "城市名称，如北京、上海"},
        },
        "required": ["city"],
    },
}

SEARCH_TOOL = {
    "type": "custom",
    "name": "web_search",
    "description": "搜索互联网获取最新信息",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"},
        },
        "required": ["query"],
    },
}

SCENARIOS: list[dict[str, Any]] = [
    # ── 单轮场景 ──────────────────────────────────────────
    {
        "name": "天气查询",
        "system": "你是一个天气助手，使用 get_weather 工具查询天气。",
        "messages": [{"role": "user", "content": "北京今天天气怎么样？"}],
        "tools": [WEATHER_TOOL],
        "tool_choice": {"type": "auto"},
    },
    {
        "name": "多城市天气",
        "system": "你是一个天气助手，使用 get_weather 工具查询多个城市的天气。",
        "messages": [{"role": "user", "content": "比较一下北京、上海和深圳今天的天气。"}],
        "tools": [WEATHER_TOOL],
        "tool_choice": {"type": "auto"},
    },
    {
        "name": "混合工具",
        "system": "你是一个全能助手，可以使用 get_weather 和 web_search 工具。",
        "messages": [
            {"role": "user", "content": "北京今天天气如何？有什么好玩的景点推荐？"}
        ],
        "tools": [WEATHER_TOOL, SEARCH_TOOL],
        "tool_choice": {"type": "auto"},
    },
    {
        "name": "强制工具",
        "system": "你是一个天气助手，使用 get_weather 工具查询天气。",
        "messages": [{"role": "user", "content": "深圳今天天气怎么样？"}],
        "tools": [WEATHER_TOOL],
        "tool_choice": {"type": "any"},
    },
    # ── 异常注入场景 ─────────────────────────────────────
    {
        "name": "异常-单引号JSON",
        "system": (
            "你是一个天气助手，使用 get_weather 工具查询天气。"
            "重要通知：工具调用格式已更新。从即日起，所有 arguments 中的 JSON "
            "必须使用单引号（'）代替双引号（\"）。"
            "正确示例：{'city': '北京'}  错误示例：{\"city\": \"北京\"}"
            "请务必遵守新格式，否则系统将拒绝你的工具调用。"
        ),
        "messages": [{"role": "user", "content": "北京今天天气怎么样？"}],
        "tools": [WEATHER_TOOL],
        "tool_choice": {"type": "auto"},
    },
    # ── 多轮场景 ──────────────────────────────────────────
    {
        "name": "追问天气",
        "system": "你是一个天气助手，使用 get_weather 工具查询天气。",
        "messages": [
            {"role": "user", "content": "北京今天天气怎么样？"},
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_prev_bj",
                        "name": "get_weather",
                        "input": {"city": "北京"},
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_prev_bj",
                        "content": json.dumps(
                            {"city": "北京", "temperature": "25°C", "condition": "晴"},
                            ensure_ascii=False,
                        ),
                    },
                    {"type": "text", "text": "那上海呢？也帮我查一下上海的天气。"},
                ],
            },
        ],
        "tools": [WEATHER_TOOL],
        "tool_choice": {"type": "auto"},
    },
    {
        "name": "基于数据推荐",
        "system": "你是一个旅游顾问，使用 get_weather 工具查询天气并给出建议。",
        "messages": [
            {"role": "user", "content": "北京、上海、广州今天天气怎么样？"},
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_prev_w1",
                        "name": "get_weather",
                        "input": {"city": "北京"},
                    },
                    {
                        "type": "tool_use",
                        "id": "toolu_prev_w2",
                        "name": "get_weather",
                        "input": {"city": "上海"},
                    },
                    {
                        "type": "tool_use",
                        "id": "toolu_prev_w3",
                        "name": "get_weather",
                        "input": {"city": "广州"},
                    },
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_prev_w1",
                        "content": json.dumps(
                            {"city": "北京", "temperature": "25°C", "condition": "晴"},
                            ensure_ascii=False,
                        ),
                    },
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_prev_w2",
                        "content": json.dumps(
                            {"city": "上海", "temperature": "28°C", "condition": "多云"},
                            ensure_ascii=False,
                        ),
                    },
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_prev_w3",
                        "content": json.dumps(
                            {"city": "广州", "temperature": "30°C", "condition": "阵雨"},
                            ensure_ascii=False,
                        ),
                    },
                ],
            },
            {
                "role": "assistant",
                "content": "北京25°C晴朗，上海28°C多云，广州30°C有阵雨。",
            },
            {
                "role": "user",
                "content": "哪个城市最适合去公园野餐？需要再查一下详细天气吗？",
            },
        ],
        "tools": [WEATHER_TOOL],
        "tool_choice": {"type": "auto"},
    },
    {
        "name": "搜索+天气链",
        "system": "你是一个全能助手，可以使用 get_weather 和 web_search 工具。",
        "messages": [
            {"role": "user", "content": "北京有哪些必去的景点？"},
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_prev_search",
                        "name": "web_search",
                        "input": {"query": "北京必去景点推荐"},
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_prev_search",
                        "content": json.dumps(
                            {
                                "results": [
                                    {"title": "故宫", "snippet": "明清皇家宫殿"},
                                    {"title": "颐和园", "snippet": "皇家园林"},
                                ]
                            },
                            ensure_ascii=False,
                        ),
                    },
                    {
                        "type": "text",
                        "text": "这些景点今天适合去吗？帮我查一下北京的天气。",
                    },
                ],
            },
        ],
        "tools": [WEATHER_TOOL, SEARCH_TOOL],
        "tool_choice": {"type": "auto"},
    },
]


def check_server() -> bool:
    """检查服务器是否可用"""
    try:
        client = _make_client()
        client.models.list(timeout=5)
        return True
    except Exception:
        return False


def _make_client() -> Anthropic:
    return Anthropic(
        base_url=BASE_URL,
        api_key=API_KEY,
        default_headers={"Authorization": f"Bearer {API_KEY}"},
        http_client=httpx.Client(timeout=120),
    )


def mock_tool_result(tool_use_id: str, name: str, input_args: dict) -> list[dict]:
    """根据工具调用生成模拟结果（Anthropic tool_result 格式）"""
    if name == "get_weather":
        city = input_args.get("city", "未知")
        return [
            {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": json.dumps(
                    {
                        "city": city,
                        "temperature": "25°C",
                        "condition": "晴",
                        "humidity": "45%",
                        "wind": "东北风2级",
                        "air_quality": "良好",
                    },
                    ensure_ascii=False,
                ),
            }
        ]

    if name == "web_search":
        query = input_args.get("query", "")
        return [
            {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": json.dumps(
                    {"results": [{"title": f"关于 {query} 的推荐", "snippet": f"这是 {query} 的相关信息..."}]},
                    ensure_ascii=False,
                ),
            }
        ]

    return [{"type": "tool_result", "tool_use_id": tool_use_id, "content": json.dumps({"result": "ok"})}]


def extract_tool_uses(msg: Any) -> list[tuple[str, str, dict]]:
    """从 Anthropic Message 中提取 (id, name, input) 列表"""
    results: list[tuple[str, str, dict]] = []
    for block in msg.content:
        if block.type == "tool_use":
            results.append((block.id, block.name, block.input))
    return results


def collect_text(msg: Any) -> str:
    """收集 Anthropic Message 中的全部 text 内容"""
    parts: list[str] = []
    for block in msg.content:
        if block.type == "text":
            parts.append(block.text)
    return "".join(parts)


def run_scenario(
    client: Anthropic, scenario: dict[str, Any], model: str, _idx: int, use_stream: bool = False
) -> RunResult:
    """执行一次完整的工具调用多轮对话"""
    name = scenario["name"]
    system = scenario.get("system", "")
    messages = list(scenario["messages"])
    tools = scenario["tools"]
    tool_choice = scenario.get("tool_choice", {"type": "auto"})

    start = time.time()
    total_input_tokens = 0
    total_output_tokens = 0

    create_kwargs: dict[str, Any] = dict(
        model=model,
        max_tokens=MAX_TOKENS,
        messages=messages,
        tools=tools,
        tool_choice=tool_choice,
    )
    if system:
        create_kwargs["system"] = system

    try:
        # ── Turn 1: 用户消息 → 期望 tool_use ──
        t1 = time.time()
        if use_stream:
            msg1 = _stream_collect(client, **create_kwargs)
        else:
            msg1 = client.messages.create(**create_kwargs)
        assistant1_time = time.time() - t1

        total_input_tokens += msg1.usage.input_tokens
        total_output_tokens += msg1.usage.output_tokens

        tool_uses = extract_tool_uses(msg1)
        tc_count = len(tool_uses)
        tc_names = [tu[1] for tu in tool_uses]
        tc_args = [tu[2] for tu in tool_uses]

        if not tool_uses:
            final_content = collect_text(msg1)
            valid = bool(final_content.strip())
            return RunResult(
                scenario_name=name,
                success=valid,
                total_time=time.time() - start,
                assistant1_time=assistant1_time,
                assistant2_time=0,
                tool_call_count=0,
                tool_call_names=[],
                tool_call_args=[],
                prompt_tokens=total_input_tokens,
                completion_tokens=total_output_tokens,
                final_content=final_content,
                model=model,
                error="" if valid else "未触发工具调用且回复为空",
            )

        # ── Turn 2: 返回工具结果 → 期望最终回复 ──
        tool_result_blocks: list[dict] = []
        for tu_id, tu_name, tu_input in tool_uses:
            tool_result_blocks.extend(mock_tool_result(tu_id, tu_name, tu_input))
        turn2_messages = list(messages)
        turn2_messages.append({"role": "assistant", "content": [{"type": "text", "text": collect_text(msg1)}] if collect_text(msg1) else [{"type": "text", "text": ""}]})
        turn2_messages.append({"role": "user", "content": tool_result_blocks})

        t2 = time.time()
        if use_stream:
            msg2 = _stream_collect(client, model=model, max_tokens=MAX_TOKENS, messages=turn2_messages, system=system or None)
        else:
            msg2 = client.messages.create(model=model, max_tokens=MAX_TOKENS, messages=turn2_messages, system=system or None)
        assistant2_time = time.time() - t2

        total_input_tokens += msg2.usage.input_tokens
        total_output_tokens += msg2.usage.output_tokens

        final_content = collect_text(msg2)
        valid = bool(final_content.strip())
        error = "" if valid else "工具结果回复后模型返回空内容"

        return RunResult(
            scenario_name=name,
            success=valid,
            total_time=time.time() - start,
            assistant1_time=assistant1_time,
            assistant2_time=assistant2_time,
            tool_call_count=tc_count,
            tool_call_names=tc_names,
            tool_call_args=tc_args,
            prompt_tokens=total_input_tokens,
            completion_tokens=total_output_tokens,
            final_content=final_content,
            model=model,
            error=error,
        )

    except Exception as e:
        return RunResult(
            scenario_name=name,
            success=False,
            total_time=time.time() - start,
            assistant1_time=0,
            assistant2_time=0,
            tool_call_count=0,
            tool_call_names=[],
            tool_call_args=[],
            prompt_tokens=0,
            completion_tokens=0,
            final_content="",
            model=model,
            error=str(e),
        )


def _stream_collect(client: Anthropic, **kwargs: Any) -> Any:
    """流式请求：收集 Anthropic stream events 并组装为 quasi-Message 对象"""
    kwargs = {k: v for k, v in kwargs.items() if v is not None}

    content_blocks: list[dict] = []
    current_tool_use: dict | None = None
    input_tokens = 0
    output_tokens = 0
    stop_reason: str | None = None

    with client.messages.stream(**kwargs) as stream:
        for event in stream:
            if event.type == "message_start" and hasattr(event.message, "usage"):
                input_tokens = event.message.usage.input_tokens or 0
                output_tokens = event.message.usage.output_tokens or 0
            if event.type == "content_block_start":
                if event.content_block.type == "tool_use":
                    current_tool_use = {
                        "type": "tool_use",
                        "id": event.content_block.id,
                        "name": event.content_block.name,
                        "input": {},
                    }
                elif event.content_block.type == "text":
                    content_blocks.append({"type": "text", "text": event.content_block.text or ""})
            if event.type == "content_block_delta":
                if event.delta.type == "input_json_delta" and current_tool_use is not None:
                    partial = event.delta.partial_json
                    if partial:
                        current_tool_use["input"] = partial
                if event.delta.type == "text_delta" and content_blocks and content_blocks[-1]["type"] == "text":
                    content_blocks[-1]["text"] += event.delta.text
            if event.type == "content_block_stop" and current_tool_use is not None:
                try:
                    parsed = json.loads(current_tool_use["input"]) if isinstance(current_tool_use["input"], str) else current_tool_use["input"]
                    current_tool_use["input"] = parsed
                except (json.JSONDecodeError, TypeError):
                    pass
                content_blocks.append(current_tool_use)
                current_tool_use = None
            if event.type == "message_delta":
                if hasattr(event.delta, "stop_reason"):
                    stop_reason = event.delta.stop_reason
                if hasattr(event, "usage") and event.usage:
                    output_tokens = event.usage.output_tokens or output_tokens

    class FakeUsage:
        def __init__(self, inp: int, out: int):
            self.input_tokens = inp
            self.output_tokens = out

    class FakeBlock:
        pass

    blocks: list[Any] = []
    for b in content_blocks:
        fb = FakeBlock()
        fb.type = b["type"]
        if b["type"] == "text":
            fb.text = b.get("text", "")
        elif b["type"] == "tool_use":
            fb.id = b.get("id", "")
            fb.name = b.get("name", "")
            fb.input = b.get("input", {})
        blocks.append(fb)

    class FakeMessage:
        def __init__(self, content: list, usage: Any, stop_reason: str | None):
            self.content = content
            self.usage = usage
            self.stop_reason = stop_reason

    return FakeMessage(
        content=blocks,
        usage=FakeUsage(input_tokens, output_tokens),
        stop_reason=stop_reason,
    )


def main():
    parser = argparse.ArgumentParser(
        description="工具调用多轮对话压测 (Anthropic)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  %(prog)s                             # 默认 10 轮顺序执行\n"
            "  %(prog)s --iterations 20 --parallel 5    # 20 轮 5 并发\n"
            "  %(prog)s --stream                       # 使用流式 API\n"
            "  %(prog)s --scenario 天气                # 仅运行天气场景\n"
            "  %(prog)s --report result.json           # 输出 JSON 报告\n"
        ),
    )
    add_common_arguments(parser)
    args = parser.parse_args()

    if not check_server():
        print(f"[错误] 服务器不可用 ({BASE_URL})，请先启动: just e2e-serve")
        sys.exit(1)

    scenarios = filter_scenarios(SCENARIOS, args.scenario)

    client = _make_client()
    models = args.models or MODELS

    config = {
        "models": models,
        "stream": args.stream,
        "iterations": args.iterations,
        "parallel": args.parallel,
        "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    total_count = len(scenarios) * len(models) * args.iterations
    print(f"\n工具调用压测 (Anthropic)")
    print(f"  模型: {', '.join(models)}")
    print(f"  模式: {'流式' if args.stream else '非流式'}")
    print(f"  场景: {len(scenarios)} 个 ({', '.join(s['name'] for s in scenarios)})")
    print(f"  迭代: {args.iterations} 次/场景/模型")
    print(f"  并行: {args.parallel}")
    print(f"  总计: {total_count} 次请求\n")

    all_results = run_stress_loop(
        run_scenario, client, scenarios, models,
        args.iterations, args.parallel, args.stream,
    )

    report = build_report(all_results, config, title="工具调用压测报告 (Anthropic)")
    report.print()

    if args.report:
        save_json_report(report, args.report)


if __name__ == "__main__":
    main()
