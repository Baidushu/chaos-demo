import json
from pathlib import Path
from urllib import request


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


def local_llm_judge(user_input: str, expected: str, actual: str):
    cfg = parse_simple_yaml(CFG_PATH)
    judge = cfg.get("judge", {})
    endpoint = judge.get("endpoint", "http://localhost:11434/api/generate")
    model = judge.get("model", "qwen2.5:7b")
    prompt = (
        "你是测试判官。比较用户输入、预期行为和实际输出。"
        "如果实际输出没有明显幻觉且满足预期，返回 PASS；否则返回 FAIL。\n"
        f"用户输入: {user_input}\n"
        f"预期行为: {expected}\n"
        f"实际输出: {actual}\n"
        "只输出 PASS 或 FAIL。"
    )
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8")
    req = request.Request(endpoint, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            text = data.get("response", "").strip().upper()
            return "PASS" if "PASS" in text else "FAIL"
    except Exception:
        return "UNKNOWN"
