"""声明式混沌实验 runner（Chaos Toolkit 风格）。

用法：
    python agent-eval/scripts/run_experiment.py [--experiment <yaml>]

流程：
    1. 加载并严格校验实验定义 YAML（未知键/缺段/非法值 fail-fast）；
    2. 以 YAML 中的 method/tolerance 驱动 chaos_compare.py（子进程，参数化）；
    3. 裁决：稳态假设（baseline 指标底线）+ 容忍上界（token/重试增量门禁）；
    4. 写 reports/experiment_<name>_latest.{json,md}，任一不满足 exit 1。

与 chaos_compare.py --strict 的分工：本脚本是声明式入口（参数与阈值
单一来源 = YAML，随仓库评审）；chaos_compare 保留为 CI 直跑的命令式
入口（默认值与 YAML 一致）。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
CHAOS_COMPARE_SCRIPT = ROOT / "scripts" / "chaos_compare.py"
COMPARE_JSON = ROOT / "reports" / "chaos_compare_latest.json"
REPORT_DIR = ROOT / "reports"
DEFAULT_EXPERIMENT = ROOT / "experiments" / "mixed_fault.yaml"

_SUPPORTED_VERSIONS = (1,)
_TOP_LEVEL_KEYS = {"version", "name", "description", "steady_state", "method", "tolerance", "rollback"}
_STEADY_STATE_KEYS = {"tool_selection_accuracy_min", "arg_accuracy_min", "retry_rate_max"}
_METHOD_KEYS = {"mode", "experiment"}
_EXPERIMENT_KEYS = {"chaos", "fail_rate", "latency_ms"}
_MODES = ("rule", "ollama", "llm")
_TOLERANCE_KEYS = {"token_surge_max", "retry_surge_max", "fail_path_token_surge_max"}
_ROLLBACK_KEYS = {"fault_ttl_sec"}

# tolerance 键 -> (chaos_compare 环境变量, gate 结果字段前缀)
_TOLERANCE_ENV = {
    "token_surge_max": ("CHAOS_TOKEN_SURGE_MAX", "token_surge"),
    "retry_surge_max": ("CHAOS_RETRY_SURGE_MAX", "retry_surge"),
    "fail_path_token_surge_max": ("CHAOS_FAIL_PATH_TOKEN_SURGE_MAX", "fail_path_token_surge"),
}


class ExperimentDefinitionError(ValueError):
    """实验定义不合法——加载期 fail-fast。"""


def load_experiment(path: Path | str) -> dict:
    """加载并严格校验实验定义，返回规范化 dict。"""
    file_path = Path(path)
    if not file_path.is_file():
        raise ExperimentDefinitionError(f"experiment definition not found: {file_path}")
    try:
        raw = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ExperimentDefinitionError(f"invalid YAML in {file_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ExperimentDefinitionError(f"experiment definition {file_path} must be a mapping")

    unknown = set(raw) - _TOP_LEVEL_KEYS
    if unknown:
        raise ExperimentDefinitionError(f"unknown top-level keys: {sorted(unknown)}")
    if raw.get("version") not in _SUPPORTED_VERSIONS:
        raise ExperimentDefinitionError(f"unsupported version {raw.get('version')!r}")

    name = str(raw.get("name", "")).strip()
    if not name:
        raise ExperimentDefinitionError("experiment name must not be empty")

    steady_state = _validate_section(raw.get("steady_state"), _STEADY_STATE_KEYS, "steady_state", required=True)
    for key in _STEADY_STATE_KEYS:
        if key not in steady_state:
            raise ExperimentDefinitionError(f"steady_state.{key} is required")
        steady_state[key] = _as_float(steady_state[key], f"steady_state.{key}")

    method = _validate_section(raw.get("method"), _METHOD_KEYS, "method", required=True)
    mode = str(method.get("mode", "rule"))
    if mode not in _MODES:
        raise ExperimentDefinitionError(f"method.mode must be {'|'.join(_MODES)}, got {mode!r}")
    experiment = _validate_section(method.get("experiment"), _EXPERIMENT_KEYS, "method.experiment", required=True)
    chaos = str(experiment.get("chaos", "mixed"))
    if chaos not in ("latency", "error", "mixed"):
        raise ExperimentDefinitionError(f"method.experiment.chaos must be latency|error|mixed, got {chaos!r}")
    experiment["fail_rate"] = _as_float(experiment.get("fail_rate", 0.0), "method.experiment.fail_rate")
    experiment["latency_ms"] = int(_as_float(experiment.get("latency_ms", 0), "method.experiment.latency_ms"))

    tolerance = _validate_section(raw.get("tolerance"), _TOLERANCE_KEYS, "tolerance", required=True)
    for key, value in list(tolerance.items()):
        tolerance[key] = _as_float(value, f"tolerance.{key}")

    rollback = _validate_section(raw.get("rollback"), _ROLLBACK_KEYS, "rollback", required=False) or {}
    if "fault_ttl_sec" in rollback:
        rollback["fault_ttl_sec"] = int(_as_float(rollback["fault_ttl_sec"], "rollback.fault_ttl_sec"))

    return {
        "version": raw["version"],
        "name": name,
        "description": str(raw.get("description", "")),
        "steady_state": steady_state,
        "method": {"mode": mode, "experiment": experiment},
        "tolerance": tolerance,
        "rollback": rollback,
        "source": str(file_path),
    }


def evaluate_steady_state(baseline_metrics: dict, steady_state: dict) -> tuple[bool, list[str]]:
    """裁决稳态假设：baseline 指标必须全部越过底线。"""
    reasons: list[str] = []
    checks = {
        "tool_selection_accuracy_min": ("tool_selection_accuracy", "min"),
        "arg_accuracy_min": ("arg_accuracy", "min"),
        "retry_rate_max": ("retry_rate", "max"),
    }
    for threshold_key, (metric_key, direction) in checks.items():
        if threshold_key not in steady_state:
            continue
        threshold = steady_state[threshold_key]
        actual = baseline_metrics.get(metric_key)
        if actual is None:
            reasons.append(f"steady_state.{threshold_key}: baseline 缺少指标 {metric_key}")
        elif direction == "min" and actual < threshold:
            reasons.append(
                f"steady_state.{threshold_key}: baseline {metric_key}={actual:.4f} < {threshold}"
            )
        elif direction == "max" and actual > threshold:
            reasons.append(
                f"steady_state.{threshold_key}: baseline {metric_key}={actual:.4f} > {threshold}"
            )
    return (not reasons), reasons


def run_compare(experiment: dict) -> int:
    """以 YAML 参数驱动 chaos_compare.py，返回其退出码（报告总会落盘）。"""
    import os

    exp = experiment["method"]["experiment"]
    env = os.environ.copy()
    # 实验模式显式声明（YAML 单一来源）——阻断本地 .env 的 AGENT_MODE
    # 泄漏（曾致离线实验静默调用真实 LLM）
    env["AGENT_MODE"] = str(experiment["method"].get("mode", "rule"))
    for key, (env_name, _prefix) in _TOLERANCE_ENV.items():
        if key in experiment["tolerance"]:
            env[env_name] = str(experiment["tolerance"][key])
    proc = subprocess.run(
        [
            sys.executable,
            str(CHAOS_COMPARE_SCRIPT),
            "--chaos",
            str(exp["chaos"]),
            "--fail-rate",
            str(exp["fail_rate"]),
            "--latency-ms",
            str(exp["latency_ms"]),
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=env,
        timeout=int(env.get("CHAOS_SUBPROC_TIMEOUT_SEC", "1200")),
    )
    if proc.stdout:
        print(proc.stdout)
    if proc.returncode != 0 and proc.stderr:
        print(proc.stderr, file=sys.stderr)
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a declarative chaos experiment (YAML).")
    parser.add_argument("--experiment", default=str(DEFAULT_EXPERIMENT), help="实验定义 YAML 路径")
    args = parser.parse_args()

    try:
        experiment = load_experiment(args.experiment)
    except ExperimentDefinitionError as exc:
        print(f"[EXPERIMENT] invalid definition: {exc}", file=sys.stderr)
        return 2

    print(f"[EXPERIMENT] running {experiment['name']} ({experiment['source']})")
    import time

    started_at = time.time()
    compare_exit = run_compare(experiment)

    # 新鲜度守卫：chaos_compare 未产出"本轮"报告（服务不可达/运行崩溃）时，
    # 绝不能拿历史报告误判——曾实测：服务未起 + 读到 Aug15 旧报告 → 假 PASS。
    if (
        not COMPARE_JSON.is_file()
        or COMPARE_JSON.stat().st_mtime < started_at
    ):
        print(
            "[EXPERIMENT] chaos_compare 未产出本轮新报告"
            f"（exit={compare_exit}；检查 Chaos Service :5000 可达性，"
            "或离线验证设 SKIP_TOOLS_HEALTH_CHECK=1）",
            file=sys.stderr,
        )
        return 2
    compare = json.loads(COMPARE_JSON.read_text(encoding="utf-8"))

    steady_pass, steady_reasons = evaluate_steady_state(
        compare.get("baseline", {}), experiment["steady_state"]
    )
    gate = compare.get("token_black_hole_gate", {})
    tolerance_pass = bool(gate.get("pass"))
    tolerance_reasons: list[str] = []
    if not tolerance_pass:
        # YAML tolerance 声明的相对增量维度
        for key, (_env_name, gate_prefix) in _TOLERANCE_ENV.items():
            if gate.get(f"{gate_prefix}_pass") is False:
                tolerance_reasons.append(
                    f"{key}: ratio={gate.get(gate_prefix + '_ratio')} > max={gate.get(gate_prefix + '_max')}"
                )
        # chaos_compare 内建的绝对上限/重试税维度（不在 YAML 声明范围内，
        # 但失败时必须可见，避免"FAIL 却无原因"）
        _ABSOLUTE_GATE_FIELDS = {
            "token_max_per_task": "chaos_max_token_per_task",
            "token_p99_per_task": "chaos_p99_token_per_task",
            "retry_tax": "chaos_retry_tax_ratio",
        }
        for prefix, observed_field in _ABSOLUTE_GATE_FIELDS.items():
            if gate.get(f"{prefix}_pass") is False:
                tolerance_reasons.append(
                    f"{prefix}: observed={gate.get(observed_field)} > max={gate.get(prefix + '_max')}"
                )

    verdict = steady_pass and tolerance_pass
    report = {
        "experiment": experiment,
        "verdict": "PASS" if verdict else "FAIL",
        "steady_state_pass": steady_pass,
        "steady_state_reasons": steady_reasons,
        "tolerance_pass": tolerance_pass,
        "tolerance_reasons": tolerance_reasons,
        "baseline": compare.get("baseline", {}),
        "chaos": compare.get("chaos", {}),
        "delta": compare.get("delta", {}),
        "token_black_hole_gate": gate,
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = REPORT_DIR / f"experiment_{experiment['name']}_latest.json"
    out_md = REPORT_DIR / f"experiment_{experiment['name']}_latest.md"
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    out_md.write_text(_render_markdown(report), encoding="utf-8")

    print(f"[EXPERIMENT] verdict={report['verdict']} → {out_json}")
    if not verdict:
        for reason in steady_reasons + tolerance_reasons:
            print(f"  FAIL: {reason}")
        return 1
    return 0


def _render_markdown(report: dict) -> str:
    exp = report["experiment"]
    lines = [
        f"# Chaos Experiment: {exp['name']}",
        "",
        f"- verdict: **{report['verdict']}**",
        f"- definition: `{exp['source']}`",
        f"- description: {exp['description']}",
        "",
        "## Steady state（稳态假设）",
        "",
        f"- pass: {report['steady_state_pass']}",
    ]
    lines.extend(f"  - {r}" for r in report["steady_state_reasons"] or ["  (all thresholds met)"])
    lines.extend(
        [
            "",
            "## Tolerance（容忍上界）",
            "",
            f"- pass: {report['tolerance_pass']}",
        ]
    )
    lines.extend(f"  - {r}" for r in report["tolerance_reasons"] or ["  (all surges within tolerance)"])
    lines.extend(
        [
            "",
            "## Experiment",
            "",
            f"- mode: `{exp['method'].get('mode', 'rule')}`",
            f"- chaos: `{exp['method']['experiment']}`",
            f"- rollback: `{exp.get('rollback', {})}`",
            "",
            "## Delta (chaos - baseline)",
            "",
            "| Metric | Baseline | Chaos |",
            "|---|---:|---:|",
        ]
    )
    for key, value in report.get("delta", {}).items():
        if value is None:
            continue
        base = report["baseline"].get(key)
        chaos = report["chaos"].get(key)
        lines.append(f"| {key} | {base if base is not None else 'N/A'} | {chaos if chaos is not None else 'N/A'} |")
    return "\n".join(lines)


def _validate_section(raw, allowed_keys: set[str], section: str, *, required: bool) -> dict:
    if raw is None:
        if required:
            raise ExperimentDefinitionError(f"missing required section: {section}")
        return {}
    if not isinstance(raw, dict):
        raise ExperimentDefinitionError(f"{section} must be a mapping")
    unknown = set(raw) - allowed_keys
    if unknown:
        raise ExperimentDefinitionError(f"unknown keys in {section}: {sorted(unknown)}")
    return dict(raw)


def _as_float(value, name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ExperimentDefinitionError(f"{name} must be numeric, got {value!r}") from exc


if __name__ == "__main__":
    sys.exit(main())
