from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config import Settings


@dataclass(frozen=True, slots=True)
class LLMResult:
    raw_answer: str
    model_name: str
    model_version: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    finish_reason: str


class LLMProvider:
    def generate(self, prompt: str, context_chunks: list[dict], query: str) -> LLMResult:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class ModelProfile:
    id: str
    label: str
    provider: str
    model_name: str
    enabled: bool
    status: str = "available"
    reason: str | None = None
    description: str = ""
    details: dict[str, Any] | None = None


class ModelProfileError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class LocalMockProvider(LLMProvider):
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    def generate(self, prompt: str, context_chunks: list[dict], query: str) -> LLMResult:
        started = time.perf_counter()
        if not context_chunks:
            answer = "I do not have enough context to answer this question."
            finish_reason = "stop"
        else:
            snippets = " ".join(chunk["text"] for chunk in context_chunks[:2])
            answer = f"{snippets} Sources: " + ", ".join(
                f"{chunk['document_id']}#{chunk['chunk_id']}" for chunk in context_chunks[:2]
            )
            finish_reason = "stop"

        latency_ms = int((time.perf_counter() - started) * 1000)
        return LLMResult(
            raw_answer=answer,
            model_name=self.model_name,
            model_version="mock-v1",
            input_tokens=len(prompt.split()),
            output_tokens=len(answer.split()),
            latency_ms=latency_ms,
            finish_reason=finish_reason,
        )


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        model_name: str,
        base_url: str | None = None,
        api_key: str | None = None,
        allow_mock_fallback: bool = True,
    ) -> None:
        self.model_name = model_name
        self.base_url = (base_url or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.api_key = api_key if api_key is not None else os.getenv("OPENAI_API_KEY", "")
        self.allow_mock_fallback = allow_mock_fallback
        self.fallback = LocalMockProvider(model_name=f"mock-fallback:{model_name}")

    def generate(self, prompt: str, context_chunks: list[dict], query: str) -> LLMResult:
        started = time.perf_counter()
        if not self.api_key:
            return self._fallback(prompt, context_chunks, query, started, "missing_api_key")

        request_payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": "Answer using only the provided RAG context and include citations."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
        }
        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(request_payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))) as response:
                body = json.loads(response.read().decode("utf-8"))
            answer = body["choices"][0]["message"]["content"]
            usage = body.get("usage", {})
            latency_ms = int((time.perf_counter() - started) * 1000)
            return LLMResult(
                raw_answer=answer,
                model_name=f"openai:{self.model_name}",
                model_version=str(body.get("model", self.model_name)),
                input_tokens=int(usage.get("prompt_tokens", len(prompt.split()))),
                output_tokens=int(usage.get("completion_tokens", len(answer.split()))),
                latency_ms=latency_ms,
                finish_reason=str(body["choices"][0].get("finish_reason", "stop")),
            )
        except (HTTPError, URLError, TimeoutError, KeyError, json.JSONDecodeError, OSError) as exc:
            return self._fallback(prompt, context_chunks, query, started, type(exc).__name__)

    def _fallback(self, prompt: str, context_chunks: list[dict], query: str, started: float, reason: str) -> LLMResult:
        if not self.allow_mock_fallback:
            return _failed_llm_result(
                provider_prefix="openai",
                model_name=self.model_name,
                prompt=prompt,
                started=started,
                reason=reason,
            )
        result = self.fallback.generate(prompt, context_chunks, query)
        return LLMResult(
            raw_answer=result.raw_answer,
            model_name=f"openai:{self.model_name}",
            model_version="fallback-mock-v1",
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            latency_ms=int((time.perf_counter() - started) * 1000),
            finish_reason=f"fallback:{reason}",
        )


