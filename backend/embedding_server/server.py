"""FlagEmbedding server for BGE-M3 tri-vector embeddings."""
import logging
import os
from typing import Any, Dict, List, Optional

import numpy as np
import torch
from fastapi import FastAPI, HTTPException
from FlagEmbedding import BGEM3FlagModel
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize model with device auto-detection
device = "cuda" if torch.cuda.is_available() else "cpu"
use_fp16 = device == "cuda"
logger.info(f"Loading BGE-M3 model on {device} (fp16={use_fp16})")

model = BGEM3FlagModel('BAAI/bge-m3', use_fp16=use_fp16, device=device)
logger.info("BGE-M3 model loaded successfully")

app = FastAPI(title="FlagEmbedding Server", version="1.0.0")


class EmbedRequest(BaseModel):
    input: str | List[str]
    model: str = "BAAI/bge-m3"


class EmbedResponse(BaseModel):
    object: str = "list"
    data: List[Dict[str, Any]]
    model: str
    usage: Dict[str, int]


class TriVectorResponse(BaseModel):
    dense: List[float]
    sparse: Dict[str, float]
    colbert: Optional[List[float]] = None


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "model": "BAAI/bge-m3",
        "supports_sparse": True,
        "device": device
    }


def _safe_to_list(value) -> List[float]:
    """Convert various types (numpy, tensor, list) to flat list of floats."""
    if value is None:
        return []

    # Helper to recursively flatten nested lists
    def flatten(nested):
        result = []
        for item in nested:
            if isinstance(item, (list, tuple)):
                result.extend(flatten(item))
            else:
                result.append(item)
        return result

    # If it's already a list, flatten and convert elements to float
    if isinstance(value, list):
        try:
            return [float(x) for x in flatten(value)]
        except (TypeError, ValueError):
            return []

    # If it's a tensor with .tolist() method (pytorch, numpy, etc.)
    if hasattr(value, 'tolist'):
        try:
            result = value.tolist()
            # Flatten nested lists and convert to floats
            if isinstance(result, list):
                return [float(x) for x in flatten(result)]
            return [float(result)]
        except (AttributeError, TypeError, ValueError):
            return []

    # If it's a numpy array (without .tolist())
    if isinstance(value, np.ndarray):
        try:
            return [float(x) for x in value.flatten()]
        except (TypeError, ValueError):
            return []

    # If it's a single scalar with .item() method
    if hasattr(value, 'item'):
        try:
            return [float(value.item())]
        except (AttributeError, TypeError, ValueError):
            return []

    # Fallback: try to convert to float directly
    try:
        return [float(value)]
    except (TypeError, ValueError):
        return []


def _parse_lexical_weights(weights) -> Dict[str, float]:
    """Parse lexical_weights from various possible formats."""
    if weights is None:
        return {}

    # If it's already a dict, validate and normalize it
    if isinstance(weights, dict):
        try:
            return {str(k): float(v) for k, v in weights.items()}
        except (TypeError, ValueError):
            return {}

    # If it's a list of dicts, take the first one
    if isinstance(weights, list):
        if not weights:
            return {}
        return _parse_lexical_weights(weights[0])

    # Unexpected type
    return {}


def _extract_dense_vector(outputs: Dict[str, Any], index: int) -> List[float]:
    """Extract dense vector from model outputs with defensive parsing."""
    if not isinstance(outputs, dict):
        logger.warning(f"outputs is not a dict: {type(outputs)}")
        return []

    dense_vecs = outputs.get('dense_vecs')
    if dense_vecs is None:
        logger.warning("dense_vecs key missing from outputs")
        return []

    try:
        vec = dense_vecs[index]
    except (IndexError, TypeError) as e:
        logger.warning(f"Failed to access dense_vecs[{index}]: {e}")
        return []

    return _safe_to_list(vec)


