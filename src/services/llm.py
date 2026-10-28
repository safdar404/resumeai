"""LLM provider integration via LangChain with structured outputs, bounded
retries and explicit error classification. Credentials are never logged."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Type, TypeVar

from pydantic import BaseModel, ValidationError

from src.config import (LLM_MAX_FORMAT_RETRIES, LLM_MAX_TRANSIENT_RETRIES, LLM_TIMEOUT_SECONDS, PROVIDERS)
from src.security.credentials import check_api_key

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

TRANSIENT = {"RateLimitError", "APITimeoutError", "APIConnectionError", "InternalServerError",
             "ServiceUnavailableError", "OverloadedError", "Timeout", "TimeoutError", "ReadTimeout",
             "ConnectTimeout", "ConnectionError"}
AUTH = {"AuthenticationError", "PermissionDeniedError"}
MALFORMED = {"OutputParserException", "ValidationError", "JSONDecodeError"}


class LLMError(Exception):
    """kind: missing_credentials | invalid_key_format | auth | rate_limit | timeout |
    unavailable | malformed | bad_request | unknown"""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message

    def user_message(self) -> str:
        return {
            "missing_credentials": "No API key is configured for the selected provider.",
            "invalid_key_format": "The API key format looks wrong: " + self.message,
            "auth": "The provider rejected the API key (authentication failed). Check the key and account.",
            "rate_limit": "The provider's rate limit or quota was reached. Try again shortly or check billing.",
            "timeout": "The provider did not respond in time.",
            "unavailable": "The provider is temporarily unavailable.",
            "malformed": "The model returned a response that did not match the required structure.",
            "bad_request": "The provider rejected the request: " + self.message,
        }.get(self.kind, "Unexpected provider error: " + self.message)


def classify(exc: BaseException) -> LLMError:
    name = type(exc).__name__
    if isinstance(exc, LLMError):
        return exc
    if name in AUTH:
        return LLMError("auth", name)
    if name == "RateLimitError":
        return LLMError("rate_limit", name)
    if "Timeout" in name:
        return LLMError("timeout", name)
    if name in TRANSIENT:
        return LLMError("unavailable", name)
    if name in MALFORMED or isinstance(exc, ValidationError):
        return LLMError("malformed", name)
    if name in ("BadRequestError", "NotFoundError", "UnprocessableEntityError"):
        # Message may include model name but never the key.
        return LLMError("bad_request", f"{name}: {str(exc)[:200]}")
    return LLMError("unknown", name)


@dataclass
class LLMSettings:
    provider: str = "none"
    model: str = ""
    api_key: str | None = None
    base_url: str = ""
    temperature: float = 0.2
    timeout: int = LLM_TIMEOUT_SECONDS


class LLMService:
    def __init__(self, settings: LLMSettings, chat_model: Any = None):
        self.settings = settings
        self._model = chat_model
        self.calls = 0
        if chat_model is None:
            self._model = self._build()

    @property
    def provider_label(self) -> str:
        return PROVIDERS.get(self.settings.provider, {}).get("label", self.settings.provider)

    def _build(self):
        s = self.settings
        if s.provider not in PROVIDERS or s.provider == "none":
            raise LLMError("bad_request", "No provider selected")
        if s.provider == "openai_compatible" and not s.base_url:
            raise LLMError("bad_request", "A base URL is required for an OpenAI-compatible endpoint.")
        check = check_api_key(s.api_key)
        if not check.ok:
            if not s.api_key:
                raise LLMError("missing_credentials", "missing")
            raise LLMError("invalid_key_format", " ".join(check.problems))
        model = s.model or PROVIDERS[s.provider]["default_model"]
        if s.provider in ("openai", "openai_compatible"):
            from langchain_openai import ChatOpenAI

            kwargs = dict(model=model, api_key=s.api_key, temperature=s.temperature,
                          timeout=s.timeout, max_retries=0)
            if s.base_url:
                kwargs["base_url"] = s.base_url
            return ChatOpenAI(**kwargs)
        if s.provider == "anthropic":
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(model=model, api_key=s.api_key, temperature=s.temperature,
                                 timeout=s.timeout, max_retries=0, max_tokens=4096)
        raise LLMError("bad_request", f"Unknown provider {s.provider}")

    # ---------------------------------------------------------------- calls
    def structured(self, schema: Type[T], prompt, variables: dict) -> T:
        """Invoke ``prompt | model.with_structured_output(schema)`` with bounded
        retries for transient errors and one corrective retry for malformed output."""
        runnable = self._model.with_structured_output(schema, method="function_calling") \
            if self.settings.provider in ("openai", "openai_compatible") else self._model.with_structured_output(schema)
        chain = prompt | runnable
        transient_left, format_left = LLM_MAX_TRANSIENT_RETRIES, LLM_MAX_FORMAT_RETRIES
        vars_ = dict(variables)
        vars_.setdefault("format_feedback", "")
        attempt = 0
        while True:
            attempt += 1
            try:
                self.calls += 1
                result = chain.invoke(vars_)
                if result is None:
                    raise LLMError("malformed", "empty structured response")
                if isinstance(result, dict):
                    result = schema.model_validate(result)
                if not isinstance(result, schema):
                    raise LLMError("malformed", f"expected {schema.__name__}, got {type(result).__name__}")
                return result
            except Exception as exc:  # noqa: BLE001 — classified below
                err = classify(exc)
                log.warning("LLM call failed (%s, attempt %d)", err.kind, attempt)
                if err.kind in ("rate_limit", "timeout", "unavailable") and transient_left > 0:
                    transient_left -= 1
                    time.sleep(min(8.0, 1.5 * (2 ** (LLM_MAX_TRANSIENT_RETRIES - transient_left - 1))))
                    continue
                if err.kind == "malformed" and format_left > 0:
                    format_left -= 1
                    vars_["format_feedback"] = ("Your previous reply did not match the required schema. "
                                                "Return only the structured fields requested.")
                    continue
                raise err from None

    def test_connection(self) -> tuple[bool, str]:
        """Minimal call that proves the key and model work. Never echoes the key."""
        from langchain_core.prompts import ChatPromptTemplate

        class Ping(BaseModel):
            ok: bool

        prompt = ChatPromptTemplate.from_messages([("system", "Reply with ok=true."), ("human", "ping{format_feedback}")])
        try:
            r = self.structured(Ping, prompt, {})
            return bool(r.ok), "Connection verified."
        except LLMError as e:
            return False, e.user_message()


def build_service(settings: LLMSettings) -> tuple[LLMService | None, str | None]:
    """Return (service, error_message). None service means offline mode."""
    if settings.provider == "none":
        return None, None
    try:
        return LLMService(settings), None
    except LLMError as e:
        return None, e.user_message()
