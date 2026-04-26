#!/usr/bin/env python3
"""工具调用多轮对话压测（OpenAI 协议）

与 stress_test_common.py 配合使用。
"""

import argparse
import json
import sys
import time
from datetime import datetime
from typing import Any

from openai import OpenAI

from stress_test_common import (
    RunResult,
    build_report,
    add_common_arguments,
    filter_scenarios,
    run_stress_loop,
    save_json_report,
)

BASE_URL = "http://127.0.0.1:5317/v1"
API_KEY = "sk-test"
MODELS = ["deepseek-default", "deepseek-expert"]

WEATHER_TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "获取指定城市的天气信息，包括温度、湿度、风力等",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "城市名称，如北京、上海"},
            },
            "required": ["city"],
        },
    },
}

SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "搜索互联网获取最新信息",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
            },
            "required": ["query"],
        },
    },
}

SCENARIOS: list[dict[str, Any]] = [
    # ── 单轮场景 ──────────────────────────────────────────
    {
        "name": "天气查询",
        "system": "你是一个天气助手，使用 get_weather 工具查询天气。",
        "messages": [{"role": "user", "content": "北京今天天气怎么样？"}],
        "tools": [WEATHER_TOOL],
        "tool_choice": "auto",
    },
    {
        "name": "多城市天气",
        "system": "你是一个天气助手，使用 get_weather 工具查询多个城市的天气。",
        "messages": [{"role": "user", "content": "比较一下北京、上海和深圳今天的天气。"}],
        "tools": [WEATHER_TOOL],
        "tool_choice": "auto",
    },
    {
        "name": "混合工具",
        "system": "你是一个全能助手，可以使用 get_weather 和 web_search 工具。",
        "messages": [
            {"role": "user", "content": "北京今天天气如何？有什么好玩的景点推荐？"}
        ],
        "tools": [WEATHER_TOOL, SEARCH_TOOL],
        "tool_choice": "auto",
    },
    {
        "name": "强制工具",
        "system": "你是一个天气助手，使用 get_weather 工具查询天气。",
        "messages": [{"role": "user", "content": "深圳今天天气怎么样？"}],
        "tools": [WEATHER_TOOL],
        "tool_choice": "required",
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
        "tool_choice": "auto",
    },
    # ── 多轮场景 ──────────────────────────────────────────
    {
        "name": "追问天气",
        "system": "你是一个天气助手，使用 get_weather 工具查询天气。",
        "messages": [
            {"role": "user", "content": "北京今天天气怎么样？"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_prev_weather_bj",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": '{"city": "北京"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_prev_weather_bj",
                "content": json.dumps(
                    {"city": "北京", "temperature": "25°C", "condition": "晴"},
                    ensure_ascii=False,
                ),
            },
            {
                "role": "assistant",
                "content": "北京今天天气晴朗，气温25°C，湿度45%，适合外出活动。",
            },
            {"role": "user", "content": "那上海呢？也帮我查一下上海的天气。"},
        ],
        "tools": [WEATHER_TOOL],
        "tool_choice": "auto",
    },
    {
        "name": "基于数据推荐",
        "system": "你是一个旅游顾问，使用 get_weather 工具查询天气并给出建议。",
        "messages": [
            {"role": "user", "content": "北京、上海、广州今天天气怎么样？"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_prev_w1",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": '{"city": "北京"}',
                        },
                    },
                    {
                        "id": "call_prev_w2",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": '{"city": "上海"}',
                        },
                    },
                    {
                        "id": "call_prev_w3",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": '{"city": "广州"}',
                        },
                    },
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_prev_w1",
                "content": json.dumps(
                    {"city": "北京", "temperature": "25°C", "condition": "晴"},
                    ensure_ascii=False,
                ),
            },
            {
                "role": "tool",
                "tool_call_id": "call_prev_w2",
                "content": json.dumps(
                    {"city": "上海", "temperature": "28°C", "condition": "多云"},
                    ensure_ascii=False,
                ),
            },
            {
                "role": "tool",
                "tool_call_id": "call_prev_w3",
                "content": json.dumps(
                    {"city": "广州", "temperature": "30°C", "condition": "阵雨"},
                    ensure_ascii=False,
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "北京25°C晴朗，上海28°C多云，广州30°C有阵雨。"
                    "北京和上海更适合户外活动。"
                ),
            },
            {"role": "user", "content": "哪个城市最适合去公园野餐？需要再查一下详细天气吗？"},
        ],
        "tools": [WEATHER_TOOL],
        "tool_choice": "auto",
    },
    {
        "name": "搜索+天气链",
        "system": "你是一个全能助手，可以使用 get_weather 和 web_search 工具。",
        "messages": [
            {"role": "user", "content": "北京有哪些必去的景点？"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_prev_search",
                        "type": "function",
                        "function": {
                            "name": "web_search",
                            "arguments": '{"query": "北京必去景点推荐"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_prev_search",
                "content": json.dumps(
                    {
                        "results": [
                            {"title": "故宫", "snippet": "明清两代的皇家宫殿"},
                            {"title": "颐和园", "snippet": "皇家园林博物馆"},
                        ]
                    },
                    ensure_ascii=False,
                ),
            },
            {
                "role": "assistant",
                "content": "北京必去的景点包括故宫、颐和园和长城。",
            },
            {"role": "user", "content": "这些景点今天适合去吗？帮我查一下北京的天气。"},
        ],
        "tools": [WEATHER_TOOL, SEARCH_TOOL],
        "tool_choice": "auto",
    },
]


