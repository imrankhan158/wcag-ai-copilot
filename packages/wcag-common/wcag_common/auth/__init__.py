"""Authentication utilities — JWT tokens and password hashing.

Usage
-----
>>> from wcag_common.auth import (
...     create_access_token,
...     decode_access_token,
...     create_refresh_token,
...     hash_password,
...     verify_password,
... )
"""

from wcag_common.auth.jwt import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
)
from wcag_common.auth.password import hash_password, verify_password

__all__ = [
    "create_access_token",
    "create_refresh_token",
    "decode_access_token",
    "hash_password",
    "verify_password",
]
