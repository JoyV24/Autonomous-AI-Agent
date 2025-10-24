from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum

class HypothesisType(str, Enum):
    EVIDENCE_BACKED = "evidence-backed"
    ANALOGY_DERIVED = "analogy-derived"
    SPECULATIVE = "speculative"

class Plausibility(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"

class EvidenceItem(BaseModel):
    pmid: str = Field(..., description="PubMed ID")
    title: str = Field(..., description="Paper title")
    snippet: str = Field(..., description="Relevant text snippet")
    score: Optional[float] = Field(None, description="Relevance score")
    source: Optional[str] = Field("pubmed", description="Source of evidence")

class SummarySection(BaseModel):
    overview: str = Field(..., description="Brief overview of the research area")
    key_findings: List[str] = Field(..., description="List of key findings from papers")
    knowledge_gaps: List[str] = Field(..., description="Identified research gaps")
    implications: str = Field(..., description="Research implications")

class KGTriple(BaseModel):
    subject: str = Field(..., description="Subject entity")
    relation: str = Field(..., description="Relation type")
    object: str = Field(..., description="Object entity")
    supporting_pmids: List[str] = Field(default_factory=list, description="Supporting PubMed IDs")

class SuggestedExperiment(BaseModel):
    model: str = Field(..., description="Experimental model")
    intervention: str = Field(..., description="Intervention details")
    primary_outcome: str = Field(..., description="Primary outcome measure")
    design_summary: str = Field(..., description="Experimental design summary")
    safety_measures: Optional[str] = Field(None, description="Safety/ethical measures")

class Hypothesis(BaseModel):
    id: str = Field(..., description="Hypothesis ID (H1, H2, etc.)")
    statement: str = Field(..., description="Testable hypothesis statement")
    type: HypothesisType = Field(HypothesisType.EVIDENCE_BACKED, description="Type of hypothesis")
    plausibility: Plausibility = Field(Plausibility.MEDIUM, description="Plausibility rating")
    confidence_score: float = Field(0.7, ge=0.0, le=1.0, description="Confidence score 0-1")
    supporting_evidence: List[str] = Field(default_factory=list, description="List of evidence snippets")
    mechanistic_rationale: str = Field(..., description="Mechanistic rationale")
    suggested_experiment: SuggestedExperiment = Field(..., description="Experimental design")
    limitations: str = Field(..., description="Limitations and uncertainties")

class QueryRequest(BaseModel):
    query: str = Field(..., description="Research query")
    seeded_input: Optional[str] = Field(None, description="Optional seed PMID or text")
    top_k: int = Field(5, ge=1, le=20, description="Number of papers to retrieve")
    creative_mode: bool = Field(False, description="Enable creative/analogy mode")
    temperature: float = Field(0.0, ge=0.0, le=1.0, description="LLM temperature")

class HypothesisResponse(BaseModel):
    query: str = Field(..., description="Original query")
    summary: Optional[SummarySection] = Field(None, description="Research summary") 
    hypotheses: List[Hypothesis] = Field(default_factory=list, description="Generated hypotheses")
    evidence: List[EvidenceItem] = Field(default_factory=list, description="Retrieved evidence")
    kg_triples: List[KGTriple] = Field(default_factory=list, description="Knowledge graph triples")
    note: Optional[str] = Field(None, description="Optional note")

class StatusResponse(BaseModel):
    pubmed_loaded: bool = Field(..., description="PubMed data status")
    chroma_ready: bool = Field(..., description="Chroma index status")
    neo4j_ready: bool = Field(..., description="Neo4j connection status")
    llm_ready: bool = Field(..., description="LLM connection status")

class KGQueryResponse(BaseModel):
    query: str = Field(..., description="Original query string")
    triples: List[KGTriple] = Field(default_factory=list, description="List of knowledge graph triples found")
    total_count: int = Field(..., description="Total number of triples found", ge=0)
    note: Optional[str] = Field(None, description="Additional information or notes about the query results")

    class Config:
        schema_extra = {
            "example": {
                "query": "alzheimer disease treatment",
                "triples": [
                    {
                        "subject": "NLRP3",
                        "relation": "INVOLVED_IN",
                        "object": "Neuroinflammation",
                        "supporting_pmids": ["12345678", "23456789"]
                    }
                ],
                "total_count": 1,
                "note": "Found 1 relevant triple for the query"
            }
        }