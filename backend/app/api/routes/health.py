"""
Health check API route.

Provides a health endpoint to check backend status.
Expensive model checks are opt-in via ?deep=true query parameter.
"""

import logging

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import get_llm_health_checker, get_model_checker
from app.services.llm_health import LLMHealthChecker
from app.services.model_checker import ModelChecker

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health_check(
    request: Request,
    deep: bool = Query(False, description="Run expensive model availability checks"),
    llm_checker: LLMHealthChecker = Depends(get_llm_health_checker),
    model_checker: ModelChecker = Depends(get_model_checker),
):
    """
    Health check endpoint.

    By default (deep=false), returns immediately with backend status only.
    This is fast and suitable for frequent polling.

    With deep=true, also checks LLM service health, model availability,
    and vector store connectivity.
    """
    result = {
        "status": "ok",
        "services": {"backend": True, "embeddings": None, "chat": None, "vector_store": None},
    }

    if deep:
        llm_status = await llm_checker.check_all()
        models_status = await model_checker.check_models()

        # Probe vector store connectivity
        vector_status = {"ok": False}
        try:
            vector_store = getattr(request.app.state, "vector_store", None)
            if vector_store and vector_store.table:
                row_count = await vector_store.table.count_rows()
                vector_status = {"ok": True, "rows": row_count}
            elif vector_store:
                vector_status = {"ok": True, "rows": 0}
            else:
                vector_status = {"ok": False, "error": "not initialized"}
        except Exception as e:
            logger.debug("Vector store health probe failed: %s", e)
            vector_status = {"ok": False, "error": str(e)}

        result["llm"] = llm_status
        result["models"] = models_status
        result["vector_store"] = vector_status
        result["services"] = {
            "backend": True,
            "embeddings": llm_status.get("embeddings", {}).get("ok", False),
            "chat": llm_status.get("chat", {}).get("ok", False),
            "vector_store": vector_status.get("ok", False),
        }

    return result
