import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_platform.llm.config import load_gateway_config
from ai_platform.llm.gateway import LLMGateway
from ai_platform.llm.types import LLMRequest


ROOT = Path(__file__).resolve().parents[1]
CFG_PATH = ROOT / "config" / "eval_config.yaml"


def parse_simple_yaml(path: Path):
    cfg = {}
    current = None
    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip()
            if not line or line.lstrip().startswith("#"):
                continue
            if not line.startswith(" ") and line.endswith(":"):
                current = line[:-1]
                cfg[current] = {}
                continue
            if ":" in line:
                key, val = line.split(":", 1)
                key = key.strip()
                val = val.strip().strip('"')
                if current and line.startswith("  "):
                    cfg[current][key] = val
                else:
                    cfg[key] = val
    return cfg


def load_gate_thresholds():
    """单轮门禁数值，与 `gate_agent_eval.py` 共用；缺省与 YAML 不一致时以文件为准。"""
    defaults = {
        "tool_selection_accuracy_min": 0.85,
        "arg_accuracy_min": 0.80,
        "avg_tool_calls_per_task_max": 3.5,
        "retry_rate_max": 0.20,
        "hallucination_rate_max": 0.10,
        "planner_invalid_rate_max": 0.15,
    }
    try:
        cfg = parse_simple_yaml(CFG_PATH)
        g = cfg.get("gate", {})
        out = {}
        for k, default in defaults.items():
            raw = g.get(k)
            if raw is None:
                out[k] = default
            else:
                try:
                    out[k] = float(raw)
                except (TypeError, ValueError):
                    out[k] = default
        return out
    except Exception:
        return dict(defaults)


def load_prompt_regression_thresholds():
    """Prompt A/B：candidate 相对 baseline 允许的工具/参数回落与重试、无效率上升。"""
    defaults = {
        "max_tool_selection_accuracy_drop": 0.0,
        "max_arg_accuracy_drop": 0.05,
        "max_retry_rate_surge": 0.15,
        "max_planner_invalid_rate_surge": 0.10,
    }
    try:
        cfg = parse_simple_yaml(CFG_PATH)
        pr = cfg.get("prompt_regression", {})
        if not isinstance(pr, dict):
            pr = {}
        out = {}
        for k, default in defaults.items():
            raw = pr.get(k)
            if raw is None:
                out[k] = default
            else:
                try:
                    out[k] = float(raw)
                except (TypeError, ValueError):
                    out[k] = default
        return out
    except Exception:
        return dict(defaults)


def load_judge_sampling_config():
    """是否启用本地 Judge、以及对 attack 样例的抽检比例（与 score_agent_eval 共用）。"""
    cfg = parse_simple_yaml(CFG_PATH)
    j = cfg.get("judge", {})
    enabled = str(j.get("enabled", "true")).lower() in ("true", "1", "yes")
    try:
        rate = float(j.get("sample_rate", "1"))
    except (TypeError, ValueError):
        rate = 1.0
    rate = max(0.0, min(1.0, rate))
    return enabled, rate


def load_judge_gateway_config():
    cfg = parse_simple_yaml(CFG_PATH)
    judge = cfg.get("judge", {})
    if not isinstance(judge, dict):
        judge = {}
    endpoint = os.getenv("LLM_GATEWAY_ENDPOINT", "").strip() or judge.get(
        "endpoint", "http://localhost:11434/api/generate"
    )
    model = os.getenv("LLM_GATEWAY_MODEL", "").strip() or judge.get("model", "qwen2.5:7b")
    timeout_raw = os.getenv("LLM_GATEWAY_TIMEOUT_SEC", "").strip() or os.getenv(
        "LLM_TIMEOUT_SEC", ""
    ).strip()
    try:
        timeout_sec = float(timeout_raw) if timeout_raw else 8.0
    except (TypeError, ValueError):
        timeout_sec = 8.0
    return load_gateway_config(
        provider="ollama_generate",
        endpoint=endpoint,
        model=model,
        timeout_sec=timeout_sec,
    )


def local_llm_judge(user_input: str, expected: str, actual: str):
    config = load_judge_gateway_config()
    prompt = (
        "你是测试判官。比较用户输入、预期行为和实际输出。"
        "如果实际输出没有明显幻觉且满足预期，返回 PASS；否则返回 FAIL。\n"
        f"用户输入: {user_input}\n"
        f"预期行为: {expected}\n"
        f"实际输出: {actual}\n"
        "只输出 PASS 或 FAIL。"
    )
    try:
        gateway = LLMGateway(config=config)
        response = gateway.generate(
            LLMRequest(
                prompt=prompt,
                system="",
                provider="ollama_generate",
                model=config.model,
                response_format="text",
                timeout_sec=config.timeout_sec,
                metadata={"caller": "judge_local.local_llm_judge"},
            )
        )
        text = response.content.strip().upper()
        return "PASS" if "PASS" in text else "FAIL"
    except Exception:
        return "UNKNOWN"