class OllamaProvider(LLMProvider):
    def __init__(self, model_name: str, base_url: str | None = None, allow_mock_fallback: bool = True) -> None:
        self.model_name = model_name
        self.base_url = (base_url or os.getenv("LOCAL_LLM_BASE_URL") or "http://localhost:11434").rstrip("/")
        self.allow_mock_fallback = allow_mock_fallback
        self.fallback = LocalMockProvider(model_name=f"mock-fallback:{model_name}")

    def generate(self, prompt: str, context_chunks: list[dict], query: str) -> LLMResult:
        started = time.perf_counter()
        request_payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0},
        }
        request = Request(
            f"{self.base_url}/api/generate",
            data=json.dumps(request_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))) as response:
                body = json.loads(response.read().decode("utf-8"))
            answer = str(body.get("response", ""))
            latency_ms = int((time.perf_counter() - started) * 1000)
            return LLMResult(
                raw_answer=answer,
                model_name=f"ollama:{self.model_name}",
                model_version=str(body.get("model", self.model_name)),
                input_tokens=int(body.get("prompt_eval_count", len(prompt.split())) or 0),
                output_tokens=int(body.get("eval_count", len(answer.split())) or 0),
                latency_ms=latency_ms,
                finish_reason="stop" if body.get("done", True) else "length",
            )
        except (HTTPError, URLError, TimeoutError, KeyError, json.JSONDecodeError, OSError) as exc:
            return self._fallback(prompt, context_chunks, query, started, type(exc).__name__)

    def _fallback(self, prompt: str, context_chunks: list[dict], query: str, started: float, reason: str) -> LLMResult:
        if not self.allow_mock_fallback:
            return _failed_llm_result(
                provider_prefix="ollama",
                model_name=self.model_name,
                prompt=prompt,
                started=started,
                reason=reason,
            )
        result = self.fallback.generate(prompt, context_chunks, query)
        return LLMResult(
            raw_answer=result.raw_answer,
            model_name=f"ollama:{self.model_name}",
            model_version="fallback-mock-v1",
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            latency_ms=int((time.perf_counter() - started) * 1000),
            finish_reason=f"fallback:{reason}",
        )


class QwenOllamaProvider(OllamaProvider):
    def __init__(self, model_name: str, base_url: str | None = None, allow_mock_fallback: bool = True) -> None:
        super().__init__(model_name, base_url=base_url, allow_mock_fallback=allow_mock_fallback)

    def generate(self, prompt: str, context_chunks: list[dict], query: str) -> LLMResult:
        result = super().generate(prompt, context_chunks, query)
        return LLMResult(
            raw_answer=result.raw_answer,
            model_name=result.model_name.replace("ollama:", "qwen_ollama:", 1),
            model_version=result.model_version,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            latency_ms=result.latency_ms,
            finish_reason=result.finish_reason,
        )


def build_provider(settings: Settings | str, model_name: str | None = None) -> LLMProvider:
    if isinstance(settings, Settings):
        return _build_provider_from_settings(settings)
    return _build_provider_from_legacy_args(settings, model_name or "llama3")


def get_model_profiles(settings: Settings) -> list[ModelProfile]:
    ollama_runtime = _ollama_runtime_status(settings)
    return [
        ModelProfile(
            id="mock",
            label="Mock model",
            provider="mock",
            model_name="mock-v1",
            enabled=True,
            status="available",
            reason="always available",
            description="Deterministic local fallback for demos, tests, and offline development.",
            details={"runtime": "in-process"},
        ),
        _ollama_profile(
            id="qwen_ollama_3b",
            label="Qwen via Ollama",
            provider="qwen_ollama",
            model_name=settings.qwen_ollama_3b_model,
            config_enabled=settings.model_profile_qwen_ollama_enabled or settings.llm_provider == "qwen_ollama",
            runtime=ollama_runtime,
            description="Lightweight local Qwen profile. Recommended first real-provider smoke model.",
        ),
        _ollama_profile(
            id="qwen_ollama_7b",
            label="Qwen via Ollama",
            provider="qwen_ollama",
            model_name=settings.qwen_ollama_7b_model,
            config_enabled=settings.model_profile_qwen_ollama_enabled or settings.llm_provider == "qwen_ollama",
            runtime=ollama_runtime,
            description="Stronger local Qwen profile for MVP demos when the workstation has enough RAM.",
        ),
        _ollama_profile(
            id="ollama_llama",
            label="Llama via Ollama",
            provider="ollama",
            model_name=settings.local_llm_model,
            config_enabled=settings.model_profile_ollama_llama_enabled or settings.llm_provider == "ollama",
            runtime=ollama_runtime,
            description="Generic local Ollama profile for Llama-compatible models.",
        ),
        _openai_profile(
            id="openai_default",
            label="OpenAI-compatible default",
            provider="openai",
            model_name=settings.openai_model,
            api_key_present=bool(settings.openai_api_key.strip()),
            description="OpenAI-compatible chat completions provider. Requires API key configured on backend.",
        ),
    ]


