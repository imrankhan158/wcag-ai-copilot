from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()
logger = logging.getLogger("audit-service.llm")

MAX_CONCURRENT_LLM_CALLS = int(os.getenv("MAX_CONCURRENT_LLM_CALLS", "10"))
_llm_semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS)


@dataclass
class CircuitBreaker:
    """Simple circuit breaker: if a provider fails N times in window_seconds, skip it for cooldown_seconds."""
    max_failures: int = 5
    window_seconds: float = 60.0
    cooldown_seconds: float = 300.0  # 5 minutes
    _failures: list[float] = field(default_factory=list)
    _open_until: float = 0.0

    @property
    def is_open(self) -> bool:
        if time.time() < self._open_until:
            return True
        return False

    def record_failure(self):
        now = time.time()
        self._failures = [t for t in self._failures if now - t < self.window_seconds]
        self._failures.append(now)
        if len(self._failures) >= self.max_failures:
            self._open_until = now + self.cooldown_seconds
            logger.warning(f"Circuit breaker OPEN — too many failures. Cooling down for {self.cooldown_seconds}s.")
            self._failures.clear()

    def record_success(self):
        self._failures.clear()
        self._open_until = 0.0


@dataclass
class LLMProvider:
    name: str
    model: str
    api_key: str
    base_url: str | None = None
    circuit_breaker: CircuitBreaker = field(default_factory=CircuitBreaker)

    def create_llm(self) -> ChatOpenAI:
        return ChatOpenAI(
            model=self.model,
            api_key=self.api_key,
            base_url=self.base_url,
            temperature=0,
            streaming=True,
        )


class LLMProviderFactory:
    def __init__(self):
        self.providers: list[LLMProvider] = []
        self._setup_providers()

    def _setup_providers(self):
        openai_key = os.getenv("OPENAI_API_KEY")
        nvidia_key = os.getenv("NVIDIA_API_KEY")
        llm_key = os.getenv("LLM_API_KEY")
        llm_base = os.getenv("LLM_BASE_URL")
        llm_model = os.getenv("LLM_MODEL")

        if llm_key and llm_base and llm_model:
            self.providers.append(LLMProvider(
                name="custom", model=llm_model, api_key=llm_key, base_url=llm_base
            ))

        if openai_key:
            model = os.getenv("LLM_MODEL", "gpt-4o")
            base_url = os.getenv("OPENAI_BASE_URL")
            self.providers.append(LLMProvider(
                name="openai", model=model, api_key=openai_key, base_url=base_url
            ))

        if nvidia_key:
            self.providers.append(LLMProvider(
                name="nvidia", model="meta/llama-3.3-70b-instruct",
                api_key=nvidia_key, base_url="https://integrate.api.nvidia.com/v1"
            ))

        if not self.providers:
            raise RuntimeError("No LLM provider configured. Set OPENAI_API_KEY or NVIDIA_API_KEY.")

        logger.info(f"LLM providers configured: {[p.name for p in self.providers]}")

    def get_available_llm(self) -> tuple[ChatOpenAI, str]:
        for provider in self.providers:
            if not provider.circuit_breaker.is_open:
                return provider.create_llm(), provider.name
        # All circuit breakers open — force use the first provider anyway
        logger.error("All LLM circuit breakers are open! Forcing first provider.")
        provider = self.providers[0]
        return provider.create_llm(), provider.name

    def record_success(self, provider_name: str):
        for p in self.providers:
            if p.name == provider_name:
                p.circuit_breaker.record_success()
                break

    def record_failure(self, provider_name: str):
        for p in self.providers:
            if p.name == provider_name:
                p.circuit_breaker.record_failure()
                break


_factory: LLMProviderFactory | None = None

def _get_factory() -> LLMProviderFactory:
    global _factory
    if _factory is None:
        _factory = LLMProviderFactory()
    return _factory

def get_llm() -> ChatOpenAI:
    """Get the best available LLM instance with circuit breaker logic."""
    factory = _get_factory()
    llm, name = factory.get_available_llm()
    return llm

def get_llm_with_tracking() -> tuple[ChatOpenAI, str]:
    """Get LLM instance and provider name for tracking."""
    factory = _get_factory()
    return factory.get_available_llm()

def record_llm_success(provider_name: str):
    _get_factory().record_success(provider_name)

def record_llm_failure(provider_name: str):
    _get_factory().record_failure(provider_name)

async def acquire_llm_semaphore():
    await _llm_semaphore.acquire()

def release_llm_semaphore():
    _llm_semaphore.release()
