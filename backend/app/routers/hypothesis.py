# app/routers/hypothesis.py
import logging
from typing import List, Optional, Any, Dict
from pathlib import Path

from fastapi import APIRouter, HTTPException

# Import your existing pipelines
from app.core.rag_pipeline import RAGPipeline
from app.core.kg_pipeline import KGPipeline
from app.core.llm_agent import LLMAgent
from app.core.summary_generator import SummaryGenerator
from app.models.schema import (
    QueryRequest, HypothesisResponse, EvidenceItem, KGTriple, 
    Hypothesis, SuggestedExperiment, HypothesisType, Plausibility,
    SummarySection
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

router = APIRouter(prefix="/api/hypothesis", tags=["hypothesis"])

# Initialize pipelines
VECTOR_DIR = Path("chroma_db")
try:
    rag_pipeline = RAGPipeline(chroma_dir=VECTOR_DIR)
except Exception:
    rag_pipeline = RAGPipeline(chroma_dir=VECTOR_DIR)

try:
    kg_pipeline = KGPipeline()
except Exception:
    kg_pipeline = KGPipeline()

# Initialize LLM Agent
try:
    llm_agent = LLMAgent()
except Exception as e:
    logger.warning(f"LLM Agent initialization failed: {e}")
    llm_agent = None

# -------------------------
# Helper utilities
# -------------------------
def get_field(item: Any, field: str, default: Any = None) -> Any:
    """Safely return a field from either a dict or an object with attributes."""
    if item is None:
        return default
    if isinstance(item, dict):
        return item.get(field, default)
    return getattr(item, field, default)

def create_fallback_hypothesis(query: str, evidence: List[EvidenceItem], kg_triples: List[KGTriple]) -> List[Hypothesis]:
    """Create basic hypothesis structure from available evidence."""
    hypotheses = []
    
    if evidence:
        supporting_evidence = []
        for i, ev in enumerate(evidence[:3]):
            supporting_evidence.append(f"PMID {ev.pmid}: {ev.title} - {ev.snippet[:100]}...")
        
        hypothesis = Hypothesis(
            id="H1",
            statement=f"Potential therapeutic intervention for {query} based on molecular mechanisms identified in literature",
            type=HypothesisType.EVIDENCE_BACKED,
            plausibility=Plausibility.MEDIUM,
            confidence_score=0.6,
            supporting_evidence=supporting_evidence,
            mechanistic_rationale="Based on associations between key biological pathways and disease mechanisms identified in the retrieved literature. The evidence suggests potential targets for intervention.",
            suggested_experiment=SuggestedExperiment(
                model="In vitro neuronal cell culture",
                intervention="Small molecule screening targeting identified pathways",
                primary_outcome="Reduction in pathological biomarkers",
                design_summary="Dose-response study with appropriate controls",
                safety_measures="Standard laboratory safety protocols and ethical guidelines"
            ),
            limitations="Limited by the scope of available literature and requires experimental validation in relevant models."
        )
        hypotheses.append(hypothesis)
    
    return hypotheses

def create_fallback_summary(query: str, evidence: List[EvidenceItem]) -> SummarySection:
    """Create fallback summary."""
    key_findings = []
    for i, paper in enumerate(evidence[:3]):
        key_findings.append(f"PMID {paper.pmid}: {paper.title} - {paper.snippet[:100]}...")
    
    return SummarySection(
        overview=f"Research analysis on '{query}' based on {len(evidence)} retrieved papers",
        key_findings=key_findings,
        knowledge_gaps=[
            "Need for more comprehensive mechanistic studies",
            "Limited understanding of underlying molecular pathways"
        ],
        implications="Suggests potential for developing novel therapeutic approaches targeting identified mechanisms"
    )

# -------------------------
# Status endpoint
# -------------------------
@router.get("/status")
async def hypothesis_status():
    """Status/health for hypothesis pipeline."""
    try:
        vs_ready = False
        try:
            vs_ready = bool(getattr(rag_pipeline, "is_ready", lambda: False)())
        except Exception as e:
            logger.debug("Vector store status check failed: %s", e)
            vs_ready = False

        kg_ready = False
        try:
            kg_ready = bool(getattr(kg_pipeline, "is_ready", lambda: False)())
        except Exception as e:
            logger.debug("KG status check failed: %s", e)
            kg_ready = False

        llm_ready = bool(llm_agent and llm_agent.is_ready())

        return {
            "pubmed_loaded": True,
            "chroma_ready": vs_ready,
            "neo4j_ready": kg_ready,
            "llm_ready": llm_ready
        }
    except Exception as e:
        logger.exception("hypothesis_status failed: %s", e)
        return {
            "pubmed_loaded": False,
            "chroma_ready": False,
            "neo4j_ready": False,
            "llm_ready": False
        }

# -------------------------
# Main generate route
# -------------------------
@router.post("/generate", response_model=HypothesisResponse)
async def generate_hypothesis(payload: QueryRequest):
    """Generate hypotheses using RAG, KG, and LLM synthesis."""
    query = (payload.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query must not be empty.")

    # Ensure vector store is ready
    try:
        if not getattr(rag_pipeline, "is_ready", lambda: False)():
            logger.error("Vector store is not ready")
            raise HTTPException(status_code=503, detail="Vector store not ready. Build the index first.")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error checking vector store readiness: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error checking vector store")

    # 1) Retrieve evidence
    try:
        raw_results = rag_pipeline.retrieve(query=query, k=payload.top_k)
    except Exception as e:
        logger.exception("Error during vector retrieval: %s", e)
        raise HTTPException(status_code=500, detail=f"Retrieval error: {str(e)}")

    evidence_out: List[EvidenceItem] = []
    missing_pmid_count = 0

    # Convert results into EvidenceItem
    for item in raw_results or []:
        pmid = get_field(item, "pmid")
        title = get_field(item, "title", "")
        snippet = get_field(item, "snippet", "")
        score = get_field(item, "score", None)
        source = get_field(item, "source", "pubmed")

        if not pmid or str(pmid).strip() == "":
            missing_pmid_count += 1
            continue

        pmid = str(pmid)
        try:
            evidence_out.append(EvidenceItem(
                pmid=pmid, 
                title=title or "No title", 
                snippet=snippet or "No snippet", 
                score=score, 
                source=source
            ))
        except Exception as e:
            logger.debug("Failed to append evidence item: %s", e)
            missing_pmid_count += 1
            continue

    # 2) Query KG for related triples
    kg_triples_out: List[KGTriple] = []
    try:
        entities = []
        q_tokens = [t.strip() for t in query.split() if len(t) > 2]
        entities.extend(q_tokens[:6])
        
        for ev in evidence_out[:3]:
            if ev.title:
                title_tokens = [t.strip() for t in ev.title.split() if len(t) > 2]
                entities.extend(title_tokens[:3])

        # Dedupe entities
        seen = set()
        entities_unique = []
        for e in entities:
            key = e.lower()
            if key not in seen:
                seen.add(key)
                entities_unique.append(e)

        if getattr(kg_pipeline, "is_ready", lambda: False)():
            raw_triples = kg_pipeline.query_kg(query=query, limit=10, entities=entities_unique or None)
            for t in raw_triples or []:
                if isinstance(t, dict):
                    subj = t.get("subject", "") or ""
                    rel = t.get("relation", "") or ""
                    obj = t.get("object", "") or ""
                    pmids = t.get("supporting_pmids", []) or []
                else:
                    subj = getattr(t, "subject", "") or ""
                    rel = getattr(t, "relation", "") or ""
                    obj = getattr(t, "object", "") or ""
                    pmids = getattr(t, "supporting_pmids", []) or []

                pmids_list = [str(x) for x in pmids if x]
                try:
                    kg_triples_out.append(KGTriple(
                        subject=subj, 
                        relation=rel, 
                        object=obj, 
                        supporting_pmids=pmids_list
                    ))
                except Exception:
                    logger.debug("Invalid KG triple skipped: %r", t)
        else:
            logger.info("KG pipeline not ready; skipping KG lookup.")
    except Exception as e:
        logger.exception("Error querying KG: %s", e)
        kg_triples_out = []

    # 3) Generate summary
    summary_out = None
    try:
        if llm_agent:
            summary_out = llm_agent.generate_summary(query, evidence_out)
        else:
            summary_out = create_fallback_summary(query, evidence_out)
    except Exception as e:
        logger.exception("Error generating summary: %s", e)
        summary_out = create_fallback_summary(query, evidence_out)

    # 4) Generate hypotheses using LLM or fallback
    hypotheses_out = []
    note = f"Retrieved {len(evidence_out)} evidence items. {missing_pmid_count} items skipped due to missing pmid."

    try:
        if llm_agent and llm_agent.is_ready():
            # Use LLM for hypothesis generation
            llm_response = llm_agent.generate_hypothesis(payload, evidence_out, kg_triples_out)
            hypotheses_out = llm_response.hypotheses
            # Use the summary from LLM agent (it already generates one)
            summary_out = llm_response.summary or summary_out
            note = llm_response.note or note
        else:
            # Fallback to basic hypothesis generation
            hypotheses_out = create_fallback_hypothesis(query, evidence_out, kg_triples_out)
            note += " Used fallback hypothesis generation (LLM not available)."
            
    except Exception as e:
        logger.exception("Error in hypothesis generation: %s", e)
        hypotheses_out = create_fallback_hypothesis(query, evidence_out, kg_triples_out)
        note += f" Error in LLM generation: {str(e)}. Used fallback."

    return HypothesisResponse(
        query=query,
        summary=summary_out,
        hypotheses=hypotheses_out,
        evidence=evidence_out,
        kg_triples=kg_triples_out,
        note=note
    )
