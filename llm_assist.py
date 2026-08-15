"""LLM 辅助测试工具 — 测开向「AI 素养」能力：生成用例、分析报告/日志、补全 case、读代码、契约审计。

子命令：
- generate-tests: 从内置 API 描述生成 pytest 草稿（需人审 + pytest；依赖仓库 conftest 提供的 `client` 夹具）
- analyze-report: 分析 benchmark / security 等 JSON 报告
- analyze-logs: 抽样 JSON 行日志，归纳异常与可观测性建议（勿把含密钥的原始日志上传公网模型）
- complete-cases: 按 jsonl（agent-eval tool_eval）或 yaml（api-automation）风格**建议**新用例草稿
- explain-code: 读取源码片段，辅助理解与重构提问
- contract-audit: 对照契约测试与 API 说明，列出缺口与建议（草稿）

用法示例：
    python llm_assist.py generate-tests
    python llm_assist.py analyze-report --report reports/benchmark_latest.json
    python llm_assist.py analyze-logs --input reports/traffic_record_latest.jsonl
    python llm_assist.py complete-cases --format jsonl --input agent-eval/datasets/tool_eval.jsonl -n 2
    python llm_assist.py complete-cases --format yaml --input api-automation-demo/data/api_cases.yaml -n 2
    python llm_assist.py explain-code --path chaos_service/resilience.py --question 限流 fail-open 在哪
    python llm_assist.py contract-audit --contract tests/test_api_contract.py

环境变量见 llm_client.py（LLM_BACKEND / LLM_API_KEY / Ollama 等）。

**注意**：所有 LLM 输出均为草稿，须经过人工审查、单测与门禁；CI 主链默认不依赖本脚本。根目录 `conftest.py` 会加载 `tests.conftest`，因此 `--output` 写到 `reports/` 等目录时同样能解析 `client`。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sys
import urllib.request
from pathlib import Path

from ai_platform.llm.config import GatewayConfig, load_gateway_config
from ai_platform.llm.gateway import LLMGateway
from ai_platform.llm.types import LLMError, LLMRequest

REPORT_DIR = Path("reports")


class GatewayLLMClient:
    def __init__(self) -> None:
        self._config, self._backend = self._resolve_config()
        self._gateway = LLMGateway(config=self._config)

    @property
    def backend(self) -> str:
        return self._backend

    @property
    def model(self) -> str:
        return self._config.model

    def chat(self, prompt: str, system: str = "", max_tokens: int = 2000) -> str:
        request = LLMRequest(
            prompt=prompt,
            system=system,
            model=self._config.model,
            provider=self._config.provider,
            response_format="text",
            timeout_sec=self._config.timeout_sec,
            metadata={
                "caller": "llm_assist",
                "max_tokens": max_tokens,
            },
        )
        try:
            response = self._gateway.generate(request)
            return response.content
        except LLMError as exc:
            raise RuntimeError(exc.message) from exc

    def _resolve_config(self) -> tuple[GatewayConfig, str]:
        explicit_provider = os.getenv("LLM_GATEWAY_PROVIDER", "").strip()
        if explicit_provider:
            config = load_gateway_config()
            self._validate_config(config, backend_name=_legacy_backend_name(config.provider))
            return config, _legacy_backend_name(config.provider)

        backend = os.getenv("LLM_BACKEND", "auto").strip().lower()
        api_key = os.getenv("LLM_API_KEY", "").strip()
        if backend == "auto":
            if _check_ollama_available():
                config = load_gateway_config(provider="ollama_chat")
                return config, "ollama"
            if api_key:
                config = load_gateway_config(provider="openai_compatible")
                self._validate_config(config, backend_name="openai")
                return config, "openai"
            raise ValueError(
                "No LLM backend available. Either:\n"
                "  1. Start Ollama: ollama serve && ollama pull qwen2.5:7b\n"
                "  2. Set LLM_API_KEY for cloud API (Qwen/DeepSeek)"
            )

        if backend == "ollama":
            return load_gateway_config(provider="ollama_chat"), "ollama"
        if backend == "openai":
            config = load_gateway_config(provider="openai_compatible")
            self._validate_config(config, backend_name="openai")
            return config, "openai"

        config = load_gateway_config(provider=backend)
        self._validate_config(config, backend_name=_legacy_backend_name(config.provider))
        return config, _legacy_backend_name(config.provider)

    @staticmethod
    def _validate_config(config: GatewayConfig, *, backend_name: str) -> None:
        if config.provider == "openai_compatible" and not config.api_key:
            raise ValueError(
                "LLM_API_KEY is required for cloud backend. "
                "Get a free key from https://dashscope.console.aliyun.com/ "
                "or set LLM_BACKEND=ollama for local model."
            )
        if backend_name == "mock" and not config.model:
            raise ValueError("LLM mock provider requires a model name")


def _legacy_backend_name(provider_name: str) -> str:
    if provider_name == "openai_compatible":
        return "openai"
    if provider_name.startswith("ollama"):
        return "ollama"
    return provider_name


def _check_ollama_available() -> bool:
    try:
        endpoint = os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434").rstrip("/")
        req = urllib.request.Request(f"{endpoint}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.getcode() == 200
    except (OSError, RuntimeError, TimeoutError, socket.timeout):
        return False
    except Exception:
        return False


def get_client() -> GatewayLLMClient:
    try:
        return GatewayLLMClient()
    except (ValueError, LLMError) as e:
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


def generate_tests(client: GatewayLLMClient) -> str:
    print(f"[llm_assist] generating tests with {client.backend}/{client.model} ...")
    system = "你是测开专家，输出高质量的 pytest 测试代码。只输出 Python 代码，不要解释。"
    return client.chat(GENERATE_TESTS_PROMPT, system=system, max_tokens=3000)


def build_analysis_prompt(report_data: dict, report_type: str) -> str:
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
    if report_type == "security":
        return f"""分析以下安全扫描报告，给出：
