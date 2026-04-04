param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("help", "up", "down", "test", "bench", "gate", "scan", "replay", "qa", "agenteval", "agentchaos", "agentvariance")]
    [string]$Task
)

switch ($Task) {
    "help" {
        @"
可用 Task:
  help          本说明
  up / down     Docker Compose 启动 / 停止
  test          安装 dev 依赖并 pytest
  bench         benchmark_compare
  gate          quality_gate（含安全报告校验）
  qa            test + bench + scan + gate（服务侧 QA + 安全门禁）
  scan          安全扫描门禁（security_scan.py）
  replay        回放录制流量（replay_traffic.py）
  agenteval     Agent：run + score + gate
  agentchaos    chaos_compare（无故障 vs 混合故障对照）
  agentvariance eval_variance（3 轮 mixed，看波动）
"@
    }
    "up" {
        docker compose up --build -d
    }
    "down" {
        docker compose down
    }
    "test" {
        python -m pip install -r requirements-dev.txt
        python -m pytest -q
    }
    "bench" {
        python benchmark_compare.py
    }
    "gate" {
        python quality_gate.py
    }
    "scan" {
        python security_scan.py
    }
    "replay" {
        python replay_traffic.py --input reports/traffic_record_latest.jsonl --base-url http://127.0.0.1:5000 --limit 100
    }
    "qa" {
        python -m pip install -r requirements-dev.txt
        python -m pytest -q
        python benchmark_compare.py
        python security_scan.py
        python quality_gate.py
    }
    "agenteval" {
        python agent-eval/scripts/run_agent_eval.py
        python agent-eval/scripts/score_agent_eval.py
        python agent-eval/scripts/gate_agent_eval.py
    }
    "agentchaos" {
        python agent-eval/scripts/chaos_compare.py
    }
    "agentvariance" {
        python agent-eval/scripts/eval_variance.py --runs 3 --chaos mixed --fail-rate 0.45 --latency-ms 180
    }
}
