import logging
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.rag_pipeline import RAGPipeline

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

router = APIRouter(prefix="/api/retriever", tags=["retriever"])

# Initialize RAG pipeline (will try to load persisted Chroma if exists)
rag_pipeline = RAGPipeline(chroma_dir=Path("chroma_db"))

# Lightweight Pydantic response model to match frontend expectation
class EvidenceItem(BaseModel):
    pmid: str
    title: str
    snippet: str
    score: float
    source: str = "pubmed"

@router.get("/status")
async def vectorstore_status():
    """Check if vector store is ready."""
    return {"ready": rag_pipeline.is_ready()}

@router.post("/build-index")
async def build_index():
    """
    Build the vector store index from the CSV file.
    Expects 'pubmed_results.csv' to be at project root.
    """
    csv_path = Path("pubmed_results.csv")
    if not csv_path.exists():
        logger.error("pubmed_results.csv not found at %s", csv_path.resolve())
        raise HTTPException(
            status_code=404,
            detail="PubMed CSV not found. Place pubmed_results.csv at project root."
        )

    success = rag_pipeline.build_index(csv_path)
    if not success:
        logger.error("Failed to build vector store from CSV.")
        raise HTTPException(
            status_code=500,
            detail="Failed to build index. Check logs for details."
        )
    return {
        "message": "Index built successfully",
        "vector_dir": str(rag_pipeline.chroma_dir)
    }

@router.get("/search", response_model=List[EvidenceItem])
async def search_papers(query: str, k: int = 5):
    """
    Search for relevant papers using the vector store.
    Example: GET /api/retriever/search?query=alzheimer&k=5
    """
    if not rag_pipeline.is_ready():
        logger.warning("Search requested but vector store not ready.")
        raise HTTPException(
            status_code=503,
            detail="Vector store not ready. Build index first via POST /api/retriever/build-index"
        )

    try:
        results = rag_pipeline.retrieve(query=query, k=k)
        return [EvidenceItem(**r) for r in results]
    except Exception as e:
        logger.exception("Search error: %s", e)
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")