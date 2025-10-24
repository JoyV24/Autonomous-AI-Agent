# app/routers/kg.py
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Dict, Any
import logging
import os

from app.models.schema import KGTriple, KGQueryResponse  # ensure these pydantic models exist
from app.core.kg_pipeline import KGPipeline

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

router = APIRouter(prefix="/api/kg", tags=["knowledge-graph"])

# initialize pipeline (reads env vars)
kg_pipeline = KGPipeline()


@router.get("/query", response_model=KGQueryResponse)
async def query_kg(
    query: str = Query(..., description="Natural language query to extract entities from"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type (gene, disease, drug, etc.)"),
    relation_type: Optional[str] = Query(None, description="Filter by relation type"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of triples to return")
):
    if not kg_pipeline.is_ready():
        raise HTTPException(status_code=503, detail="Knowledge Graph pipeline not ready. Please check Neo4j connection.")
    try:
        logger.info("KG Query: %s", query)
        triples = kg_pipeline.query_kg(query=query, limit=limit)
        # apply optional filters
        if entity_type:
            triples = [t for t in triples if entity_type.lower() in (t.get("subject","").lower() or "") or entity_type.lower() in (t.get("object","").lower() or "")]
        if relation_type:
            triples = [t for t in triples if relation_type.lower() in (t.get("relation","").lower() or "")]
        return KGQueryResponse(
            query=query,
            triples=[KGTriple(**t) if not isinstance(t, KGTriple) else t for t in triples],
            total_count=len(triples),
            note=f"Found {len(triples)} relevant triples"
        )
    except Exception as e:
        logger.exception("Error querying KG: %s", e)
        raise HTTPException(status_code=500, detail=f"KG query error: {str(e)}")


@router.get("/entities", response_model=Dict[str, Any])
async def get_entities(
    entity_type: Optional[str] = Query(None),
    search_term: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=200)
):
    if not kg_pipeline.is_ready():
        raise HTTPException(status_code=503, detail="Knowledge Graph not available")
    try:
        entities = kg_pipeline.get_entities(entity_type=entity_type, search_term=search_term, limit=limit)
        return {"entities": entities, "total_count": len(entities)}
    except Exception as e:
        logger.exception("Error retrieving entities: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/relations", response_model=Dict[str, Any])
async def get_relations(limit: int = Query(20, ge=1, le=200)):
    if not kg_pipeline.is_ready():
        raise HTTPException(status_code=503, detail="Knowledge Graph not available")
    try:
        relations = kg_pipeline.get_relations(limit=limit)
        return {"relations": relations, "total_count": len(relations)}
    except Exception as e:
        logger.exception("Error retrieving relations: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/neighborhood/{entity}", response_model=Dict[str, Any])
async def get_entity_neighborhood(entity: str, hops: int = Query(1, ge=1, le=3), limit: int = Query(50)):
    if not kg_pipeline.is_ready():
        raise HTTPException(status_code=503, detail="Knowledge Graph not available")
    try:
        nb = kg_pipeline.get_entity_neighborhood(entity=entity, hops=hops, limit=limit)
        return {"central_entity": entity, "hops": hops, "neighborhood": nb}
    except Exception as e:
        logger.exception("Error retrieving neighborhood: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/path/{entity1}/{entity2}", response_model=Dict[str, Any])
async def find_path_between_entities(entity1: str, entity2: str, max_path_length: int = Query(3, ge=1, le=5), limit: int = Query(5, ge=1, le=50)):
    if not kg_pipeline.is_ready():
        raise HTTPException(status_code=503, detail="Knowledge Graph not available")
    try:
        paths = kg_pipeline.find_paths_between_entities(entity1=entity1, entity2=entity2, max_path_length=max_path_length, limit=limit)
        return {"entity1": entity1, "entity2": entity2, "paths": paths}
    except Exception as e:
        logger.exception("Error finding paths: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=Dict[str, Any])
async def get_kg_statistics():
    if not kg_pipeline.is_ready():
        raise HTTPException(status_code=503, detail="Knowledge Graph not available")
    try:
        stats = kg_pipeline.get_statistics()
        return stats
    except Exception as e:
        logger.exception("Error retrieving KG statistics: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def kg_health_check():
    try:
        is_healthy = kg_pipeline.health_check()
        return {"status": "healthy" if is_healthy else "unhealthy", "neo4j_available": kg_pipeline.is_ready()}
    except Exception as e:
        logger.exception("Health check failed: %s", e)
        return {"status": "unhealthy", "neo4j_available": False, "error": str(e)}


@router.post("/cypher")
async def execute_cypher_query(
    cypher_query: str = Query(..., description="Cypher query string"),
    parameters: Optional[Dict[str, Any]] = None
):
    """
    Execute a custom read-only Cypher query. Basic check prevents destructive keywords.
    """
    if not kg_pipeline.is_ready():
        raise HTTPException(status_code=503, detail="Knowledge Graph not available")

    # Basic safety: disallow writes/destructive keywords in the query
    dangerous = {"DROP", "DELETE", "REMOVE", "CREATE", "MERGE", "SET", "DETACH"}
    if any(tok in cypher_query.upper() for tok in dangerous):
        raise HTTPException(status_code=400, detail="Query appears to contain write/destructive operations. Only read queries allowed.")

    try:
        results = kg_pipeline.execute_cypher(cypher_query, parameters or {})
        return {"query": cypher_query, "parameters": parameters or {}, "results": results, "result_count": len(results)}
    except Exception as e:
        logger.exception("Error executing cypher query: %s", e)
        raise HTTPException(status_code=500, detail=f"Error executing Cypher query: {str(e)}")
    
@router.get("/test-connection")
async def test_kg_connection():
    """Test KG connection and basic functionality."""
    try:
        if not kg_pipeline.is_ready():
            return {
                "status": "error",
                "message": "KG pipeline not ready. Check Neo4j connection.",
                "neo4j_uri": os.getenv("NEO4J_URI", "Not set"),
                "neo4j_user": os.getenv("NEO4J_USER", "Not set"),
                "neo4j_password_set": bool(os.getenv("NEO4J_PASSWORD"))
            }
        
        # Test a simple query
        test_triples = kg_pipeline.query_kg("alzheimer", limit=5)
        
        return {
            "status": "success",
            "kg_ready": kg_pipeline.is_ready(),
            "test_triples_found": len(test_triples),
            "neo4j_connected": True,
            "sample_triples": test_triples[:2]  # Show first 2 for debugging
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "kg_ready": kg_pipeline.is_ready()
        }