1. 发现的安全问题解读
2. 风险等级评估
3. 修复建议
4. 是否有误报可能

报告数据：
{report_json}

用中文回答，结构化输出。"""
    return f"""分析以下测试报告，识别异常指标，给出根因假设和改进建议。

报告数据：
{report_json}

用中文回答，结构化输出。"""


def _report_type_from_path(path: Path, data: dict) -> str:
    name = path.name.lower()
    if "security" in name:
        return "security"
    if "benchmark_trend" in name or "trend" in name and "benchmark" in name:
        return "unknown"
    if isinstance(data, dict) and "protected" in data and "baseline" in data:
        return "benchmark"
    if "benchmark" in name:
        return "benchmark"
    return "unknown"


def analyze_report(client: GatewayLLMClient, report_path: str) -> str:
    path = Path(report_path)
    if not path.exists():
        print(f"[llm_assist] ERROR: report not found: {report_path}", file=sys.stderr)
        sys.exit(1)

    data = json.loads(path.read_text(encoding="utf-8"))
    report_type = _report_type_from_path(path, data)

    print(f"[llm_assist] analyzing ({report_type}) {path.name} with {client.backend}/{client.model} ...")
    prompt = build_analysis_prompt(data, report_type)
    system = "你是资深 SRE 和测开专家，擅长分析性能和安全报告。"
    return client.chat(prompt, system=system, max_tokens=2000)


def read_log_sample(path: Path, max_lines: int = 80, max_chars: int = 28000) -> str:
    """从 JSONL/行日志文件**尾部**抽样，控制体积（便于 LLM 与用户脱敏）。"""
    if not path.is_file():
        raise FileNotFoundError(str(path))
    lines: list[str] = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            s = line.rstrip("\n")
            if s.strip():
                lines.append(s)
    tail = lines[-max_lines:] if len(lines) > max_lines else lines
    text = "\n".join(tail)
    if len(text) > max_chars:
        text = text[-max_chars:]
        text = "…(仅保留文件末尾一段，已截断)\n" + text
    return text


def analyze_logs(
    client: GatewayLLMClient,
    log_path: str,
    *,
    max_lines: int = 80,
) -> str:
    path = Path(log_path)
    sample = read_log_sample(path, max_lines=max_lines)
    print(f"[llm_assist] analyzing log sample from {path} with {client.backend}/{client.model} ...")
    prompt = f"""下面是应用/流量**抽样日志行**（可能为 JSON 行混排）。请用中文结构化输出：

1. 时间线与请求模式（若可从字段推断）
2. 错误、4xx/5xx、超时、降级（circuit、rate limit、queued）等异常簇
3. 与可观测性相关的建议（应打什么指标、什么日志字段、如何做告警分级）
4. **说明**：此为抽样，结论仅为假设，需对照全量日志与指标验证

抽样内容：
{sample}
"""
    system = "你是 SRE + 测开，擅长从日志归纳问题与可观测缺口。不要编造未出现在抽样中的具体 request_id。"
    return client.chat(prompt, system=system, max_tokens=2500)


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars // 2] + "\n…[中间已省略]…\n" + text[-max_chars // 2 :]


def explain_code(
    client: GatewayLLMClient,
    code_path: str,
    *,
    question: str | None = None,
    max_chars: int = 14000,
) -> str:
    path = Path(code_path)
    if not path.is_file():
        print(f"[llm_assist] ERROR: file not found: {code_path}", file=sys.stderr)
        sys.exit(1)
    raw = path.read_text(encoding="utf-8", errors="replace")
    body = _truncate(raw, max_chars)
    q = question or "请总结模块职责、关键函数与扩展时容易踩的坑。"
    print(f"[llm_assist] explaining {path} with {client.backend}/{client.model} ...")
    prompt = f"""文件路径：`{path}`