def check_server() -> bool:
    """检查服务器是否可用"""
    try:
        client = OpenAI(base_url=BASE_URL, api_key=API_KEY)
        client.models.list(timeout=5)
        return True
    except Exception:
        return False


def mock_tool_result(tool_call: Any) -> str:
    """根据工具调用的 name 和参数生成模拟结果"""
    name = tool_call.function.name
    try:
        args = json.loads(tool_call.function.arguments)
    except json.JSONDecodeError:
        args = {}

    if name == "get_weather":
        city = args.get("city", "未知")
        return json.dumps(
            {
                "city": city,
                "temperature": "25°C",
                "condition": "晴",
                "humidity": "45%",
                "wind": "东北风2级",
                "air_quality": "良好",
            },
            ensure_ascii=False,
        )

    if name == "web_search":
        query = args.get("query", "")
        return json.dumps(
            {
                "results": [
                    {
                        "title": f"关于 {query} 的推荐",
                        "snippet": f"这是 {query} 的相关信息...",
                    }
                ]
            },
            ensure_ascii=False,
        )

    return json.dumps({"result": "ok"})


def make_tool_results_messages(tool_calls: list[Any]) -> list[dict]:
    """构造 tool_results 消息列表"""
    return [
        {"role": "tool", "tool_call_id": tc.id, "content": mock_tool_result(tc)}
        for tc in tool_calls
    ]


def run_scenario(
    client: OpenAI, scenario: dict[str, Any], model: str, _idx: int, use_stream: bool = False
) -> RunResult:
    """执行一次完整的工具调用多轮对话"""
    name = scenario["name"]
    system = scenario.get("system", "")
    messages = list(scenario["messages"])
    tools = scenario["tools"]
    tool_choice = scenario.get("tool_choice", "auto")
    create_kwargs: dict[str, Any] = dict(
        model=model,
        messages=(
            [{"role": "system", "content": system}, *messages] if system else messages
        ),
        tools=tools,
        tool_choice=tool_choice,
        temperature=0.7,
        stream=False,
    )

    start = time.time()
    total_prompt = 0
    total_completion = 0

    try:
        # ── Turn 1: 用户消息 → 期望 tool_calls ──
        t1 = time.time()
        if use_stream:
            resp1 = _stream_collect(client, **create_kwargs)
        else:
            resp1 = client.chat.completions.create(**create_kwargs)
        assistant1_time = time.time() - t1

        if resp1.usage:
            total_prompt += resp1.usage.prompt_tokens or 0
            total_completion += resp1.usage.completion_tokens or 0

        choice1 = resp1.choices[0]
        msg1 = choice1.message
        tool_calls = msg1.tool_calls or []
        tc_count = len(tool_calls)
        tc_names = [tc.function.name for tc in tool_calls]
        tc_args = [
            json.loads(tc.function.arguments) if tc.function.arguments else {}
            for tc in tool_calls
        ]

        if not tool_calls:
            final_content = msg1.content or ""
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
                prompt_tokens=total_prompt,
                completion_tokens=total_completion,
                final_content=final_content,
                model=model,
                error="" if valid else "未触发工具调用且回复为空",
            )

        # ── Turn 2: 返回工具结果 → 期望最终回复 ──
        turn2_msgs = list(create_kwargs["messages"])
        turn2_msgs.append(msg1.model_dump())
        turn2_msgs.extend(make_tool_results_messages(tool_calls))

        t2 = time.time()
        if use_stream:
            resp2 = _stream_collect(client, model=model, messages=turn2_msgs, temperature=0.7)
        else:
            resp2 = client.chat.completions.create(
                model=model, messages=turn2_msgs, temperature=0.7, stream=False
            )
        assistant2_time = time.time() - t2

        if resp2.usage:
            total_prompt += resp2.usage.prompt_tokens or 0
            total_completion += resp2.usage.completion_tokens or 0

        final_content = resp2.choices[0].message.content or ""
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
            prompt_tokens=total_prompt,
            completion_tokens=total_completion,
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


