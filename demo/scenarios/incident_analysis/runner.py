#!/usr/bin/env python3
"""Case 1: AI Incident Diagnosis — 故障分析助手演示。

Usage:
  python demo/scenarios/incident_analysis/runner.py
  python demo/scenarios/incident_analysis/runner.py --case incident-001

加载 case.json 中的故障场景, 通过 AI Platform 执行诊断流程,
输出 IncidentReport。
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── Add project root ────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ai_platform.core import PlatformConfig, PlatformFactory, AIPlatformService
from ai_platform.llm.config import load_env_file, load_gateway_config
from ai_platform.llm.gateway import LLMGateway
from ai_platform.llm.types import LLMRequest
from ai_platform.security.policy import SecurityPolicy
from ai_platform.tools.base import BaseTool
from ai_platform.tools.registry import ToolRegistry
from ai_platform.tools.executor import ToolExecutor, ToolExecutionResult
from ai_platform.workflow.node import BaseNode
from ai_platform.workflow.engine import WorkflowEngine
from ai_platform.agent.runtime import AgentRuntime
from ai_platform.agent.state import AgentState
from ai_platform.agent.context import AgentContext
from demo.scenarios.incident_analysis.data_sources import fetch_metrics, read_recent_logs

# 真实数据源配置（调用时读取，便于测试注入）：
#   CHAOS_SERVICE_URL  Chaos Service 地址（默认 http://127.0.0.1:5000，取 /metrics）
#   CHAOS_LOG_FILE     流量录制 JSONL 路径（默认 reports/traffic_record_latest.jsonl）
_DEFAULT_LOG_FILE = _PROJECT_ROOT / "reports" / "traffic_record_latest.jsonl"

# 读入仓库根 .env（含 LLM_GATEWAY_*，如 DeepSeek key）；已设环境变量优先
load_env_file()

# 真 LLM 诊断的显式开关（默认关闭，保证测试离线确定性）：
#   INCIDENT_LLM_ENABLED=1 python demo/scenarios/incident_analysis/runner.py
# 或 CLI: python demo/scenarios/incident_analysis/runner.py --llm
_LLM_ENABLED = os.environ.get("INCIDENT_LLM_ENABLED", "").strip().lower() in (
    "1", "true", "yes", "on",
)


# ── Mock Tools (模拟: 日志分析, 指标查询, 根因分析) ────────────────

_SIMULATED_LOGS = {
    "order-api": [
        "[ERROR] 2026-07-25T10:15:00Z Redis connection timeout after 5000ms",
        "[ERROR] 2026-07-25T10:15:01Z Connection pool exhausted: max=100, active=100, waiting=45",
        "[ERROR] 2026-07-25T10:15:02Z Unable to execute command: OOM command not allowed when used memory > 'maxmemory'",
        "[WARN] 2026-07-25T10:14:00Z Redis memory usage at 95% — approaching maxmemory limit",
        "[ERROR] 2026-07-25T10:15:03Z Request failed: upstream connect error",
    ],
    "mysql": [
        "[SLOW] 2026-07-25T10:14:30Z Query took 3200ms: SELECT * FROM orders WHERE status='pending'",
        "[ERROR] 2026-07-25T10:15:00Z Too many connections: max=200, current=200",
        "[WARN] 2026-07-25T10:14:00Z slow_db fault injection triggered at 10:14:30",
    ],
    "cache": [
        "[WARN] 2026-07-25T10:16:00Z cache write failed after 3 retries: key='order:ORD-xxx'",
        "[ERROR] 2026-07-25T10:16:01Z Redis connection refused during cache update (drop fault injected)",
        "[WARN] 2026-07-25T10:15:00Z stale cache hit detected: TTL=-1 but DB row was updated at 10:14",
    ],
}

_SIMULATED_METRICS = {
    "order-api": {
        "error_rate": 0.35,
        "latency_p99_ms": 5200,
        "latency_p50_ms": 450,
        "qps": 1200,
        "active_connections": 100,
        "redis_memory_used_pct": 0.95,
    },
    "mysql": {
        "error_rate": 0.02,
        "latency_p99_ms": 5000,
        "latency_p50_ms": 320,
        "qps": 600,
        "slow_query_count": 128,
        "db_connections": 200,
    },
    "cache": {
        "error_rate": 0.05,
        "latency_p99_ms": 180,
        "latency_p50_ms": 60,
        "qps": 900,
        "cache_miss_rate": 0.42,
        "stale_keys": 3,
    },
}

_ROOT_CAUSE_MAP = {
    "Redis连接池耗尽": {
        "problem": "订单接口大量500错误，错误率35%，p99延迟从100ms飙升至5.2秒",
        "root_cause": "Redis连接池耗尽 — 高并发下连接池max=100全部占满，导致新请求获取连接超时",
        "evidence": [
            "日志显示10:15:00起大量 'Connection pool exhausted: max=100, active=100'",
            "Redis内存使用率达95%，触发OOM保护拒绝写入",
            "前序告警: 10:14:00 Redis内存使用率95%未及时处理",
            "p99延迟曲线在10:14:30开始陡升，与Redis内存告警时间吻合"
        ],
        "suggestion": "1. 紧急: 扩容Redis连接池max→200; 2. 清理过期key释放内存; 3. 增加maxmemory或启用LRU淘汰; 4. 长期: 增加Redis内存告警→自动扩容",
        "confidence": 0.92
    },
    "数据库慢查询": {
        "problem": "创建订单p99延迟从100ms涨到5秒",
        "root_cause": "数据库慢查询 + 连接池饱和 — pending状态订单扫描SQL耗时3.2秒，耗尽连接池",
        "evidence": [
            "慢查询日志: SELECT * FROM orders WHERE status='pending' 耗时3200ms",
            "MySQL连接池max=200全部占满",
            "p99延迟从100ms爬升至5秒，与慢查询开始时间一致",
            "slow_db故障注入在10:14:30触发"
        ],
        "suggestion": "1. 紧急: 为orders.status添加索引; 2. 限制查询范围添加LIMIT; 3. 增加MySQL连接池max→400; 4. 长期: 引入只读副本分离查询",
        "confidence": 0.88
    },
    "缓存不一致": {
        "problem": "订单查询返回404但实际存在",
        "root_cause": "Redis缓存与数据库不一致 — 写入DB成功但Redis缓存更新失败，导致读到过期数据",
        "evidence": [
            "缓存key 'order:ORD-xxx' TTL为-1 (永不过期) 但数据已更新",
            "数据库中存在该订单而Redis中TTL未刷新",
            "故障注入drop模式导致缓存更新请求被丢弃",
            "对比DB和Redis数据发现3条不一致记录"
        ],
        "suggestion": "1. 紧急: 手动刷新受影响订单缓存; 2. 启用Cache-Aside模式，DB写入成功后删除(非更新)缓存; 3. 增加缓存写入失败重试; 4. 长期: 引入CDC实时同步",
        "confidence": 0.85
    }
}


# ── Demo Tools ───────────────────────────────────────────────────────

class QueryLogsTool(BaseTool):
    name = "query_logs"
    description = "查询服务日志，支持按时间范围和关键词筛选"
    schema = {
        "service": {"type": str, "required": True},
        "time_range": {"type": str, "required": False},
        "keyword": {"type": str, "required": False},
    }

    def execute(self, params: dict[str, Any], *, context: Any = None) -> ToolExecutionResult:
        service = params.get("service", "order-api")
        keyword = params.get("keyword", "").strip() or None
        time_range = params.get("time_range", "").strip() or None

        # 真实源优先：流量录制 JSONL（可用 CHAOS_LOG_FILE 覆盖）；不可用 → 模拟数据降级
        log_file = Path(os.environ.get("CHAOS_LOG_FILE", "").strip() or _DEFAULT_LOG_FILE)
        logs = read_recent_logs(log_file, limit=200, keyword=keyword, time_range=time_range)
        if logs is None:
            logs = _SIMULATED_LOGS.get(service, [])
            if keyword:
                logs = [l for l in logs if keyword.lower() in l.lower()]
            source = "simulated"
        else:
            source = "traffic_record"

        return ToolExecutionResult(
            tool=self.name, ok=True, result={"service": service, "logs": logs, "count": len(logs)},
            attempts=[{"tool": self.name, "result": "ok"}],
            metadata={"response_text": f"找到 {len(logs)} 条日志", "source": source}
        )


class QueryMetricsTool(BaseTool):
    name = "query_metrics"
    description = "查询服务指标，返回QPS/延迟/错误率等Prometheus数据"
    schema = {
        "service": {"type": str, "required": True},
        "metric_names": {"type": list, "required": False},
    }

    def execute(self, params: dict[str, Any], *, context: Any = None) -> ToolExecutionResult:
        service = params.get("service", "order-api")

        # 真实源优先：Chaos Service /metrics（可用 CHAOS_SERVICE_URL 覆盖）；不可用 → 模拟数据降级
        base_url = os.environ.get("CHAOS_SERVICE_URL", "http://127.0.0.1:5000").strip()
        metrics = fetch_metrics(base_url) if base_url else None
        if metrics is None:
            metrics = dict(_SIMULATED_METRICS.get(service, {}))
            metrics["source"] = "simulated"

        p99 = metrics.get("latency_p99_ms")
        p99_text = f"{p99}ms" if p99 is not None else "N/A"
        return ToolExecutionResult(
            tool=self.name, ok=True, result={"service": service, "metrics": metrics},
            attempts=[{"tool": self.name, "result": "ok"}],
            metadata={
                "response_text": f"服务 {service}: 错误率 {metrics.get('error_rate', 0):.0%}, p99={p99_text}",
                "source": metrics.get("source"),
            }
        )


class AnalyzeIncidentTool(BaseTool):
    name = "analyze_incident"
    description = "基于日志和指标数据做根因分析，返回IncidentReport"
    schema = {
        "logs_summary": {"type": str, "required": True},
        "metrics_summary": {"type": str, "required": True},
        "symptom": {"type": str, "required": False},
        "use_llm": {"type": bool, "required": False},
    }

    def execute(self, params: dict[str, Any], *, context: Any = None) -> ToolExecutionResult:
        """根因分析：显式开启 LLM 时由真大模型生成报告，否则规则匹配（降级链一致）。"""
        logs_text = params.get("logs_summary", "")
        metrics_text = params.get("metrics_summary", "")
        symptom = params.get("symptom", "")
        use_llm = bool(params.get("use_llm", _LLM_ENABLED))

        if use_llm:
            report = self._analyze_with_llm(logs_text, metrics_text, symptom)
            if report is not None:
                return ToolExecutionResult(
                    tool=self.name, ok=True, result=report,
                    attempts=[{"tool": self.name, "result": "ok"}],
                    metadata={
                        "response_text": f"根因分析完成(LLM), 置信度: {report['confidence']:.0%}",
                        "analysis_backend": "llm",
                    }
                )

        # 降级链：LLM 未启用/不可用/输出不合法 → 规则匹配
        report = self._analyze_by_rule(logs_text, metrics_text, symptom)
        return ToolExecutionResult(
            tool=self.name, ok=True, result=report,
            attempts=[{"tool": self.name, "result": "ok"}],
            metadata={
                "response_text": f"根因分析完成(规则), 置信度: {report['confidence']:.0%}",
                "analysis_backend": "rule",
            }
        )

    @staticmethod
    def _analyze_by_rule(logs_text: str, metrics_text: str, symptom: str) -> dict[str, Any]:
        """写死数据 + 规则匹配（无网络依赖的确定性降级路径）。

        症状信号优先（由用户请求派生，随用例变化），日志/指标关键字作为佐证。
        注意：模拟日志内容对 order-api 是固定的，若日志关键字优先会永远命中
        Redis 连接池耗尽，导致「慢查询」「缓存不一致」两个用例误诊。
        """
        symptom = symptom or ""
        if "延迟" in symptom or "slow" in logs_text.lower() or "3200ms" in logs_text:
            return _ROOT_CAUSE_MAP["数据库慢查询"]
        if "缓存" in symptom or "404" in symptom or "缓存" in logs_text:
            return _ROOT_CAUSE_MAP["缓存不一致"]
        if "500" in symptom or "Connection pool exhausted" in logs_text or "OOM" in logs_text:
            return _ROOT_CAUSE_MAP["Redis连接池耗尽"]
        return _ROOT_CAUSE_MAP["Redis连接池耗尽"]  # default

    @staticmethod
    def _analyze_with_llm(logs_text: str, metrics_text: str, symptom: str) -> dict[str, Any] | None:
        """真 LLM 根因分析；任何异常/输出不合法返回 None（上层降级到规则匹配）。"""
        prompt = (
            "你是资深 SRE 故障诊断专家。根据以下日志、指标和用户描述，"
            "输出一个 JSON 对象（不要输出其他内容），字段：\n"
            '{"problem": "故障现象", "root_cause": "根因", '
            '"evidence": ["证据1", "证据2"], "suggestion": "修复建议", '
            '"confidence": 0.0-1.0 置信度}\n'
            f"用户描述: {symptom or '服务异常'}\n"
            f"日志摘要: {logs_text[:3000]}\n"
            f"指标摘要: {metrics_text[:2000]}\n"
            "只输出 JSON。"
        )
        try:
            config = load_gateway_config(provider=os.getenv("LLM_GATEWAY_PROVIDER", "").strip() or None)
            gateway = LLMGateway(config=config)
            response = gateway.generate(
                LLMRequest(
                    prompt=prompt,
                    system="",
                    provider=config.provider,
                    model=config.model,
                    response_format="json",
                    timeout_sec=config.timeout_sec,
                    metadata={"caller": "incident_analysis.analyze_incident"},
                )
            )
        except Exception:
            return None

        report = response.parsed_json
        if not isinstance(report, dict):
            return None
        # 结构校验：字段不齐则视为不可用
        required = {"problem", "root_cause", "evidence", "suggestion", "confidence"}
        if not required.issubset(report.keys()):
            return None
        if not isinstance(report.get("evidence"), list) or not report.get("evidence"):
            return None
        try:
            confidence = float(report.get("confidence"))
        except (TypeError, ValueError):
            return None
        if not (0.0 <= confidence <= 1.0):
            return None
        report["confidence"] = confidence
        return report


# ── Workflow Node ────────────────────────────────────────────────────

class IncidentDiagnosisNode(BaseNode):
    """故障诊断工作流节点: 日志 → 指标 → 分析 → 报告"""
    name = "incident_diagnosis"

    def __init__(self, executor: ToolExecutor, *, llm_enabled: bool = False) -> None:
        self._executor = executor
        self._llm_enabled = llm_enabled

    def execute(self, state: AgentState, context: AgentContext) -> AgentState:
        request_text = state.request if isinstance(state.request, str) else str(state.request)

        # 证据源选择：由用例上下文驱动（case.json 的 context.service 经元数据透传），
        # 保证「延迟飙升」用例查 mysql 日志、「缓存不一致」用例查 cache 日志——
        # 否则 LLM 拿到同一份证据只会给出同一个答案。
        service = state.metadata.get("service", "order-api")

        # Step 1: 查询日志
        logs_result = self._executor.execute("query_logs", {"service": service})
        if logs_result.ok:
            state.add_tool_result(tool="query_logs", result=logs_result.result, metadata={"count": logs_result.result.get("count", 0)})

        # Step 2: 查询指标
        metrics_result = self._executor.execute("query_metrics", {"service": service})
        if metrics_result.ok:
            state.add_tool_result(tool="query_metrics", result=metrics_result.result)

        # Step 3: 根因分析（use_llm 由 runner 显式开启，未开启走规则降级）
        logs_summary = str(logs_result.result.get("logs", [])[:3])
        metrics_summary = str(metrics_result.result.get("metrics", {}))
        symptom = "大量500错误" if "500" in request_text else ("延迟飙升" if "延迟" in request_text else "缓存不一致")
        analysis = self._executor.execute("analyze_incident", {
            "logs_summary": logs_summary,
            "metrics_summary": metrics_summary,
            "symptom": symptom,
            "use_llm": self._llm_enabled,
        })

        if analysis.ok:
            report = dict(analysis.result)
            report["analysis_backend"] = analysis.metadata.get("analysis_backend", "rule")
            report["called_tools"] = [entry["tool"] for entry in state.tool_result] + ["analyze_incident"]
            report["log_source"] = logs_result.metadata.get("source", "simulated")
            report["metrics_source"] = metrics_result.metadata.get("source", "simulated")
            state.add_tool_result(tool="analyze_incident", result=report)
            state.set_answer(report)
            state.metadata["incident_report"] = report
            state.metadata["diagnosis_complete"] = True

        return state


# ── Runner ───────────────────────────────────────────────────────────

def build_platform_service(*, llm_enabled: bool = False) -> AIPlatformService:
    """构建带诊断工具和节点的AI Platform服务。

    llm_enabled=True 时根因分析由真 LLM 生成（provider 走 LLM_GATEWAY_*，
    .env 可配 DeepSeek），失败自动降级规则匹配。
    """
    config = PlatformConfig.default()
    factory = PlatformFactory(config)

    # 注册诊断工具
    registry = ToolRegistry()
    registry.register(QueryLogsTool())
    registry.register(QueryMetricsTool())
    registry.register(AnalyzeIncidentTool())

    executor = ToolExecutor(registry=registry, security=config.security)

    # 创建工作流
    workflow = WorkflowEngine()
    workflow.register(IncidentDiagnosisNode(executor, llm_enabled=llm_enabled))

    runtime = AgentRuntime(
        workflow=workflow,
        security=config.security,
        observability_enabled=True,
    )

    return AIPlatformService(agent_runtime=runtime, config=config)


def _root_cause_matches(expected: str, actual: str) -> bool:
    """判定根因是否命中预期。

    取预期根因的前 4 个非 ASCII 字符作为关键词：'Redis连接池耗尽' → '连接池耗'。
    不能用 `expected[:4]`——对以 ASCII 开头的预期串会切出 'Redi'，
    任何以 Redis 开头的错误根因都会假阳性。
    """
    keyword = "".join(ch for ch in expected if not ch.isascii())[:4] or expected[:4]
    return bool(keyword) and keyword in actual


def run_incident_diagnosis(case_id: str | None = None, *, llm_enabled: bool | None = None) -> dict[str, Any]:
    """运行故障诊断演示。llm_enabled=None 时跟随 INCIDENT_LLM_ENABLED 环境变量。"""
    if llm_enabled is None:
        llm_enabled = _LLM_ENABLED
    service = build_platform_service(llm_enabled=llm_enabled)

    # 加载用例
    cases_path = Path(__file__).parent / "case.json"
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    inputs = cases["inputs"]

    if case_id:
        inputs = [c for c in inputs if c["id"] == case_id]
        if not inputs:
            print(f"ERROR: Case not found: {case_id}")
            sys.exit(2)

    results = []
    for case in inputs:
        print(f"\n{'='*60}")
        print(f"  Case: {case['id']} | Severity: {case['severity']}")
        print(f"  Input: {case['user_input']}")
        print(f"{'='*60}")

        start = time.perf_counter()
        result = service.run(
            case["user_input"],
            mode="rule",
            metadata={"service": (case.get("context") or {}).get("service", "order-api")},
        )
        elapsed = (time.perf_counter() - start) * 1000

        report: dict[str, Any]
        if result.success and result.answer:
            report = result.answer if isinstance(result.answer, dict) else {}
        else:
            report = {"error": result.error, "error_type": result.error_type}

        r = {
            "case_id": case["id"],
            "user_input": case["user_input"],
            "success": result.success,
            "report": report,
            "trace_id": result.trace_id,
            "elapsed_ms": round(elapsed, 1),
            "analysis_backend": report.get("analysis_backend", "rule") if isinstance(report, dict) else "unknown",
            "expected_root_cause": case["expected_root_cause"],
            "expected_tools": case["expected_tools"],
            "tools_called": report.get("called_tools", []) if isinstance(report, dict) else [],
        }

        # Check if root cause matches
        actual_rc = report.get("root_cause", "") if isinstance(report, dict) else ""
        r["root_cause_match"] = _root_cause_matches(case["expected_root_cause"], actual_rc)

        results.append(r)
        _print_report(report, elapsed, case, match=r["root_cause_match"])

    return {"scenario": "AI Incident Diagnosis", "results": results, "total": len(results)}


def _print_report(report: dict[str, Any], elapsed_ms: float, case: dict[str, Any], *, match: bool) -> None:
    if not isinstance(report, dict) or "error" in report:
        print(f"\n  [FAIL] Diagnosis failed: {report.get('error', 'Unknown')}")
        return

    print(f"\n  [Report] Incident Report")
    print(f"  {'─' * 50}")
    print(f"  故障现象:   {report.get('problem', 'N/A')}")
    print(f"  根因:       {report.get('root_cause', 'N/A')}")
    print(f"  置信度:     {report.get('confidence', 0):.0%}")
    print(f"  证据:")
    for evidence in report.get("evidence", []):
        print(f"    - {evidence}")
    print(f"  修复建议:   {report.get('suggestion', 'N/A')}")
    print(f"  {'─' * 50}")
    print(f"  预期根因:   {case['expected_root_cause']}")
    print(f"  诊断判定:   {'正确' if match else '错误（与预期不符）'}")
    print(f"  分析后端:   {report.get('analysis_backend', 'rule')} / 数据来源: 日志={report.get('log_source', 'simulated')} 指标={report.get('metrics_source', 'simulated')}")
    print(f"  耗时:       {elapsed_ms:.1f}ms")
    print(f"  Trace ID:   (collector snapshot available)")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AI Incident Diagnosis Demo")
    parser.add_argument("--case", type=str, default=None, help="Run specific case (e.g. incident-001)")
    parser.add_argument(
        "--llm",
        action="store_true",
        help="根因分析由真 LLM 生成（provider 走 LLM_GATEWAY_*，.env 可配 DeepSeek）；"
             "失败自动降级规则匹配。等价于 INCIDENT_LLM_ENABLED=1",
    )
    args = parser.parse_args()
    run_incident_diagnosis(args.case, llm_enabled=args.llm or None)
