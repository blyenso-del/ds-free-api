"""压测公共模块：数据类型、报告构建、CLI 参数"""

import argparse
import statistics
from dataclasses import dataclass
from datetime import datetime
from typing import Any


DEFAULT_ITERATIONS = 10
DEFAULT_PARALLEL = 1


@dataclass
class RunResult:
    """单轮压测结果"""

    scenario_name: str
    success: bool
    total_time: float
    assistant1_time: float
    assistant2_time: float
    tool_call_count: int
    tool_call_names: list[str]
    tool_call_args: list[dict]
    prompt_tokens: int
    completion_tokens: int
    final_content: str
    model: str = ""
    error: str = ""


@dataclass
class ScenarioStats:
    """单个场景统计"""

    name: str
    total: int
    success: int
    tool_triggered: int
    total_time: list[float]
    tool_calls_per_run: list[int]


@dataclass
class Report:
    """压测总报告"""

    scenarios: dict[str, ScenarioStats]
    all_results: list[RunResult]
    start_time: str
    end_time: str
    config: dict
    title: str = "工具调用压测报告"

    @property
    def total(self) -> int:
        return len(self.all_results)

    @property
    def success(self) -> int:
        return sum(1 for r in self.all_results if r.success)

    @property
    def failed(self) -> int:
        return self.total - self.success

    def print(self):
        rate = self.success / self.total * 100 if self.total else 0
        all_times = [r.total_time for r in self.all_results]
        success_times = [r.total_time for r in self.all_results if r.success]
        all_tokens = [
            r.completion_tokens for r in self.all_results if r.completion_tokens > 0
        ]
        tool_call_counts = [r.tool_call_count for r in self.all_results]

        print(f"\n{'=' * 64}")
        print(f"  {self.title}")
        print(f"  开始: {self.start_time}")
        print(f"  结束: {self.end_time}")
        print(f"  模型: {', '.join(self.config.get('models', ['?']))}")
        print(f"{'=' * 64}")
        print(f"  总运行:          {self.total}")
        print(f"  成功:            {self.success} ({rate:.1f}%)")
        print(f"  失败:            {self.failed}")
        print(f"  触发工具调用:    {sum(1 for r in self.all_results if r.tool_call_count > 0)}")
        if success_times:
            print(f"  成功平均耗时:     {statistics.mean(success_times):.2f}s")
        if all_times:
            print(f"  总平均耗时:       {statistics.mean(all_times):.2f}s")
            print(f"  最大耗时:         {max(all_times):.2f}s")
            print(f"  最小耗时:         {min(all_times):.2f}s")
            print(f"  P50 (中位数):     {statistics.median(all_times):.2f}s")
            print(f"  P95:              {sorted(all_times)[int(len(all_times) * 0.95)]:.2f}s")
        if all_tokens:
            print(f"  平均 completion tokens: {statistics.mean(all_tokens):.0f}")
        if tool_call_counts:
            print(f"  平均 tool_calls / 轮:    {statistics.mean(tool_call_counts):.1f}")

        print(f"\n{'─' * 64}")
        print(f"  各场景统计:")
        print(f"  {'场景':12s} {'总数':>5s} {'成功':>5s} {'成功率':>7s} {'触发工具':>8s} {'平均耗时':>8s}")
        print(f"{'─' * 64}")
        for name, ss in sorted(self.scenarios.items()):
            trigger_rate = ss.tool_triggered / ss.total * 100
            avg_t = statistics.mean(ss.total_time) if ss.total_time else 0
            succ_rate = ss.success / ss.total * 100 if ss.total else 0
            print(f"  {name:12s} {ss.total:5d} {ss.success:5d} {succ_rate:6.1f}% "
                  f"{trigger_rate:6.1f}%  {avg_t:7.2f}s")
        print(f"{'─' * 64}")
        for i, r in enumerate(self.all_results):
            status = "✓" if r.success else "✗"
            tools = ",".join(r.tool_call_names) if r.tool_call_names else "-"
            err = f"  ERR: {r.error}" if r.error else ""
            model_short = r.model.replace("deepseek-", "ds-")
            print(f"  #{i + 1:3d} [{status}] {model_short:10s} {r.scenario_name:10s} "
                  f"{r.total_time:6.2f}s  tools={r.tool_call_count:2d}({tools:20s})  "
                  f"tok={r.completion_tokens:5d}{err}")
        print(f"{'=' * 64}\n")


