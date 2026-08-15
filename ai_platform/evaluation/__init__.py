"""Enterprise AI evaluation framework — ai_platform.evaluation.

Directory-aligned sub-structure:
  engine/     — EvaluationEngine
  metrics/    — tool_match, arg_match, avg_or_none, percentile_or_none
  judges/     — JudgeEvaluator (from evaluator.py)
  regression/ — RegressionEvaluator, compare_prompt_regression_scores (from evaluator.py)
  dataset/    — load_json, write_json, write_jsonl
  report/     — score_agent_eval, evaluate_prompt_regression

Files kept at package root:
  evaluator.py — BaseEvaluator, JudgeEvaluator, ScoreEvaluator, RegressionEvaluator
  gate.py      — QualityGate, AgentGateError
  result.py    — EvaluationResult
"""

from ai_platform.evaluation.engine import EvaluationEngine
from ai_platform.evaluation.evaluator import (
    BaseEvaluator,
    JudgeEvaluator,
    RegressionEvaluator,
    ScoreEvaluator,
)
from ai_platform.evaluation.gate import AgentGateError, QualityGate
from ai_platform.evaluation.result import EvaluationResult
from ai_platform.evaluation.dataset import load_json, write_json, write_jsonl

__all__ = [
    "AgentGateError",
    "BaseEvaluator",
    "EvaluationEngine",
    "EvaluationResult",
    "JudgeEvaluator",
    "QualityGate",
    "RegressionEvaluator",
    "ScoreEvaluator",
    "load_json",
    "write_json",
    "write_jsonl",
]