def get_model_profile_aliases(settings: Settings) -> list[ModelProfile]:
    ollama_runtime = _ollama_runtime_status(settings)
    return [
        _ollama_profile(
            id="qwen_ollama",
            label="Qwen via Ollama",
            provider="qwen_ollama",
            model_name=settings.qwen_ollama_model,
            config_enabled=settings.model_profile_qwen_ollama_enabled or settings.llm_provider == "qwen_ollama",
            runtime=ollama_runtime,
            description=(
                "Backward-compatible alias for DEFAULT_MODEL_PROFILE_ID=qwen_ollama. "
                "New UI examples should use qwen_ollama_7b or qwen_ollama_3b."
            ),
        ),
    ]


def resolve_model_profile(settings: Settings, model_profile_id: str | None = None) -> ModelProfile:
    requested_id = (model_profile_id or settings.default_model_profile_id or "mock").strip()
    profiles = {profile.id: profile for profile in [*get_model_profiles(settings), *get_model_profile_aliases(settings)]}
    profile = profiles.get(requested_id)
    if profile is None:
        raise ModelProfileError(f"unknown model_profile_id: {requested_id}", status_code=400)
    if not profile.enabled:
        raise ModelProfileError(f"model_profile_id is disabled: {requested_id}", status_code=400)
    return profile


def build_provider_from_profile(settings: Settings, profile: ModelProfile) -> LLMProvider:
    normalized = profile.provider.strip().lower()
    if normalized == "mock":
        return LocalMockProvider(model_name=f"mock:{profile.model_name}")
    if normalized == "openai":
        return OpenAICompatibleProvider(
            model_name=profile.model_name,
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
            allow_mock_fallback=settings.llm_allow_mock_fallback,
        )
    if normalized == "ollama":
        return OllamaProvider(
            model_name=profile.model_name,
            base_url=settings.local_llm_base_url,
            allow_mock_fallback=settings.llm_allow_mock_fallback,
        )
    if normalized == "qwen_ollama":
        return QwenOllamaProvider(
            model_name=profile.model_name,
            base_url=settings.local_llm_base_url,
            allow_mock_fallback=settings.llm_allow_mock_fallback,
        )
    raise ModelProfileError(f"unsupported provider for model_profile_id={profile.id}: {profile.provider}")


def _build_provider_from_settings(settings: Settings) -> LLMProvider:
    normalized = settings.llm_provider.strip().lower()
    if normalized in {"mock", "local_mock", "local_llama"}:
        return LocalMockProvider(model_name=f"{normalized}:{settings.local_llm_model}")
    if normalized in {"openai", "openai_gpt", "openai_compatible"}:
        return OpenAICompatibleProvider(
            model_name=settings.openai_model,
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
            allow_mock_fallback=settings.llm_allow_mock_fallback,
        )
    if normalized == "ollama":
        return OllamaProvider(
            model_name=settings.local_llm_model,
            base_url=settings.local_llm_base_url,
            allow_mock_fallback=settings.llm_allow_mock_fallback,
        )
    if normalized == "qwen_ollama":
        return QwenOllamaProvider(
            model_name=settings.qwen_ollama_model,
            base_url=settings.local_llm_base_url,
            allow_mock_fallback=settings.llm_allow_mock_fallback,
        )
    return LocalMockProvider(model_name=f"unknown-provider-fallback:{settings.llm_provider}:{settings.local_llm_model}")