def build_report(results: list[RunResult], config: dict, title: str = "工具调用压测报告") -> Report:
    """汇总结果为报告"""
    scenes: dict[str, list[RunResult]] = {}
    for r in results:
        scenes.setdefault(r.scenario_name, []).append(r)

    stats = {}
    for sname, sresults in scenes.items():
        stats[sname] = ScenarioStats(
            name=sname,
            total=len(sresults),
            success=sum(1 for r in sresults if r.success),
            tool_triggered=sum(1 for r in sresults if r.tool_call_count > 0),
            total_time=[r.total_time for r in sresults],
            tool_calls_per_run=[r.tool_call_count for r in sresults],
        )

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return Report(
        scenarios=stats,
        all_results=results,
        start_time=config.get("start_time", now_str),
        end_time=now_str,
        config=config,
        title=title,
    )


def add_common_arguments(parser: argparse.ArgumentParser):
    """添加共享 CLI 参数"""
    parser.add_argument(
        "--iterations", type=int, default=DEFAULT_ITERATIONS, help="每场景迭代次数"
    )
    parser.add_argument("--parallel", type=int, default=DEFAULT_PARALLEL, help="并行数")
    parser.add_argument(
        "--models", type=str, nargs="*", default=None,
        help="模型列表 (default: 协议默认)"
    )
    parser.add_argument(
        "--scenario", type=str, default=None, help="仅运行指定场景（名称关键字匹配）"
    )
    parser.add_argument(
        "--stream", action="store_true", help="使用流式 API（默认非流式）"
    )
    parser.add_argument(
        "--report", type=str, default=None, help="输出 JSON 报告文件路径"
    )


def filter_scenarios(
    scenarios: list[dict[str, Any]], keyword: str | None
) -> list[dict[str, Any]]:
    """按关键字过滤场景"""
    if not keyword:
        return scenarios
    matched = [s for s in scenarios if keyword.lower() in s["name"].lower()]
    if not matched:
        print(f"[错误] 未找到匹配的场景: {keyword}")
        raise SystemExit(1)
    return matched


def run_stress_loop(
    run_scenario_fn,
    client: Any,
    scenarios: list[dict[str, Any]],
    models: list[str],
    iterations: int,
    parallel: int,
    use_stream: bool,
) -> list[RunResult]:
    """通用压测主循环（并行执行 + 进度输出）"""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    total_count = len(scenarios) * len(models) * iterations
    all_results: list[RunResult] = []

    with ThreadPoolExecutor(max_workers=parallel) as executor:
        futures = []
        for model in models:
            for scenario in scenarios:
                for i in range(iterations):
                    futures.append(
                        executor.submit(run_scenario_fn, client, scenario, model, i, use_stream)
                    )

        done = 0
        for future in as_completed(futures):
            done += 1
            all_results.append(future.result())
            if done % max(1, total_count // 10) == 0 or done == total_count:
                print(f"  进度: {done}/{total_count} ({done * 100 // total_count}%)", end="\r", flush=True)

    print(f"\n  完成!                                  ")
    return all_results


def save_json_report(report: Report, path: str):
    """输出 JSON 报告文件"""
    import json

    json_data = {
        "config": report.config,
        "title": report.title,
        "summary": {
            "total": report.total,
            "success": report.success,
            "failed": report.failed,
            "success_rate": round(report.success / report.total * 100, 1),
        },
        "scenarios": {
            name: {
                "total": ss.total,
                "success": ss.success,
                "tool_triggered": ss.tool_triggered,
                "avg_time": round(statistics.mean(ss.total_time), 3),
                "max_time": round(max(ss.total_time), 3),
                "min_time": round(min(ss.total_time), 3),
                "avg_tool_calls": round(statistics.mean(ss.tool_calls_per_run), 1),
            }
            for name, ss in report.scenarios.items()
        },
        "runs": [
            {
                "scenario": r.scenario_name,
                "success": r.success,
                "total_time": round(r.total_time, 3),
                "tool_call_count": r.tool_call_count,
                "tool_call_names": r.tool_call_names,
                "completion_tokens": r.completion_tokens,
                "error": r.error,
            }
            for r in report.all_results
        ],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)
    print(f"  JSON 报告已输出: {path}")
