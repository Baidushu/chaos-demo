from __future__ import annotations

import os
from pathlib import Path

from ai_platform.evaluation.legacy_adapter import score_agent_eval as run_score_agent_eval
from ai_platform.evaluation.metrics import arg_match, avg_or_none, percentile_or_none, tool_match

SKIP_JUDGE = os.getenv("AGENT_EVAL_SKIP_JUDGE", "").lower() in ("1", "true", "yes")

from judge_local import load_judge_sampling_config


ROOT = Path(__file__).resolve().parents[1]
RAW_DEFAULT = ROOT / "reports" / "agent_raw_latest.json"
SCORE_DEFAULT = ROOT / "reports" / "agent_eval_latest.json"
MD_DEFAULT = ROOT / "reports" / "agent_eval_latest.md"
REVIEW_DEFAULT = ROOT / "reports" / "manual_review_pool.jsonl"


def main() -> None:
    seed = int(os.getenv("EVAL_SEED", "42"))
    judge_enabled, judge_sample_rate = load_judge_sampling_config()
    raw_path = Path(os.getenv("AGENT_EVAL_RAW_JSON", str(RAW_DEFAULT)))
    score_path = Path(os.getenv("AGENT_EVAL_SCORE_JSON", str(SCORE_DEFAULT)))
    md_env = os.getenv("AGENT_EVAL_SCORE_MD")
    md_path = Path(md_env) if md_env else score_path.with_suffix(".md")
    review_path = Path(os.getenv("AGENT_EVAL_REVIEW_POOL_JSON", str(REVIEW_DEFAULT)))

    result = run_score_agent_eval(
        raw_path=raw_path,
        score_path=score_path,
        md_path=md_path,
        review_path=review_path,
        judge_enabled=judge_enabled,
        judge_sample_rate=judge_sample_rate,
        skip_judge=SKIP_JUDGE,
        seed=seed,
    )
    report = {
        key[len("score.") :]: value
        for key, value in result.metrics.items()
        if key.startswith("score.")
    }
    print(f"Saved score json: {score_path}")
    print(f"Saved score md: {md_path}")
    print(f"Saved review pool: {review_path}")
    if report:
        print(
            "[AGENT_EVAL] "
            f"tool_acc={report['tool_selection_accuracy']:.2%}, "
            f"arg_acc={report['arg_accuracy']:.2%}, "
            f"retry_rate={report['retry_rate']:.2%}, "
            f"planner_invalid={report['planner_invalid_rate']:.2%}"
        )


if __name__ == "__main__":
    main()