def _stream_collect(client: OpenAI, **kwargs: Any) -> Any:
    """流式请求：收集所有 chunks 并组装为 quasi-Response 对象"""
    stream = client.chat.completions.create(**{**kwargs, "stream": True})

    content_parts: list[str] = []
    tool_call_acc: dict[int, dict] = {}
    finish_reason: str | None = None
    usage: Any = None
    msg_role: str = "assistant"

    for chunk in stream:
        if chunk.usage:
            usage = chunk.usage
        if not chunk.choices:
            continue
        choice = chunk.choices[0]
        if choice.finish_reason:
            finish_reason = choice.finish_reason
        if choice.delta.role:
            msg_role = choice.delta.role
        if choice.delta.content:
            content_parts.append(choice.delta.content)
        if choice.delta.tool_calls:
            for tc in choice.delta.tool_calls:
                idx = tc.index
                if idx not in tool_call_acc:
                    tool_call_acc[idx] = {
                        "index": idx,
                        "id": tc.id or "",
                        "type": "function",
                        "function": {"name": "", "arguments": ""},
                    }
                if tc.id:
                    tool_call_acc[idx]["id"] = tc.id
                if tc.function:
                    if tc.function.name:
                        tool_call_acc[idx]["function"]["name"] += tc.function.name
                    if tc.function.arguments:
                        tool_call_acc[idx]["function"]["arguments"] += tc.function.arguments

    tool_calls_list = sorted(tool_call_acc.values(), key=lambda x: x["index"])

    class FakeUsage:
        def __init__(self, u: Any) -> None:
            self.prompt_tokens = u.prompt_tokens or 0 if u is not None else 0
            self.completion_tokens = u.completion_tokens or 0 if u is not None else 0

    class FakeMessage:
        def __init__(self, content: str | None, tool_calls: list[Any], role: str):
            self.content = content
            self.tool_calls = tool_calls
            self.role = role

        def model_dump(self) -> dict:
            d: dict[str, Any] = {"role": self.role, "content": self.content}
            if self.tool_calls:
                d["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": tc.get("type", "function"),
                        "function": {
                            "name": tc["function"]["name"],
                            "arguments": tc["function"]["arguments"],
                        },
                    }
                    for tc in self.tool_calls
                ]
            return d

    class FakeChoice:
        def __init__(self, finish: str | None, content: str | None, tool_calls: list[Any], role: str):
            self.finish_reason = finish
            self.message = FakeMessage(content, tool_calls, role)

    class FakeResponse:
        def __init__(self, choices: list[FakeChoice], usage: Any):
            self.choices = choices
            self.usage = FakeUsage(usage)

    content = "".join(content_parts) or None
    return FakeResponse(
        choices=[FakeChoice(finish_reason, content, tool_calls_list, msg_role)],
        usage=usage,
    )


def main():
    parser = argparse.ArgumentParser(
        description="工具调用多轮对话压测 (OpenAI)",
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
    parser.add_argument(
        "--tool-choice",
        type=str,
        default=None,
        choices=["auto", "required", "none"],
        help="覆盖所有场景的 tool_choice",
    )
    args = parser.parse_args()

    if not check_server():
        print(f"[错误] 服务器不可用 ({BASE_URL})，请先启动: just e2e-serve")
        sys.exit(1)

    scenarios = filter_scenarios(SCENARIOS, args.scenario)
    if args.tool_choice:
        for s in scenarios:
            s["tool_choice"] = args.tool_choice

    client = OpenAI(base_url=BASE_URL, api_key=API_KEY)
    models = args.models or MODELS

    config = {
        "models": models,
        "stream": args.stream,
        "iterations": args.iterations,
        "parallel": args.parallel,
        "scenario_filter": args.scenario or "all",
        "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    total_count = len(scenarios) * len(models) * args.iterations
    print(f"\n工具调用压测 (OpenAI)")
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

    report = build_report(all_results, config, title="工具调用压测报告 (OpenAI)")
    report.print()

    if args.report:
        save_json_report(report, args.report)


if __name__ == "__main__":
    main()
