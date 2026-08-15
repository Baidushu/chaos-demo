from ai_platform.llm.types import LLMError, LLMRequest, LLMResponse


def test_llm_request_defaults():
    request = LLMRequest(prompt="hello")
    assert request.prompt == "hello"
    assert request.system == ""
    assert request.provider is None
    assert request.response_format == "text"
    assert request.metadata == {}


def test_llm_response_fields():
    response = LLMResponse(
        content="ok",
        parsed_json={"status": "ok"},
        provider="mock",
        model="mock-model",
        latency_ms=1.5,
        raw={"source": "unit-test"},
        total_tokens=10,
    )
    assert response.content == "ok"
    assert response.parsed_json == {"status": "ok"}
    assert response.provider == "mock"
    assert response.model == "mock-model"
    assert response.total_tokens == 10


def test_llm_error_is_exception():
    err = LLMError(
        provider="mock",
        model="demo",
        error_type="mock_failure",
        retryable=False,
        message="boom",
    )
    assert isinstance(err, Exception)
    assert str(err) == "boom"
    assert err.provider == "mock"
    assert err.retryable is False


def test_llm_error_all_fields():
    """All constructor fields are preserved as attributes."""
    err = LLMError(
        provider="ollama",
        model="llama3",
        error_type="timeout",
        retryable=True,
        message="request timed out after 30s",
        raw={"http_status": 504, "url": "http://localhost:11434"},
    )
    assert err.provider == "ollama"
    assert err.model == "llama3"
    assert err.error_type == "timeout"
    assert err.retryable is True
    assert err.message == "request timed out after 30s"
    assert err.raw == {"http_status": 504, "url": "http://localhost:11434"}


def test_llm_error_str_is_message():
    """str(err) returns the message field, consistent with Exception."""
    err = LLMError(
        provider="p", model="m", error_type="e",
        retryable=False, message="custom message",
    )
    assert str(err) == "custom message"


def test_llm_error_repr():
    """repr includes all key fields for debugging."""
    err = LLMError(
        provider="openai", model="gpt-4", error_type="rate_limit",
        retryable=True, message="rate limited",
    )
    r = repr(err)
    assert "LLMError" in r
    assert "openai" in r
    assert "gpt-4" in r
    assert "rate_limit" in r
    assert "retryable=True" in r
    assert "rate limited" in r


def test_llm_error_can_raise_and_catch():
    """LLMError can be raised and caught as a normal Exception."""
    raised = False
    try:
        raise LLMError(
            provider="test", model="x", error_type="fatal",
            retryable=False, message="test error",
        )
    except LLMError as e:
        raised = True
        assert isinstance(e, Exception)
        assert str(e) == "test error"
    assert raised, "LLMError was not raised"


def test_llm_error_exception_chaining():
    """LLMError can be used as __cause__ in exception chains."""
    try:
        try:
            raise LLMError(
                provider="inner", model="m", error_type="inner_err",
                retryable=True, message="root cause",
            )
        except LLMError as inner:
            raise RuntimeError("wrapper error") from inner
    except RuntimeError as outer:
        assert isinstance(outer.__cause__, LLMError)
        assert str(outer.__cause__) == "root cause"


def test_llm_error_default_raw_is_none():
    """When raw is omitted, it defaults to None."""
    err = LLMError(
        provider="p", model="m", error_type="e",
        retryable=False, message="msg",
    )
    assert err.raw is None


def test_llm_error_retryable_can_be_true():
    """retryable=True means the caller should retry."""
    err = LLMError(
        provider="p", model="m", error_type="timeout",
        retryable=True, message="timeout",
    )
    assert err.retryable is True


def test_llm_error_isinstance_exception():
    """LLMError is a proper Exception subclass (not just has __bases__)."""
    err = LLMError(
        provider="p", model="m", error_type="e",
        retryable=False, message="msg",
    )
    # Check direct isinstance
    assert isinstance(err, Exception)
    # Check caught by base handler
    try:
        raise err
    except Exception:
        pass  # should catch
    else:
        raise AssertionError("LLMError not caught by except Exception")


def test_llm_error_kwargs_only():
    """LLMError.__init__ uses keyword-only arguments (after *)."""
    import inspect
    sig = inspect.signature(LLMError.__init__)
    for name in ("provider", "model", "error_type", "retryable", "message", "raw"):
        param = sig.parameters[name]
        assert param.kind == inspect.Parameter.KEYWORD_ONLY, (
            f"{name} should be KEYWORD_ONLY, got {param.kind}"
        )