用户问题：{q}

--- 源码（可能已截断）---
{body}
"""
    system = "你是资深 Python 工程师，回答准确、分点说明，不确定处请标明假设。"
    return client.chat(prompt, system=system, max_tokens=2500)


def complete_cases_jsonl(client: GatewayLLMClient, input_path: Path, n: int) -> str:
    lines = [ln.strip() for ln in input_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    sample = lines[-8:] if len(lines) > 8 else lines
    existing_ids = []
    for ln in lines:
        try:
            existing_ids.append(json.loads(ln).get("id", ""))
        except json.JSONDecodeError:
            pass
    sample_txt = "\n".join(sample)
    print(f"[llm_assist] suggesting {n} new jsonl cases with {client.backend}/{client.model} ...")
    prompt = f"""现有 agent-eval tool_eval JSONL 样例（每行一个 JSON）：
{sample_txt}

已有 id 包含：{existing_ids[:20]}{'...' if len(existing_ids) > 20 else ''}

请再设计 **{n}** 条新用例（边界/攻击/异常输入/澄清），字段必须严格为：
id（新 id，不要用 case-001 等已占用形式）、category、input、expected_tools（字符串数组）、expected_args（对象）、forbidden_behavior（字符串数组）

**只输出**一个 JSON 数组（不要 markdown 围栏，不要解释）。"""
    system = "你只输出合法 JSON 数组，ASCII 外中文可保留，不要其它文字。"
    text = client.chat(prompt, system=system, max_tokens=3000)
    m = re.search(r"(\[[\s\S]*\])", text)
    if not m:
        return text
    try:
        arr = json.loads(m.group(1))
        if not isinstance(arr, list):
            return text
        return "\n".join(json.dumps(obj, ensure_ascii=False) for obj in arr) + "\n"
    except json.JSONDecodeError:
        return text


def complete_cases_yaml(client: GatewayLLMClient, input_path: Path, n: int) -> str:
    head = input_path.read_text(encoding="utf-8", errors="replace")
    head = _truncate(head, 12000)
    print(f"[llm_assist] suggesting {n} YAML cases with {client.backend}/{client.model} ...")
    prompt = f"""下面是 api-automation-demo 风格的 `api_cases.yaml` 片段（字段含 suite、cases[].id/name/method/path/headers/json_body/retry/mock/assertions 等）：

{head}

