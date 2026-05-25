---
name: fastapi-rate-limiting-integration
description: Patterns for integrating rate limiting into FastAPI applications using slowapi. Covers decorator signatures, dependency injection, and common pitfalls.
generated_from_knowledge:
  - 88cf3ffd-8d47-4521-9da8-b944de1f4add
  - 9cc8ee05-12f6-465b-bb3d-0f6358f61036
confidence: 0.75
status: active
---

# FastAPI Rate Limiting Integration

## Trigger

Use this skill when:
- Adding rate limiting to FastAPI endpoints
- Using slowapi or similar rate limiting libraries
- Reviewing endpoint code that includes rate limiting decorators
- Debugging rate limits that appear to not be enforced

## Required Procedure

### 1. slowapi @limiter.limit() requires request: Request parameter

**WRONG:**
```python
@router.post("/chat")
@limiter.limit(settings.chat_rate_limit)
async def chat_endpoint(message: str):  # MISSING request parameter!
    ...
```

**RIGHT:**
```python
@router.post("/chat")
@limiter.limit(settings.chat_rate_limit)
async def chat_endpoint(
    request: Request,  # MUST be present in the signature
    message: str
):
    ...
```

`request: Request` can appear at any position in the signature — it does not need to be first. The only requirement is that it is present so slowapi can extract the request object for rate limit key generation.

### 2. Use dependency injection for custom limiter logic

```python
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request
import hmac

class WhitelistLimiter(Limiter):
    def __init__(self, default_limit: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_limit = default_limit

    def _check_request_limit(self, request, endpoint_func, in_middleware=True):
        key = request.headers.get("X-API-Key")
        if key and hmac.compare_digest(key, settings.health_check_api_key):
            return  # bypass rate limiting for whitelisted keys
        super()._check_request_limit(request, endpoint_func, in_middleware)

limiter = WhitelistLimiter(
    default_limit="30/minute",
    key_func=get_remote_address
)
```

## Forbidden Shortcuts

- NEVER omit request: Request parameter on rate-limited endpoints
- NEVER assume rate limiting works without testing — silent failures are common
- NEVER use plain `==` for API key comparison in whitelist logic — use `hmac.compare_digest`

## Common Error Signatures

| Symptom | Cause | Fix |
|---------|-------|-----|
| Rate limits not enforced | Missing request: Request parameter | Add request to endpoint signature |
| "Request" not defined | Missing import | from starlette.requests import Request |
| Whitelist bypass not working | Limiter not subclassed | Extend slowapi.Limiter and override _check_request_limit |
| Timing attack on API key | Using `==` instead of hmac.compare_digest | Use hmac.compare_digest for key comparison |

## Delegation Template

When delegating a task affected by this skill, include:

```
SKILLS: file:.opencode/skills/generated/fastapi-rate-limiting-integration/SKILL.md
```

## Reviewer Checks

- [ ] All rate-limited endpoints have request: Request present in signature
- [ ] Request import is present (from starlette.requests import Request)
- [ ] Rate limiting tested with both authenticated and unauthenticated requests
- [ ] Whitelist logic uses hmac.compare_digest for key comparison
- [ ] Custom limiter extends slowapi.Limiter (not a plain class)

## Source Knowledge IDs

- 88cf3ffd-8d47-4521-9da8-b944de1f4add — slowapi @limiter.limit() requires request: Request parameter
- 9cc8ee05-12f6-465b-bb3d-0f6358f61036 — Always verify decorator signature requirements when adding rate limiting
