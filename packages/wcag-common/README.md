# wcag-common

Shared library for the WCAG AI Copilot microservice platform.

## Features

- **Models**: Shared Pydantic schemas (auth, audits, chat, queue)
- **Auth**: JWT utilities (HS256/RS256) and direct password hashing via bcrypt (no passlib)
- **Config**: Centralized settings via Pydantic Settings base class
- **Health**: Pluggable health checker factory for FastAPI microservices

## Installation

Install in editable mode for local development:

```bash
pip install -e packages/wcag-common
```

Or when using `uv`:

```bash
uv add --path packages/wcag-common wcag-common
```

## Usage

```python
from wcag_common.auth.jwt import create_access_token
from wcag_common.config import BaseServiceSettings
```
