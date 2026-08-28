"""Tests for Docker deployment configuration.

Validates:
  - Docker files exist and are well-formed
  - docker-compose configuration is correct
  - Environment variables are fully documented
  - .dockerignore covers expected patterns
"""

import os
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class TestDockerFilesExist:
    def test_dockerfile_ai_exists(self):
        path = PROJECT_ROOT / "Dockerfile.ai"
        assert path.exists(), f"Missing: {path}"

    def test_docker_compose_ai_exists(self):
        path = PROJECT_ROOT / "docker-compose.ai.yml"
        assert path.exists(), f"Missing: {path}"

    def test_dockerignore_exists(self):
        path = PROJECT_ROOT / ".dockerignore"
        assert path.exists(), f"Missing: {path}"

    def test_requirements_ai_exists(self):
        path = PROJECT_ROOT / "requirements-ai.txt"
        assert path.exists(), f"Missing: {path}"

    def test_env_example_exists(self):
        path = PROJECT_ROOT / ".env.example"
        assert path.exists(), f"Missing: {path}"


class TestDockerfileContent:
    def test_dockerfile_starts_from_python(self):
        content = (PROJECT_ROOT / "Dockerfile.ai").read_text(encoding="utf-8")
        assert "FROM python:" in content, "Dockerfile must start from python base image"

    def test_dockerfile_uses_slim_image(self):
        content = (PROJECT_ROOT / "Dockerfile.ai").read_text(encoding="utf-8")
        assert "slim" in content, "Should use slim image for smaller image size"

    def test_dockerfile_copies_ai_platform_api(self):
        content = (PROJECT_ROOT / "Dockerfile.ai").read_text(encoding="utf-8")
        assert "ai_platform_api.py" in content, "Must copy the FastAPI entry point"

    def test_dockerfile_copies_ai_module(self):
        content = (PROJECT_ROOT / "Dockerfile.ai").read_text(encoding="utf-8")
        assert "ai_platform" in content, "Must copy the ai_platform module"

    def test_dockerfile_exposes_port_8000(self):
        content = (PROJECT_ROOT / "Dockerfile.ai").read_text(encoding="utf-8")
        assert "EXPOSE 8000" in content, "Must expose port 8000"

    def test_dockerfile_has_healthcheck(self):
        content = (PROJECT_ROOT / "Dockerfile.ai").read_text(encoding="utf-8")
        assert "HEALTHCHECK" in content, "Must have a HEALTHCHECK instruction"

    def test_dockerfile_healthcheck_hits_api(self):
        content = (PROJECT_ROOT / "Dockerfile.ai").read_text(encoding="utf-8")
        assert "/api/v1/health" in content, "Healthcheck must call /api/v1/health"

    def test_dockerfile_uses_uvicorn(self):
        content = (PROJECT_ROOT / "Dockerfile.ai").read_text(encoding="utf-8")
        assert "uvicorn" in content, "Entry point must use uvicorn"

    def test_dockerfile_uses_non_root_user(self):
        content = (PROJECT_ROOT / "Dockerfile.ai").read_text(encoding="utf-8")
        has_user = "useradd" in content.lower() or "USER " in content
        assert has_user, "Should create non-root user"

    def test_dockerfile_is_multi_stage(self):
        content = (PROJECT_ROOT / "Dockerfile.ai").read_text(encoding="utf-8")
        assert content.count("FROM python:") >= 2, "Should use multi-stage build"


class TestChaosDockerfileContent:
    def test_dockerfile_copies_lua_scripts(self):
        """限流器（默认 sliding 算法）运行时读取 lua/sliding_window.lua，
        镜像缺少该目录会让 /order 请求在 before_request 直接 500。"""
        content = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
        assert "COPY lua ./lua" in content, "Chaos Dockerfile must copy lua scripts dir"

    def test_lua_scripts_exist_in_repo(self):
        assert (PROJECT_ROOT / "lua" / "sliding_window.lua").exists()
        assert (PROJECT_ROOT / "lua" / "fixed_window.lua").exists()


