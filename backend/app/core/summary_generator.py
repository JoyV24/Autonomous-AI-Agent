# app/core/summary_generator.py
import logging
from typing import List
from langchain.schema import HumanMessage, SystemMessage
from app.models.schema import EvidenceItem, SummarySection

logger = logging.getLogger(__name__)

SUMMARY_SYSTEM_PROMPT = """You are a biomedical research analyst. Create a concise summary of research papers.

Your task is to analyze the retrieved PubMed papers and provide a structured summary.

Return a JSON object with this structure:
{
  "overview": "Brief 2-3 sentence overview of the main research theme",
  "key_findings": [
    "Finding 1 from the papers",
    "Finding 2 from the papers", 
    "Finding 3 from the papers"
  ],
  "knowledge_gaps": [
    "Gap 1 identified in the literature",
    "Gap 2 identified in the literature"
  ],
  "implications": "1-2 sentences about research implications"
}

Guidelines:
- Focus on the most important findings across all papers
- Identify genuine research gaps, not just general statements
- Keep findings specific and evidence-based
- Maximum 5 key findings and 3 knowledge gaps
- Be concise but informative
"""

class SummaryGenerator:
    def __init__(self, llm):
        self.llm = llm
    
    def generate_summary(self, query: str, evidence: List[EvidenceItem]) -> SummarySection:
        """Generate research summary from retrieved evidence."""
        if not evidence:
            return self._create_empty_summary(query)
        
        try:
            # Prepare paper information for the prompt
            papers_info = []
            for i, paper in enumerate(evidence[:8]):  # Limit to top 8 papers
                papers_info.append({
                    "number": i + 1,
                    "pmid": paper.pmid,
                    "title": paper.title,
                    "key_points": paper.snippet[:200] + "..." if len(paper.snippet) > 200 else paper.snippet
                })
            
            # Create prompt
            messages = [
                SystemMessage(content=SUMMARY_SYSTEM_PROMPT),
                HumanMessage(content=f"""
                Research Query: {query}
                
                Retrieved Papers:
                {self._format_papers_for_prompt(papers_info)}
                
                Please analyze these papers and provide the structured summary.
                """)
            ]
            
            if self.llm and hasattr(self.llm, 'invoke'):
                response = self.llm.invoke(messages)
                response_content = getattr(response, "content", str(response))
                
                # Extract JSON from response
                import json
                import re
                
                # Clean response
                if "```json" in response_content:
                    response_content = response_content.split("```json")[1].split("```")[0].strip()
                elif "```" in response_content:
                    response_content = response_content.split("```")[1].strip()
                
                # Parse JSON
                summary_data = json.loads(response_content)
                return SummarySection(**summary_data)
                
            else:
                return self._create_fallback_summary(query, evidence)
                
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return self._create_fallback_summary(query, evidence)
    
    def _format_papers_for_prompt(self, papers_info: List[dict]) -> str:
        """Format papers information for the prompt."""
        formatted = []
        for paper in papers_info:
            formatted.append(f"Paper {paper['number']} (PMID: {paper['pmid']}):")
            formatted.append(f"Title: {paper['title']}")
            formatted.append(f"Key Content: {paper['key_points']}")
            formatted.append("---")
        return "\n".join(formatted)
    
    def _create_fallback_summary(self, query: str, evidence: List[EvidenceItem]) -> SummarySection:
        """Create a fallback summary when LLM fails."""
        key_findings = []
        for i, paper in enumerate(evidence[:3]):
            key_findings.append(f"PMID {paper.pmid}: {paper.title} - {paper.snippet[:100]}...")
        
        return SummarySection(
            overview=f"Research on {query} based on {len(evidence)} retrieved papers",
            key_findings=key_findings,
            knowledge_gaps=[
                "Need for more comprehensive studies",
                "Limited understanding of underlying mechanisms"
            ],
            implications="Suggests potential for novel therapeutic approaches"
        )
    
    def _create_empty_summary(self, query: str) -> SummarySection:
        """Create summary when no evidence is available."""
        return SummarySection(
            overview=f"No papers retrieved for query: {query}",
            key_findings=["No evidence available for analysis"],
            knowledge_gaps=["Limited research available in the database"],
            implications="Consider broadening search terms or updating the knowledge base"
        )