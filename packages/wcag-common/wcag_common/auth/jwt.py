"""JWT token creation and verification.

Supports both **HS256** (symmetric, current default) and **RS256**
(asymmetric, for future migration).  When switching to RS256, pass the
private key to *create_** functions and the public key to *decode_*.

Examples
--------
>>> token = create_access_token(
...     data={"sub": "user-uuid"},
...     secret_key="my-secret",
... )
>>> payload = decode_access_token(token, secret_key="my-secret")
>>> payload["sub"]
'user-uuid'
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from jwt.exceptions import PyJWTError  # noqa: F401 — re-exported for consumers

__all__ = [
    "create_access_token",
    "create_refresh_token",
    "decode_access_token",
    "PyJWTError",
]

# Algorithms explicitly supported by this module.
_SUPPORTED_ALGORITHMS = frozenset({"HS256", "RS256"})


def _validate_algorithm(algorithm: str) -> None:
    """Raise ``ValueError`` if *algorithm* is not supported."""
    if algorithm not in _SUPPORTED_ALGORITHMS:
        raise ValueError(
            f"Unsupported algorithm {algorithm!r}. "
            f"Choose from {sorted(_SUPPORTED_ALGORITHMS)}."
        )


def create_access_token(
    data: dict[str, Any],
    secret_key: str,
    *,
    algorithm: str = "HS256",
    expires_minutes: int = 60,
) -> str:
    """Create a signed JWT access token.

    Parameters
    ----------
    data:
        Arbitrary claims to embed in the token.  Must include ``"sub"``
        by convention, but this is **not** enforced here.
    secret_key:
        HMAC secret (HS256) **or** PEM-encoded private key (RS256).
    algorithm:
        Signing algorithm — ``"HS256"`` or ``"RS256"``.
    expires_minutes:
        Token lifetime in minutes from *now*.

    Returns
    -------
    str
        The compact JWS string.
    """
    _validate_algorithm(algorithm)
    now = datetime.now(timezone.utc)
    payload = {
        **data,
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
        "token_type": "access",
    }
    return jwt.encode(payload, secret_key, algorithm=algorithm)


def create_refresh_token(
    data: dict[str, Any],
    secret_key: str,
    *,
    algorithm: str = "HS256",
    expires_days: int = 7,
) -> str:
    """Create a signed JWT refresh token.

    Refresh tokens are long-lived and carry a ``token_type`` of
    ``"refresh"`` so that the verification layer can distinguish them
    from access tokens.

    Parameters
    ----------
    data:
        Claims to embed (typically just ``{"sub": user_id}``).
    secret_key:
        HMAC secret or PEM private key.
    algorithm:
        ``"HS256"`` or ``"RS256"``.
    expires_days:
        Token lifetime in days from *now*.

    Returns
    -------
    str
        The compact JWS string.
    """
    _validate_algorithm(algorithm)
    now = datetime.now(timezone.utc)
    payload = {
        **data,
        "iat": now,
        "exp": now + timedelta(days=expires_days),
        "token_type": "refresh",
    }
    return jwt.encode(payload, secret_key, algorithm=algorithm)


def decode_access_token(
    token: str,
    secret_key: str,
    *,
    algorithm: str = "HS256",
) -> dict[str, Any]:
    """Decode and verify a JWT token.

    Parameters
    ----------
    token:
        The compact JWS string.
    secret_key:
        HMAC secret (HS256) **or** PEM-encoded public key (RS256).
    algorithm:
        Expected algorithm — ``"HS256"`` or ``"RS256"``.

    Returns
    -------
    dict
        The decoded payload.

    Raises
    ------
    jwt.exceptions.PyJWTError
        On any verification failure (expired, invalid signature, …).
    """
    _validate_algorithm(algorithm)
    return jwt.decode(
        token,
        secret_key,
        algorithms=[algorithm],
        options={"require": ["exp", "iat"]},
    )
