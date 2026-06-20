"""Bcrypt password hashing and verification.

Uses the ``bcrypt`` library directly rather than ``passlib``, which has
known compatibility issues on Python 3.12+.

Examples
--------
>>> hashed = hash_password("hunter2")
>>> verify_password("hunter2", hashed)
True
>>> verify_password("wrong", hashed)
False
"""

from __future__ import annotations

import bcrypt

__all__ = ["hash_password", "verify_password"]

# Default bcrypt cost factor.  12 is a reasonable balance between
# security and login latency (~250 ms on modern hardware).
_DEFAULT_ROUNDS = 12


def hash_password(password: str, *, rounds: int = _DEFAULT_ROUNDS) -> str:
    """Return a bcrypt hash of *password*.

    Parameters
    ----------
    password:
        The plain-text password to hash.
    rounds:
        The bcrypt cost factor (log₂ iterations).  Higher is slower but
        more resistant to brute-force attacks.

    Returns
    -------
    str
        A UTF-8 bcrypt hash string suitable for database storage.
    """
    salt = bcrypt.gensalt(rounds=rounds)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check *plain_password* against a bcrypt *hashed_password*.

    Parameters
    ----------
    plain_password:
        The plain-text password provided by the user.
    hashed_password:
        The bcrypt hash stored in the database.

    Returns
    -------
    bool
        ``True`` if the password matches, ``False`` otherwise.
        Also returns ``False`` on any unexpected error (malformed hash,
        encoding issue, etc.) so callers can treat it as a simple
        boolean check.
    """
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False
