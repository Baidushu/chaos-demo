"""LLM 辅助测试工具 — 用大模型生成测试用例、分析测试报告。

功能：
- generate-tests: 从 API 描述生成 pytest 测试用例
- analyze-report: 分析压测/安全扫描报告，给出根因和建议

用法：
    python llm_assist.py generate-tests
    python llm_assist.py analyze-report --report reports/benchmark_latest.json
    python llm_assist.py analyze-report --report reports/security_scan_latest.json

环境变量（LLM 配置见 llm_client.py）：
    LLM_BACKEND: ollama | openai（默认 auto）
    LLM_API_KEY: 云端 API Key
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from llm_client import LLMClient

REPORT_DIR = Path("reports")


def get_client() -> LLMClient:
    try:
        return LLMClient()
    except ValueError as e:
        print(f"[llm_assist] ERROR: {e}", file=sys.stderr)
        sys.exit(1)


# ---- 测试用例生成 ----

API_DESCRIPTION = """
这是一个 Flask 订单服务的 API：

POST /order
- 请求体: {"item_id": "sku-1", "quantity": 2}
- 请求头: X-Idempotency-Key（可选，幂等键）
- 成功: 201 {"status": "ok", "order_id": "..."}
- 幂等回放: 200 {"status": "ok", "order_id": "...", "idempotent": true}
- 参数错误: 400 {"error": "invalid request"}
- 限流: 429 {"error": "rate limit exceeded"}
- 幂等冲突: 409 {"error": "idempotency key reused with different payload"}
- 降级/熔断: 202 {"status": "queued", "reason": "circuit open"}
- 库存繁忙: 503 {"error": "inventory busy"}

GET /order/<order_id>
- 成功: 200 {"order_id": "...", "item_id": "...", "quantity": 2, "status": "created"}
- 不存在: 404 {"error": "order not found"}

POST /order/<order_id>/cancel
- 成功: 200 {"status": "ok", "cancelled": true}
- 已取消: 200 {"status": "ok", "already_cancelled": true}

故障注入 API：
POST /fault/inject  {"type": "latency|exception|drop|slow_db", "params": {...}, "ttl_sec": 60}
POST /fault/clear   {"type": "latency"}
POST /fault/clear-all
GET  /fault/status

已有的测试覆盖：
- 正常下单、幂等回放、幂等冲突、并发幂等
- 限流拒绝（滑动窗口、固定窗口）
- 熔断半开探测（成功关闭、失败重开）
- 健康检查（正常、Redis 不可用降级）
- 参数校验（空 item_id、quantity<=0、非数字）
- 订单取消幂等
- 故障注入（延迟/丢包/异常/API 清除）
"""

GENERATE_TESTS_PROMPT = f"""你是一个资深测开工程师。基于以下 API 描述，生成 pytest 测试用例。

要求：
1. 只生成**尚未覆盖**的测试场景（见"已有的测试覆盖"）
2. 重点关注：边界值、异常路径、组合场景
3. 每个测试用例用 def test_xxx(client): 格式
4. 用 assert 验证状态码和响应体
5. 输出合法的 Python 代码，可以直接用

API 描述：
{API_DESCRIPTION}

输出格式：一个合法的 Python 文件内容，包含 imports 和多个 test_ 函数。"""


def generate_tests(client: LLMClient) -> str:
    """用 LLM 生成测试用例。"""
    print(f"[llm_assist] generating tests with {client.backend}/{client.model} ...")
    system = "你是测开专家，输出高质量的 pytest 测试代码。只输出 Python 代码，不要解释。"
    code = client.chat(GENERATE_TESTS_PROMPT, system=system, max_tokens=3000)
    return code


# ---- 报告分析 ----

def build_analysis_prompt(report_data: dict, report_type: str) -> str:
    """根据报告类型构建分析 prompt。"""
    report_json = json.dumps(report_data, ensure_ascii=False, indent=2)
    if report_type == "benchmark":
        return f"""分析以下压测报告，给出：
1. 关键指标解读（QPS、P95、P99、成功率、降级率）
2. 治理版 vs 基线版的差异分析
3. 是否存在性能问题或配置不合理
4. 优化建议

报告数据：
{report_json}

用中文回答，结构化输出。"""
    elif report_type == "security":
        return f"""分析以下安全扫描报告，给出：
1. 发现的安全问题解读
2. 风险等级评估
3. 修复建议
4. 是否有误报可能

报告数据：
{report_json}

用中文回答，结构化输出。"""
    else:
        return f"""分析以下测试报告，识别异常指标，给出根因假设和改进建议。

报告数据：
{report_json}

用中文回答，结构化输出。"""


def analyze_report(client: LLMClient, report_path: str) -> str:
    """用 LLM 分析报告。"""
    path = Path(report_path)
    if not path.exists():
        print(f"[llm_assist] ERROR: report not found: {report_path}", file=sys.stderr)
        sys.exit(1)

    data = json.loads(path.read_text(encoding="utf-8"))
    report_type = "benchmark" if "benchmark" in str(path) else (
        "security" if "security" in str(path) else "unknown"
    )

    print(f"[llm_assist] analyzing {report_type} report with {client.backend}/{client.model} ...")
    prompt = build_analysis_prompt(data, report_type)
    system = "你是资深 SRE 和测开专家，擅长分析性能和安全报告。"
    return client.chat(prompt, system=system, max_tokens=2000)


def main():
    parser = argparse.ArgumentParser(description="LLM-assisted testing tool")
    sub = parser.add_subparsers(dest="command")

    gen = sub.add_parser("generate-tests", help="Generate pytest test cases from API spec")
    gen.add_argument("--output", default="tests/test_llm_generated.py", help="Output file path")

    ana = sub.add_parser("analyze-report", help="Analyze a test/scan report")
    ana.add_argument("--report", required=True, help="Report JSON path")
    ana.add_argument("--output", help="Save analysis to file (default: print to stdout)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    client = get_client()
    print(f"[llm_assist] backend={client.backend} model={client.model}")

    if args.command == "generate-tests":
        code = generate_tests(client)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        # 清理 markdown 代码块标记
        import re
        cleaned = re.sub(r"^```python\s*", "", code, flags=re.MULTILINE)
        cleaned = re.sub(r"^```\s*$", "", cleaned, flags=re.MULTILINE)
        output.write_text(cleaned.strip() + "\n", encoding="utf-8")
        print(f"[llm_assist] saved: {output}")
        print(f"[llm_assist] run with: python -m pytest {output} -v")

    elif args.command == "analyze-report":
        analysis = analyze_report(client, args.report)
        if args.output:
            Path(args.output).write_text(analysis, encoding="utf-8")
            print(f"[llm_assist] saved: {args.output}")
        else:
            print("\n" + "=" * 60)
            print(analysis)
            print("=" * 60)

        # 同时保存到 reports/
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        analysis_path = REPORT_DIR / "llm_analysis_latest.md"
        analysis_path.write_text(analysis, encoding="utf-8")
        print(f"[llm_assist] saved: {analysis_path}")


if __name__ == "__main__":
    main()