def _extract_sparse_vector(outputs: Dict[str, Any], index: int) -> Dict[str, float]:
    """Extract sparse vector from model outputs with defensive parsing."""
    if not isinstance(outputs, dict):
        logger.warning(f"outputs is not a dict: {type(outputs)}")
        return {}

    lexical_weights = outputs.get('lexical_weights')
    if lexical_weights is None:
        logger.warning("lexical_weights key missing from outputs")
        return {}

    try:
        weights = lexical_weights[index]
    except (IndexError, TypeError) as e:
        logger.warning(f"Failed to access lexical_weights[{index}]: {e}")
        return {}

    return _parse_lexical_weights(weights)


@app.post("/embed", response_model=List[TriVectorResponse])
async def embed_tri_vector(request: EmbedRequest):
    """
    Generate tri-vector embeddings (dense + sparse + colbert).

    Returns dense vectors, sparse token weights, and null colbert (deferred).
    """
    try:
        # Validate input before encoding
        if request.input is None:
            raise HTTPException(
                status_code=400,
                detail="Invalid request: 'input' field cannot be None"
            )

        texts = request.input if isinstance(request.input, list) else [request.input]

        # Validate that texts list is not empty and contains valid strings
        if not texts:
            raise HTTPException(
                status_code=400,
                detail="Invalid request: 'input' must contain at least one text"
            )

        # Validate each text is a non-empty string
        for i, text in enumerate(texts):
            if not isinstance(text, str):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid request: 'input' at index {i} must be a string, got {type(text).__name__}"
                )
            if not text.strip():
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid request: 'input' at index {i} cannot be empty or whitespace"
                )

        # Encode with BGE-M3
        outputs = model.encode(
            texts,
            batch_size=32,
            max_length=8192,
            return_dense=True,
            return_sparse=True,
            return_colbert=False  # Deferred to Phase 7
        )

        results = []
        for i, text in enumerate(texts):
            # Extract dense vector with defensive parsing
            dense = _extract_dense_vector(outputs, i)

            # Extract sparse vector with defensive parsing
            sparse = _extract_sparse_vector(outputs, i)

            results.append(TriVectorResponse(
                dense=dense,
                sparse=sparse,
                colbert=None  # Deferred to Phase 7
            ))

        return results

    except HTTPException:
        # Re-raise HTTPException (validation errors) as-is
        raise
    except Exception as e:
        logger.error(f"Embedding failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/v1/embeddings", response_model=EmbedResponse)
async def openai_compatible_embeddings(request: EmbedRequest):
    """
    OpenAI-compatible embedding endpoint (dense vectors only).
    """
    try:
        # Validate input before encoding
        if request.input is None:
            raise HTTPException(
                status_code=400,
                detail="Invalid request: 'input' field cannot be None"
            )

        texts = request.input if isinstance(request.input, list) else [request.input]

        # Validate that texts list is not empty and contains valid strings
        if not texts:
            raise HTTPException(
                status_code=400,
                detail="Invalid request: 'input' must contain at least one text"
            )

        # Validate each text is a non-empty string
        for i, text in enumerate(texts):
            if not isinstance(text, str):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid request: 'input' at index {i} must be a string, got {type(text).__name__}"
                )
            if not text.strip():
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid request: 'input' at index {i} cannot be empty or whitespace"
                )

        outputs = model.encode(
            texts,
            batch_size=32,
            max_length=8192,
            return_dense=True,
            return_sparse=False,
            return_colbert=False
        )

        data = []
        for i, text in enumerate(texts):
            # Extract dense vector with defensive parsing
            dense = _extract_dense_vector(outputs, i)
            data.append({
                "object": "embedding",
                "embedding": dense,
                "index": i
            })

        return EmbedResponse(
            data=data,
            model="BAAI/bge-m3",
            usage={
                "prompt_tokens": sum(len(t.split()) for t in texts),
                "total_tokens": sum(len(t.split()) for t in texts)
            }
        )

    except HTTPException:
        # Re-raise HTTPException (validation errors) as-is
        raise
    except Exception as e:
        logger.error(f"Embedding failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "18080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
