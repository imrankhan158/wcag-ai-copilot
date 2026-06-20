"""Centralised configuration management via pydantic-settings.

Usage
-----
>>> from wcag_common.config import BaseServiceSettings
>>>
>>> class MyServiceSettings(BaseServiceSettings):
...     custom_flag: bool = False
...
>>> settings = MyServiceSettings()  # reads from .env automatically
"""

from wcag_common.config.settings import BaseServiceSettings

__all__ = ["BaseServiceSettings"]