def _build_provider_from_legacy_args(provider_name: str, model_name: str) -> LLMProvider:
    normalized = provider_name.strip().lower()
    fallback_settings = Settings(
        LLM_PROVIDER=provider_name,
        LOCAL_LLM_MODEL=model_name,
        OPENAI_MODEL=os.getenv("OPENAI_MODEL", model_name),
        OPENAI_BASE_URL=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        OPENAI_API_KEY=os.getenv("OPENAI_API_KEY", ""),
        LOCAL_LLM_BASE_URL=os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434"),
        QWEN_OLLAMA_MODEL=os.getenv(
            "QWEN_OLLAMA_MODEL",
            model_name if normalized == "qwen_ollama" and model_name.startswith("qwen") else "qwen2.5:7b",
        ),
        LLM_ALLOW_MOCK_FALLBACK=True,
    )
    return _build_provider_from_settings(fallback_settings)


def _failed_llm_result(provider_prefix: str, model_name: str, prompt: str, started: float, reason: str) -> LLMResult:
    return LLMResult(
        raw_answer="",
        model_name=f"{provider_prefix}:{model_name}",
        model_version="error",
        input_tokens=len(prompt.split()),
        output_tokens=0,
        latency_ms=int((time.perf_counter() - started) * 1000),
        finish_reason=f"error:{reason}",
    )


def _ollama_runtime_status(settings: Settings) -> dict[str, Any]:
    base_url = settings.local_llm_base_url.rstrip("/")
    try:
        request = Request(f"{base_url}/api/tags", method="GET")
        with urlopen(request, timeout=2) as response:
            body = json.loads(response.read().decode("utf-8"))
        models = [str(item.get("name", "")) for item in body.get("models", []) if isinstance(item, dict)]
        return {"reachable": True, "models": models, "base_url": base_url, "reason": None}
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return {"reachable": False, "models": [], "base_url": base_url, "reason": type(exc).__name__}


def _ollama_profile(
    *,
    id: str,
    label: str,
    provider: str,
    model_name: str,
    config_enabled: bool,
    runtime: dict[str, Any],
    description: str,
) -> ModelProfile:
    installed_models = set(runtime.get("models") or [])
    model_installed = model_name in installed_models
    reachable = bool(runtime.get("reachable"))
    if not config_enabled:
        status = "unavailable"
        reason = "disabled by backend configuration"
    elif not reachable:
        status = "unavailable"
        reason = "Ollama not reachable"
    elif not model_installed:
        status = "unavailable"
        reason = f"model not pulled: {model_name}"
    else:
        status = "available"
        reason = "runtime available"
    return ModelProfile(
        id=id,
        label=label,
        provider=provider,
        model_name=model_name,
        enabled=status == "available",
        status=status,
        reason=reason,
        description=description,
        details={
            "base_url": runtime.get("base_url"),
            "installed_models": sorted(installed_models),
            "runtime_error": runtime.get("reason"),
        },
    )


def _openai_profile(
    *,
    id: str,
    label: str,
    provider: str,
    model_name: str,
    api_key_present: bool,
    description: str,
) -> ModelProfile:
    return ModelProfile(
        id=id,
        label=label,
        provider=provider,
        model_name=model_name,
        enabled=api_key_present,
        status="available" if api_key_present else "unavailable",
        reason="runtime available" if api_key_present else "API key missing",
        description=description,
        details={"credentials_configured": api_key_present},
    )
