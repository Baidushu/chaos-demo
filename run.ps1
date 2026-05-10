param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("help", "up", "down", "test", "bench", "gate", "unified", "scan", "replay", "faultdemo", "qa", "qafull", "agenteval", "agentchaos", "agentvariance")]
    [string]$Task
)

# 压测后等服务就绪再扫：循环请求 /healthz，与 CI「wait for app」同类（重试 + 上限次数）
function Wait-AppHealthz {
    param(
        [int]$MaxAttempts = 30,
        [int]$IntervalSeconds = 2
    )
    $base = $env:SECURITY_SCAN_BASE_URL
    if (-not $base) { $base = "http://127.0.0.1:5000" }
    $url = ($base.TrimEnd("/") + "/healthz")
    for ($i = 1; $i -le $MaxAttempts; $i++) {
        try {
            $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
            if ($resp.StatusCode -eq 200) {
                Write-Host "[qa] healthz OK (attempt $i/$MaxAttempts) -> $url"
                return
            }
        } catch {
            Write-Host "[qa] healthz not ready ($i/$MaxAttempts): $($_.Exception.Message)"
        }
        if ($i -lt $MaxAttempts) {
            Start-Sleep -Seconds $IntervalSeconds
        }
    }
    throw "[qa] healthz did not return 200 after $MaxAttempts attempts: $url"
}

function Set-DefaultSecurityScanRetryEnv {
    if (-not $env:SECURITY_HEALTH_RETRY_ATTEMPTS) { $env:SECURITY_HEALTH_RETRY_ATTEMPTS = "5" }#重试次数
    if (-not $env:SECURITY_HEALTH_RETRY_DELAY_MS) { $env:SECURITY_HEALTH_RETRY_DELAY_MS = "500" }#重试间隔
}

function Set-DefaultBenchmarkEnv {
    # 与 .github/workflows/qa.yml 中 Benchmark 步一致，本地 bench/qa 可复现同类报告
    if (-not $env:BENCHMARK_WARMUP) { $env:BENCHMARK_WARMUP = "20" }#预热时间
    if (-not $env:BENCHMARK_SEED) { $env:BENCHMARK_SEED = "7" }
    if (-not $env:BENCHMARK_RUNS) { $env:BENCHMARK_RUNS = "3" }
}

function Set-DefaultAgentEvalEnv {
    # 与 .github/workflows/qa.yml「Agent eval」步一致，本地 agent* / qafull 可复现 CI
    if (-not $env:TOOLS_BASE_URL) { $env:TOOLS_BASE_URL = "http://127.0.0.1:5000" }
    if (-not $env:AGENT_MODE) { $env:AGENT_MODE = "rule" }#基于规则的规划器，而不是调用昂贵的 LLM（大模型）
    if (-not $env:AGENT_EVAL_SKIP_JUDGE) { $env:AGENT_EVAL_SKIP_JUDGE = "1" }#跳过判官，直接使用规则引擎
    if (-not $env:SECURITY_SCAN_BASE_URL) { $env:SECURITY_SCAN_BASE_URL = $env:TOOLS_BASE_URL }
}

function Set-DefaultQualityGateEnv {
    if (-not $env:QUALITY_GATE_CHECK_FRESHNESS) { $env:QUALITY_GATE_CHECK_FRESHNESS = "1" }#检查新鲜度
    if (-not $env:QUALITY_GATE_MAX_REPORT_AGE_SEC) { $env:QUALITY_GATE_MAX_REPORT_AGE_SEC = "3600" }#报告有效期（1 小时）
    if (-not $env:QUALITY_GATE_RETRY_ATTEMPTS) { $env:QUALITY_GATE_RETRY_ATTEMPTS = "2" }#如果读报告失败（例如文件被占用），门禁会重试 2 次。     
    if (-not $env:QUALITY_GATE_RETRY_DELAY_MS) { $env:QUALITY_GATE_RETRY_DELAY_MS = "1000" }#重试间隔
    if (-not $env:QUALITY_GATE_ERROR_RATE_MAX) { $env:QUALITY_GATE_ERROR_RATE_MAX = "0.05" }#错误率最大值
    if (-not $env:QUALITY_GATE_P99_MS_MAX) { $env:QUALITY_GATE_P99_MS_MAX = "450" }#99百分位最大值
    if (-not $env:QUALITY_GATE_P95_REGRESSION_FACTOR_MAX) { $env:QUALITY_GATE_P95_REGRESSION_FACTOR_MAX = "1.10" }#95百分位回归因子最大值
    if (-not $env:QUALITY_GATE_UNSTABLE_RATE_MAX) { $env:QUALITY_GATE_UNSTABLE_RATE_MAX = "0.35" }#不稳定率最大值
    if (-not $env:QUALITY_GATE_P95_STDEV_MAX) { $env:QUALITY_GATE_P95_STDEV_MAX = "0" }#95百分位标准差最大值
}