请再设计 **{n}** 个新 case，与现有 id 不重复。输出 **仅**一个 ```yaml 代码块，块内为可被合并进 `cases:` 列表的 YAML 列表项（每条以 `- id:` 开头），不要 suite 根键。
若无法生成合法 YAML，说明原因。"""
    system = "你是测开，熟悉 httpx/pytest 数据驱动，只输出可合并的 YAML 列表。"
    text = client.chat(prompt, system=system, max_tokens=3500)
    m = re.search(r"```yaml\s*([\s\S]*?)```", text, re.IGNORECASE)
    return m.group(1).strip() + "\n" if m else text


def contract_audit(client: GatewayLLMClient, contract_path: Path) -> str:
    if not contract_path.is_file():
        print(f"[llm_assist] ERROR: contract file not found: {contract_path}", file=sys.stderr)
        sys.exit(1)
    ct = _truncate(contract_path.read_text(encoding="utf-8", errors="replace"), 16000)
    print(f"[llm_assist] contract audit with {client.backend}/{client.model} ...")
    prompt = f"""API 约定摘要：
{API_DESCRIPTION}

以下为 `test_api_contract.py`（契约回归）源码摘录：
{ct}

请用中文输出：
1. 契约用例已覆盖的 HTTP/JSON 行为清单（简要）
2. 相对上述 API 说明仍可能缺失的契约场景（幂等、429/503、202、/fault、X-Request-Id 等）
3. 建议补的 pytest 或接口自动化 case 标题列表（不必写全代码）
4. 哪些是**必须人工确认**后再自动化（避免 LLM 误判）

标注：此为辅助审计草稿，不能替代 code review。"""
    system = "你是懂 Flask/REST 的测开 + 架构评审助理。"
    return client.chat(prompt, system=system, max_tokens=3000)


def _clean_python_fence(code: str) -> str:
    cleaned = re.sub(r"^```python\s*", "", code, flags=re.MULTILINE)
    cleaned = re.sub(r"^```\s*$", "", cleaned, flags=re.MULTILINE)
    return cleaned.strip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM-assisted testing & QE helpers (optional, offline from CI)")
    sub = parser.add_subparsers(dest="command")

    gen = sub.add_parser("generate-tests", help="Generate pytest draft from embedded API spec")
    gen.add_argument(
        "--output",
        default="tests/test_llm_generated.py",
        help="Output path (.py). 默认在 tests/；写到 reports/ 亦可（根 conftest 会挂载 tests 里的 client 夹具）",
    )

    ana = sub.add_parser("analyze-report", help="Analyze benchmark/security JSON report")
    ana.add_argument("--report", required=True, help="Report JSON path")
    ana.add_argument("--output", help="Also save analysis to this path")

    logp = sub.add_parser("analyze-logs", help="Sample JSONL/log file and summarize patterns")
    logp.add_argument("--input", required=True, help="Log file path (e.g. reports/*.jsonl)")
    logp.add_argument("--max-lines", type=int, default=80, help="Max tail lines to send to LLM")
    logp.add_argument("--output", help="Save markdown to path (default: reports/llm_log_analysis_latest.md)")

    cc = sub.add_parser("complete-cases", help="Suggest new cases for tool_eval JSONL or api_cases YAML")
    cc.add_argument("--format", choices=("jsonl", "yaml"), required=True)
    cc.add_argument("--input", required=True, help="Source dataset path")
    cc.add_argument("-n", type=int, default=2, dest="n_suggest", help="Number of suggested cases")
    cc.add_argument("--output", help="Write suggestions here (default under reports/)")

    ex = sub.add_parser("explain-code", help="LLM-assisted code reading for one file")
    ex.add_argument("--path", required=True, help="Source file path")
    ex.add_argument("--question", default=None, help="Optional focus question")
    ex.add_argument("--max-chars", type=int, default=14000, help="Max chars of file read")
    ex.add_argument("--output", help="Save to file (default: reports/llm_code_explain_latest.md)")

    ca = sub.add_parser("contract-audit", help="Gap analysis: contract tests vs API spec")
    ca.add_argument("--contract", default="tests/test_api_contract.py", help="Contract test file")
    ca.add_argument("--output", help="Save to file (default: reports/llm_contract_audit_latest.md)")

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
        output.write_text(_clean_python_fence(code), encoding="utf-8")
        print(f"[llm_assist] saved: {output}")
        print(f"[llm_assist] run with: python -m pytest {output} -v")

    elif args.command == "analyze-report":
        analysis = analyze_report(client, args.report)
        if args.output:
            Path(args.output).write_text(analysis, encoding="utf-8")
            print(f"[llm_assist] saved: {args.output}")
        else:
            print("\n" + "=" * 60 + "\n" + analysis + "\n" + "=" * 60)
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        side = REPORT_DIR / "llm_analysis_latest.md"
        side.write_text(analysis, encoding="utf-8")
        print(f"[llm_assist] saved: {side}")

    elif args.command == "analyze-logs":
        try:
            analysis = analyze_logs(client, args.input, max_lines=args.max_lines)
        except FileNotFoundError as e:
            print(f"[llm_assist] ERROR: {e}", file=sys.stderr)
            sys.exit(1)
        out = Path(args.output) if args.output else REPORT_DIR / "llm_log_analysis_latest.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(analysis, encoding="utf-8")
        print(f"[llm_assist] saved: {out}")

    elif args.command == "complete-cases":
        src = Path(args.input)
        if not src.is_file():
            print(f"[llm_assist] ERROR: not found: {src}", file=sys.stderr)
            sys.exit(1)
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        if args.format == "jsonl":
            text = complete_cases_jsonl(client, src, args.n_suggest)
            out = Path(args.output) if args.output else REPORT_DIR / "llm_tool_eval_suggested.jsonl"
        else:
            text = complete_cases_yaml(client, src, args.n_suggest)
            out = Path(args.output) if args.output else REPORT_DIR / "llm_api_cases_suggested.yaml"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"[llm_assist] saved: {out}")
        print("[llm_assist] 请人工审查后再合并进正式数据集 / 跑 pytest。")

    elif args.command == "explain-code":
        body = explain_code(client, args.path, question=args.question, max_chars=args.max_chars)
        out = Path(args.output) if args.output else REPORT_DIR / "llm_code_explain_latest.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(body, encoding="utf-8")
        print(f"[llm_assist] saved: {out}")

    elif args.command == "contract-audit":
        body = contract_audit(client, Path(args.contract))
        out = Path(args.output) if args.output else REPORT_DIR / "llm_contract_audit_latest.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(body, encoding="utf-8")
        print(f"[llm_assist] saved: {out}")


if __name__ == "__main__":
    main()
