"""Base service configuration using pydantic-settings.

Every microservice in the WCAG AI Copilot platform should subclass
:class:`BaseServiceSettings` and add any service-specific settings.

The base class reads from a ``.env`` file (if present) and from real
environment variables, with env vars taking precedence.

Example
-------
>>> from wcag_common.config import BaseServiceSettings
>>>
>>> class GatewaySettings(BaseServiceSettings):
...     service_name: str = "api-gateway"
...     cors_origins: list[str] = ["http://localhost:3000"]
...
>>> settings = GatewaySettings()
>>> settings.async_database_url
'postgresql+asyncpg://admin:admin123@localhost:5432/wcag_ai'
"""

from __future__ import annotations

from urllib.parse import quote_plus

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["BaseServiceSettings"]


class BaseServiceSettings(BaseSettings):
    """Shared settings inherited by every WCAG AI Copilot micro-service.

    All fields have sensible defaults for **local development**.
    In production, override them via environment variables or a ``.env``
    file.
    """

    # ── Service identity ──────────────────────────────────────────────
    service_name: str = Field(
        default="wcag-service",
        description="Human-readable service name (used in health checks and logs).",
    )
    service_version: str = Field(
        default="0.1.0",
        description="Semantic version of the running service.",
    )
    debug: bool = Field(
        default=False,
        description="Enable debug mode (verbose logging, etc.).",
    )

    # ── PostgreSQL ────────────────────────────────────────────────────
    postgres_host: str = Field(default="localhost")
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_db: str = Field(default="wcag_copilot")
    postgres_user: str = Field(default="admin")
    postgres_password: str = Field(default="admin123")

    # ── Redis ─────────────────────────────────────────────────────────
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL.",
    )

    # ── AWS / LocalStack ──────────────────────────────────────────────
    aws_endpoint_url: str = Field(
        default="http://localhost:4566",
        description="Custom S3/SQS endpoint (LocalStack in dev).",
    )
    aws_access_key_id: str = Field(default="test")
    aws_secret_access_key: str = Field(default="test")
    aws_region: str = Field(default="us-east-1")

    # ── Qdrant ────────────────────────────────────────────────────────
    qdrant_url: str = Field(
        default="http://localhost:6333",
        description="Qdrant vector-database URL.",
    )
    qdrant_collection: str = Field(
        default="wcag_criteria",
        description="Default Qdrant collection name.",
    )

    # ── JWT ───────────────────────────────────────────────────────────
    jwt_secret_key: str = Field(
        default="super-secret-wcag-ai-copilot-key-987654321",
        description="Secret key used to sign JWT tokens (fallback for HS256).",
    )
    jwt_private_key: str = Field(
        default="""-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQChKJVFiS3B9JqO
NeV8d1xxKu8gpGfZ5yABOwsy6ewSCKuPBomCeB/s08Qx3wUKP/u5EMfJ6JCXzO4G
9TdI+pU3DJLEkNqP9yyCNw8dZz2k0Hq4Nr4sivCLvxme/aJA4BXLQIt/D6mgIRFg
X+UZADYqP0Oj9zYu2Y4ABmItG9pR7Y3R84SS5S++AqgvAztGjxvW3SyO2H7m/M0x
9bGftwpaM7Mw/WM259bHQ1l6nHBcBtF5iZeWoUHd3tI4iEper4+HX/Nc4Fa8lRdp
q10s0k3egd0FAyFcK0C3eOBYmAlAP6MrtVdyZDFYA2lBY0gZOIjHC+M7f+41jAS1
0yidxXZXAgMBAAECggEAL10bCdW4QgGejt8eNAdsfsIMh35qGyuHR3VP5EXFoMM1
kJJuRY8CavsN9U5DT/DgDVL2NMwJ+uM6rYbSGbuzsPscA3NDGP6e8SI3af/WqSKw
foVwPO0Upy2h3Q1T61cwcIzmspAq3Sn6zmVAkqlyQdZYDc9w+DHuPumhXvqJnnwH
9jGWrI/VZqbUwac3INBgRfcZE2SgwqH4qPXKaVz0ehTIN50tMJeMUsy95E75uoEV
GnXxJKedQRI0CmaZnmlbo45BHrazcE2xTVU5bouE0d+MZaZ8ydTli5bLw7ohiFjD
fYQANiKNjGWgcGzDhpcmEIh2o5KH8NN2/QE51MvB+QKBgQDabH2Ou4qHbOvqjgM3
cPqe/5PifslEELF30SiZ49+rl4o0RvMp0EOGi8gupqDUrPUzktRthbTVBS7tnQZD
MQgHqmT6BVwDold1TeWTwP7C3b35PIDQSYOXl//zu4iaJ8JdG1vwZtdLHST5e+ar
xLne4PoktmIvjIZsMedzV/Gf8wKBgQC84hjzbvxRVVNbJg7FYQYLs9jmL9REuOJ2
eVE289hbF3FPbuEaqWStPSep0uvbkV2e3T5p3mhCdxxp1FhwndTn5+g2FSgirtVl
dfjruoYNDR77wfwSGGoGVx4gxi8yPhzPGtDrdm1j7LOZ/yCp16fe5QMl9tUnvCfZ
cw0tYlsNDQKBgQCvOhoAR7P6sQcSRJuP/rMQmziom84bLMkytjk8O/NUVV4qUkEB
anLBnaIaytJ7y8VqeoCw3HMV8fKT7UT44nzuqWQYr/QBdltzX+qtfkbjTcD6Ee/F
KTTIiMhtYCVWhk8HIsu/MMHHILpo611Cr6/tfc8vZKGgQ7wTUHW9su/EwQKBgDFs
B5NKqwKtDM6AusSyil5thIdWZHhG2Bqfy7xROX88Nw3NuWC8ifc6VTJ+WfBtrM1w
nnAdHbKmb+zQ/wMYiSjU6VGdX48TqAqQP72OZJztnfnJ3Cbv9G4MRXnV4WuIDQmz
vo6dwimvOZ9Fvkoyf143FgfM+iEXfmXLUNtbLO/RAoGAQw2fK4Cn7lWEiFlH6P2G
9214qWsurnFIfuCpquhkGpzz/GEe8sCMnwZMm2FcUxBsr2YUW6cthIl81KuwF/Et
o7oI3G9DPv227gW9/v/s307zmVBqF9bnzI7yqk/70egkvmzRWQmj6LvfIC1EjYt9
GhVtSzVWpeoDQUMZUDayfs0=
-----END PRIVATE KEY-----""",
        description="Asymmetric private key for RS256 JWT signing.",
    )
    jwt_public_key: str = Field(
        default="""-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAoSiVRYktwfSajjXlfHdc
cSrvIKRn2ecgATsLMunsEgirjwaJgngf7NPEMd8FCj/7uRDHyeiQl8zuBvU3SPqV
NwySxJDaj/csgjcPHWc9pNB6uDa+LIrwi78Znv2iQOAVy0CLfw+poCERYF/lGQA2
Kj9Do/c2LtmOAAZiLRvaUe2N0fOEkuUvvgKoLwM7Ro8b1t0sjth+5vzNMfWxn7cK
WjOzMP1jNufWx0NZepxwXAbReYmXlqFB3d7SOIhKXq+Ph1/zXOBWvJUXaatdLNJN
3oHdBQMhXCtAt3jgWJgJQD+jK7VXcmQxWANpQWNIGTiIxwvjO3/uNYwEtdMoncV2
VwIDAQAB
-----END PUBLIC KEY-----""",
        description="Asymmetric public key for RS256 JWT validation.",
    )
    jwt_algorithm: str = Field(
        default="HS256",
        description="JWT signing algorithm — 'HS256' or 'RS256'.",
    )
    jwt_access_token_expire_minutes: int = Field(
        default=60,
        ge=1,
        description="Access-token lifetime in minutes.",
    )
    jwt_refresh_token_expire_days: int = Field(
        default=7,
        ge=1,
        description="Refresh-token lifetime in days.",
    )

    # ── LLM ───────────────────────────────────────────────────────────
    openai_api_key: str = Field(
        default="",
        description="OpenAI (or compatible) API key.",
    )
    llm_model: str = Field(
        default="gpt-4o",
        description="Default LLM model identifier.",
    )
    llm_base_url: str | None = Field(
        default=None,
        description="Optional base URL for self-hosted / proxy LLM endpoints.",
    )

    # ── Derived database URLs ─────────────────────────────────────────

    @property
    def async_database_url(self) -> str:
        """Async connection string for SQLAlchemy + asyncpg."""
        password = quote_plus(self.postgres_password)
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sync_database_url(self) -> str:
        """Sync connection string for SQLAlchemy + psycopg2."""
        password = quote_plus(self.postgres_password)
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # ── pydantic-settings configuration ──────────────────────────────

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    def __init__(self, **values):
        # Dynamically load secrets from cloud provider if configured
        import os
        provider = os.getenv("SECRETS_PROVIDER")
        if provider == "aws":
            secret_id = os.getenv("SECRETS_NAME") or self.service_name
            try:
                from wcag_common.config.secrets import fetch_aws_secrets
                aws_secrets = fetch_aws_secrets(secret_id)
                for k, v in aws_secrets.items():
                    k_lower = k.lower()
                    if k_lower in self.model_fields and k_lower not in values:
                        values[k_lower] = v
            except Exception:
                pass
        super().__init__(**values)