switch ($Task) {
    "help" {
        @"
可用 Task:
  help          本说明
  up / down     Docker Compose 启动 / 停止
  test          安装 dev 依赖并 pytest 全量（分层见 pytest.ini：-m smoke / contract）
  bench         benchmark_compare（默认注入 BENCHMARK_WARMUP/SEED/RUNS；输出多轮中位数、趋势与历史）
  gate          quality_gate（仅 benchmark+security；新鲜度/重试/阈值）
  unified       unified_quality_gate（汇总 PASS/FAIL JSON；需 bench+scan+通常 agent_eval_latest）
  qa            test + bench + 等待 healthz + scan + gate
  qafull        test + bench + 等待 healthz + scan + chaos_compare --strict + unified（对齐 CI）
  scan          安全扫描门禁（security_scan.py）
  replay        回放录制流量（无录制文件时可回放内置 sample-data）
  faultdemo     故障注入演示（注入延迟/丢包 → 观察降级 → 清除 → 观察恢复）
  agenteval     Agent：run + score + gate（起服务后执行；未设时注入与 CI 一致的 TOOLS/AGENT_*）
  agentchaos    chaos_compare（无故障 vs 混合故障对照；--strict 请见 CI 或手输）
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
        python -m pytest tests/ -q
    }
    "bench" {
        Set-DefaultBenchmarkEnv
        python benchmark_compare.py
    }
    "gate" {
        Set-DefaultQualityGateEnv
        python quality_gate.py
    }
    "unified" {
        Set-DefaultQualityGateEnv
        python unified_quality_gate.py
    }
    "scan" {
        Set-DefaultSecurityScanRetryEnv
        python security_scan.py
    }
    "replay" {
        python replay_traffic.py --input reports/traffic_record_latest.jsonl --base-url http://127.0.0.1:5000 --limit 100
    }
    "faultdemo" {
        python fault_demo.py --base-url http://127.0.0.1:5000
    }
    "qa" {
        python -m pip install -r requirements-dev.txt
        python -m pytest tests/ -q
        Set-DefaultBenchmarkEnv
        python benchmark_compare.py
        Wait-AppHealthz
        Set-DefaultSecurityScanRetryEnv
        python security_scan.py
        Set-DefaultQualityGateEnv
        python quality_gate.py
    }
    "qafull" {
        python -m pip install -r requirements-dev.txt
        python -m pytest tests/ -q
        Set-DefaultBenchmarkEnv
        python benchmark_compare.py
        Wait-AppHealthz
        Set-DefaultSecurityScanRetryEnv
        python security_scan.py
        Set-DefaultAgentEvalEnv
        Wait-AppHealthz
        python agent-eval/scripts/chaos_compare.py --strict
        Set-DefaultQualityGateEnv
        python unified_quality_gate.py
    }
    "agenteval" {
        Set-DefaultAgentEvalEnv
        Wait-AppHealthz
        python agent-eval/scripts/run_agent_eval.py
        python agent-eval/scripts/score_agent_eval.py
        python agent-eval/scripts/gate_agent_eval.py
    }
    "agentchaos" {
        Set-DefaultAgentEvalEnv
        Wait-AppHealthz
        python agent-eval/scripts/chaos_compare.py
    }
    "agentvariance" {
        Set-DefaultAgentEvalEnv
        Wait-AppHealthz
        python agent-eval/scripts/eval_variance.py --runs 3 --chaos mixed --fail-rate 0.45 --latency-ms 180
    }
}
