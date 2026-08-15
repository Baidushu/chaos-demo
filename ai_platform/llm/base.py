from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any

from ai_platform.llm.types import LLMRequest, LLMResponse


class BaseLLM(ABC):
    @abstractmethod
    def generate(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError


def extract_json_payload(text: str) -> dict[str, Any] | list[Any]:
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))

    match = re.search(r"(\[.*\]|\{.*\})", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))

    return json.loads(text)
