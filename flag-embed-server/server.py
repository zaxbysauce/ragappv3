"""
Flag Embedding Server with Reranking Support

A FastAPI server that provides:
- BGE-M3 embedding endpoints (dense + sparse vectors)
- BGE reranker v2-m3 endpoint for document reranking
"""

import logging
from typing import List, Optional, Union

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from FlagEmbedding import BGEM3FlagModel, FlagReranker

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="Flag Embedding Server", version="2.0.0")

# Determine device
device = "cuda" if torch.cuda.is_available() else "cpu"
logger.info(f"Using device: {device}")

# Load BGE-M3 embedding model
try:
    model = BGEM3FlagModel(
        "BAAI/bge-m3",
        use_fp16=True,
        device=device,
    )
    logger.info("BGE-M3 model loaded successfully")
except Exception as e:
    logger.error(f"Failed to load BGE-M3 model: {e}")
    raise

# Load BGE reranker model
try:
    reranker = FlagReranker("BAAI/bge-reranker-v2-m3", use_fp16=True, device=device)
    logger.info("BGE reranker loaded successfully")
except Exception as e:
    logger.error(f"Failed to load BGE reranker: {e}")
    raise


# ============================================================================
# Request/Response Models for Embedding
# ============================================================================


class EmbedRequest(BaseModel):
    texts: List[str]
    return_dense: bool = True
    return_sparse: bool = True
    return_colbert_vecs: bool = False


class EmbeddingData(BaseModel):
    object: str = "embedding"
    embedding: List[float]
    index: int


class EmbedResponse(BaseModel):
    dense_embeddings: Optional[List[List[float]]] = None
    sparse_embeddings: Optional[List[dict]] = None
    colbert_vecs: Optional[List[List[List[float]]]] = None


class OpenAIEmbedRequest(BaseModel):
    input: Union[str, List[str]]
    model: str = "BAAI/bge-m3"


class OpenAIEmbedResponse(BaseModel):
    object: str = "list"
    data: List[EmbeddingData]
    model: str


# ============================================================================
# Request/Response Models for Reranking
# ============================================================================


class RerankDocument(BaseModel):
    text: str


class RerankRequest(BaseModel):
    query: str
    documents: List[RerankDocument]
    top_n: Optional[int] = None


class RerankResult(BaseModel):
    index: int
    relevance_score: float
    text: Optional[str] = None


class RerankResponse(BaseModel):
    results: List[RerankResult]
    model: str


# ============================================================================
# Embedding Endpoints
# ============================================================================


@app.post("/embed", response_model=EmbedResponse)
async def embed(request: EmbedRequest):
    """
    Generate embeddings for a list of texts using BGE-M3.
    Returns dense and/or sparse embeddings based on request parameters.
    """
    try:
        output = model.encode(
            request.texts,
            return_dense=request.return_dense,
            return_sparse=request.return_sparse,
            return_colbert_vecs=request.return_colbert_vecs,
        )

        response = EmbedResponse()

        if request.return_dense:
            response.dense_embeddings = output["dense_vecs"].tolist()

        if request.return_sparse:
            sparse_output = output["lexical_weights"]
            response.sparse_embeddings = [
                {k: float(v) for k, v in sparse_dict.items()}
                for sparse_dict in sparse_output
            ]

        if request.return_colbert_vecs:
            response.colbert_vecs = output["colbert_vecs"].tolist()

        return response

    except Exception as e:
        logger.error(f"Embedding failed: {e}")
        raise HTTPException(status_code=500, detail="Embedding failed")


@app.post("/v1/embeddings", response_model=OpenAIEmbedResponse)
async def openai_embeddings(request: OpenAIEmbedRequest):
    """
    OpenAI-compatible embedding endpoint.
    Returns dense embeddings only in OpenAI format.
    """
    try:
        # Normalize input to list (OpenAI API accepts both str and List[str])
        texts = request.input if isinstance(request.input, list) else [request.input]
        output = model.encode(
            texts,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )

        data = []
        for i, embedding in enumerate(output["dense_vecs"]):
            data.append(
                EmbeddingData(
                    object="embedding",
                    embedding=embedding.tolist(),
                    index=i,
                )
            )

        return OpenAIEmbedResponse(
            object="list",
            data=data,
            model="BAAI/bge-m3",
        )

    except Exception as e:
        logger.error(f"OpenAI embedding failed: {e}")
        raise HTTPException(status_code=500, detail="Embedding failed")


# ============================================================================
# Reranking Endpoint
# ============================================================================


@app.post("/v1/rerank", response_model=RerankResponse)
async def rerank(request: RerankRequest):
    """Rerank documents using BGE reranker."""
    try:
        query = request.query
        docs = [doc.text for doc in request.documents]
        pairs = [[query, doc] for doc in docs]

        scores = reranker.compute_score(
            pairs,
            batch_size=32,
            max_length=512,
        )

        results = []
        indexed = [(i, float(scores[i])) for i in range(len(docs))]
        indexed.sort(key=lambda x: x[1], reverse=True)

        top_n = request.top_n if request.top_n else len(docs)

        for idx, score in indexed[:top_n]:
            results.append(
                RerankResult(
                    index=idx,
                    relevance_score=score,
                    text=request.documents[idx].text,
                )
            )

        return RerankResponse(
            results=results,
            model="BAAI/bge-reranker-v2-m3",
        )

    except Exception as e:
        logger.error(f"Rerank failed: {e}")
        raise HTTPException(status_code=500, detail="Reranking failed")


# ============================================================================
# Health Endpoint
# ============================================================================


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "supports_sparse": True,
        "models": {
            "embedding": "BAAI/bge-m3",
            "reranker": "BAAI/bge-reranker-v2-m3",
        },
        "device": device,
    }


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=18080)