class TestDockerComposeContent:
    def test_yaml_is_valid(self):
        raw = (PROJECT_ROOT / "docker-compose.ai.yml").read_text(encoding="utf-8")
        parsed = yaml.safe_load(raw)
        assert isinstance(parsed, dict)
        assert "services" in parsed

    def test_ai_platform_service_defined(self):
        parsed = yaml.safe_load((PROJECT_ROOT / "docker-compose.ai.yml").read_text(encoding="utf-8"))
        assert "ai-platform" in parsed["services"]

    def test_ai_platform_port_mapping(self):
        parsed = yaml.safe_load((PROJECT_ROOT / "docker-compose.ai.yml").read_text(encoding="utf-8"))
        svc = parsed["services"]["ai-platform"]
        ports = svc.get("ports", [])
        assert any("8000" in str(p) for p in ports), "Must map port 8000"

    def test_redis_service_defined(self):
        parsed = yaml.safe_load((PROJECT_ROOT / "docker-compose.ai.yml").read_text(encoding="utf-8"))
        assert "redis" in parsed["services"]

    def test_mysql_service_defined(self):
        parsed = yaml.safe_load((PROJECT_ROOT / "docker-compose.ai.yml").read_text(encoding="utf-8"))
        assert "mysql" in parsed["services"]

    def test_ai_platform_depends_on_redis(self):
        parsed = yaml.safe_load((PROJECT_ROOT / "docker-compose.ai.yml").read_text(encoding="utf-8"))
        svc = parsed["services"]["ai-platform"]
        deps = svc.get("depends_on", {})
        assert "redis" in deps

    def test_environment_variables_use_interpolation(self):
        raw = (PROJECT_ROOT / "docker-compose.ai.yml").read_text(encoding="utf-8")
        assert "${" in raw, "Should use env var interpolation for flexibility"

    def test_network_is_defined(self):
        parsed = yaml.safe_load((PROJECT_ROOT / "docker-compose.ai.yml").read_text(encoding="utf-8"))
        assert "networks" in parsed, "Must define networks at top level"

    def test_volumes_are_defined(self):
        parsed = yaml.safe_load((PROJECT_ROOT / "docker-compose.ai.yml").read_text(encoding="utf-8"))
        assert "volumes" in parsed, "Must define named volumes"


class TestDockerignoreContent:
    def test_ignores_pycache(self):
        content = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8")
        assert "__pycache__" in content or "*.pyc" in content

    def test_ignores_git(self):
        content = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8")
        assert ".git" in content

    def test_ignores_tests(self):
        content = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8")
        assert "tests/" in content

    def test_ignores_pytest_cache(self):
        content = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8")
        assert ".pytest_cache" in content


class TestEnvExample:
    def test_env_example_is_valid(self):
        content = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
        assert len(content) > 0

    def test_env_example_has_app_env(self):
        content = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
        assert "APP_ENV" in content

    def test_env_example_has_agent_mode(self):
        content = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
        assert "AGENT_MODE" in content

    def test_env_example_has_llm_provider(self):
        content = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
        assert "AGENT_LLM_PROVIDER" in content

    def test_env_example_has_platform_vars(self):
        content = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
        for var in ["PLATFORM_OBSERVABILITY", "PLATFORM_EVALUATION", "PLATFORM_TIMEOUT"]:
            assert var in content, f"Missing: {var}"

    def test_env_example_has_redis(self):
        content = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
        assert "REDIS_HOST" in content

    def test_env_example_has_mysql(self):
        content = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
        assert "MYSQL" in content

    def test_env_example_has_log_level(self):
        content = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
        assert "OBSERVABILITY_LOG_LEVEL" in content

    def test_env_example_has_no_hardcoded_secrets(self):
        content = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
        for banned in ["my-production-key", "actual-password", "prod-secret-123"]:
            assert banned not in content, f"Must not contain real secret: {banned}"


class TestRequirementsAIContent:
    def test_has_fastapi(self):
        content = (PROJECT_ROOT / "requirements-ai.txt").read_text(encoding="utf-8")
        assert "fastapi" in content

    def test_has_pydantic(self):
        content = (PROJECT_ROOT / "requirements-ai.txt").read_text(encoding="utf-8")
        assert "pydantic" in content

    def test_has_uvicorn(self):
        content = (PROJECT_ROOT / "requirements-ai.txt").read_text(encoding="utf-8")
        assert "uvicorn" in content

    def test_no_flask(self):
        content = (PROJECT_ROOT / "requirements-ai.txt").read_text(encoding="utf-8")
        assert "flask" not in content.lower(), "AI platform does not depend on Flask"

    def test_no_redis(self):
        content = (PROJECT_ROOT / "requirements-ai.txt").read_text(encoding="utf-8")
        assert "redis" not in content.lower(), "AI platform does not depend on Redis at runtime"
