from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.services import retrieval

router = APIRouter(tags=["retrieval"])


class RetrieveRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=retrieval.DEFAULT_TOP_K, ge=1, le=retrieval.MAX_TOP_K)


@router.post("/retrieve")
def retrieve_chunks(payload: RetrieveRequest, session: Session = Depends(get_session)):
    try:
        result = retrieval.retrieve(session, query=payload.query, top_k=payload.top_k)
    except retrieval.RetrievalError as exc:
        raise HTTPException(
            status_code=409,
            detail={"error": "retrieval_failed", "reason": str(exc)},
        )
    return {
        "query": result.query,
        "embedding_model": result.embedding_model,
        "embedding_dim": result.embedding_dim,
        "top_k": result.top_k,
        "results": [asdict(r) for r in result.results],
    }
