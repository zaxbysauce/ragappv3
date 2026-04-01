"""
Health check API route.

Provides a health endpoint to check backend status.
Expensive model checks are opt-in via ?deep=true query parameter.
"""

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_llm_health_checker, get_model_checker
from app.services.llm_health import LLMHealthChecker
from app.services.model_checker import ModelChecker


router = APIRouter()


@router.get("/health")
async def health_check(
    deep: bool = Query(False, description="Run expensive model availability checks"),
    llm_checker: LLMHealthChecker = Depends(get_llm_health_checker),
    model_checker: ModelChecker = Depends(get_model_checker),
):
    """
    Health check endpoint.

    By default (deep=false), returns immediately with backend status only.
    This is fast and suitable for frequent polling.

    With deep=true, also checks LLM service health and model availability.
    This involves real model inference calls and may take several seconds.
    """
    result = {
        "status": "ok",
        "services": {"backend": True, "embeddings": None, "chat": None},
    }

    if deep:
        llm_status = await llm_checker.check_all()
        models_status = await model_checker.check_models()

        result["llm"] = llm_status
        result["models"] = models_status
        result["services"] = {
            "backend": True,
            "embeddings": llm_status.get("embeddings", {}).get("ok", False),
            "chat": llm_status.get("chat", {}).get("ok", False),
        }

    return result
