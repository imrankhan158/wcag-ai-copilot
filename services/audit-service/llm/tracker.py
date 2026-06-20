from __future__ import annotations

import logging
import time
from dataclasses import dataclass

logger = logging.getLogger("audit-service.usage")

@dataclass
class AuditUsageRecord:
    audit_id: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0

    @property
    def estimated_cost(self) -> float:
        # GPT-4o pricing approximation: $2.50/1M input, $10/1M output
        if "gpt-4o" in self.model:
            return (self.input_tokens * 2.5 / 1_000_000) + (self.output_tokens * 10.0 / 1_000_000)
        # NVIDIA / other models - approximate
        return (self.input_tokens + self.output_tokens) * 0.5 / 1_000_000

    def log(self):
        logger.info(
            f"AUDIT_USAGE audit_id={self.audit_id} provider={self.provider} "
            f"model={self.model} input_tokens={self.input_tokens} output_tokens={self.output_tokens} "
            f"estimated_cost=${self.estimated_cost:.6f} latency_ms={self.latency_ms:.0f}"
        )


class UsageTracker:
    """Track LLM token usage across an audit pipeline execution."""

    def __init__(self, audit_id: str, provider: str, model: str):
        self.audit_id = audit_id
        self.provider = provider
        self.model = model
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self._start_time = time.time()

    def add_usage(self, input_tokens: int, output_tokens: int):
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens

    def finalize(self) -> AuditUsageRecord:
        record = AuditUsageRecord(
            audit_id=self.audit_id,
            provider=self.provider,
            model=self.model,
            input_tokens=self.total_input_tokens,
            output_tokens=self.total_output_tokens,
            latency_ms=(time.time() - self._start_time) * 1000,
        )
        record.log()
        return record
