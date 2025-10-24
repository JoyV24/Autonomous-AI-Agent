import json
import os
import re
from typing import List, Dict, Optional
from langchain.schema import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from app.models.schema import (
    HypothesisResponse, EvidenceItem, KGTriple, QueryRequest, 
    Hypothesis, SuggestedExperiment, SummarySection
)
from app.core.summary_generator import SummaryGenerator
from app.core.prompt_template import HYPOTHESIS_SYSTEM_PROMPT
from dotenv import load_dotenv

load_dotenv()

class LLMAgent:
    def __init__(self):
        self.llm = None
        self.summary_generator = None
        self._initialize_llm()
        self._initialize_summary_generator()

    def _initialize_llm(self):
        """Initialize LLM with available API keys."""
        if os.getenv("OPENAI_API_KEY"):
            self.llm = ChatOpenAI(
                temperature=0.0,
                model="gpt-3.5-turbo",
                max_tokens=4000
            )
            print("✅ Using OpenAI GPT-3.5-turbo")
        elif os.getenv("GROQ_API_KEY"):
            self.llm = ChatGroq(
                temperature=0.0,
                model="mixtral-8x7b-32768",
                max_tokens=4000
            )
            print("✅ Using Groq Mixtral")
        else:
            print("❌ No LLM API keys found. Using fallback mode.")
            self.llm = None

    def _initialize_summary_generator(self):
        """Initialize summary generator."""
        self.summary_generator = SummaryGenerator(self.llm)

    def is_ready(self) -> bool:
        """Check if LLM agent is ready."""
        return self.llm is not None and hasattr(self.llm, "invoke")

    def _clean_json_response(self, response_content: str) -> str:
        """Clean and extract JSON from LLM response."""
        if not isinstance(response_content, str):
            response_content = str(response_content)
        
        # Remove markdown code blocks
        if "```json" in response_content:
            response_content = response_content.split("```json")[1].split("```")[0].strip()
        elif "```" in response_content:
            response_content = response_content.split("```")[1].strip()
        
        # Fix common JSON issues
        response_content = re.sub(r',\s*}', '}', response_content)
        response_content = re.sub(r',\s*]', ']', response_content)
        
        # Ensure it starts with {
        if not response_content.strip().startswith("{"):
            match = re.search(r'\{.*\}', response_content, re.DOTALL)
            if match:
                response_content = match.group()
            else:
                raise ValueError("No JSON object found in response")
        
        return response_content.strip()

    def generate_summary(self, query: str, evidence: List[EvidenceItem]) -> SummarySection:
        """Generate research summary from evidence."""
        if self.summary_generator:
            return self.summary_generator.generate_summary(query, evidence)
        else:
            return SummarySection(
                overview=f"Analysis of {len(evidence)} papers on {query}",
                key_findings=[f"Found {len(evidence)} relevant papers for analysis"],
                knowledge_gaps=["Further detailed analysis required"],
                implications="Potential for generating novel research hypotheses"
            )

    def _create_fallback_hypothesis(self, query: str, evidence: List[EvidenceItem], summary: SummarySection = None) -> HypothesisResponse:
        """Create a fallback hypothesis when LLM fails."""
        if summary is None:
            summary = self.generate_summary(query, evidence)
            
        supporting_evidence = []
        for i, ev in enumerate(evidence[:3]):
            supporting_evidence.append(f"PMID {ev.pmid}: {ev.title} - {ev.snippet[:100]}...")
        
        hypothesis = Hypothesis(
            id="H1",
            statement=f"Potential therapeutic intervention for {query} targeting key molecular pathways identified in literature",
            type="evidence-backed",
            plausibility="Medium",
            confidence_score=0.6,
            supporting_evidence=supporting_evidence,
            mechanistic_rationale="Based on associations between biological pathways and disease mechanisms identified in retrieved literature. The evidence suggests potential targets for intervention.",
            suggested_experiment=SuggestedExperiment(
                model="In vitro cell culture model",
                intervention="Compound screening targeting identified pathways",
                primary_outcome="Reduction in pathological biomarkers",
                design_summary="Dose-response study with appropriate controls",
                safety_measures="Standard laboratory safety protocols"
            ),
            limitations="Limited by available literature scope and requires experimental validation."
        )
        
        return HypothesisResponse(
            query=query,
            summary=summary,
            hypotheses=[hypothesis],
            evidence=evidence,
            kg_triples=[],
            note="Generated using fallback method (LLM parsing failed)"
        )

    def generate_hypothesis(
        self,
        request: QueryRequest,
        evidence: List[EvidenceItem],
        kg_triples: List[KGTriple]
    ) -> HypothesisResponse:
        """Generate hypotheses using structured prompt."""
        # Generate summary first
        print("📊 Generating research summary...")
        summary = self.generate_summary(request.query, evidence)
        
        if not self.is_ready():
            print("LLM not ready, using fallback")
            return self._create_fallback_hypothesis(request.query, evidence, summary)

        # Set temperature based on creative mode
        temperature = request.temperature if hasattr(request, 'temperature') else 0.0
        if hasattr(self.llm, 'temperature'):
            self.llm.temperature = temperature

        # Prepare inputs for the prompt
        retrieved_passages = [
            {
                "pmid": item.pmid,
                "title": item.title,
                "snippet": item.snippet,
                "score": item.score
            }
            for item in evidence[:5]
        ]

        kg_results = [
            {
                "subject": triple.subject,
                "relation": triple.relation,
                "object": triple.object,
                "supporting_pmids": triple.supporting_pmids
            }
            for triple in kg_triples[:3]
        ]

        # Create messages
        messages = [
            SystemMessage(content=HYPOTHESIS_SYSTEM_PROMPT),
            HumanMessage(content=json.dumps({
                "USER_QUERY": request.query,
                "RETRIEVED_PASSAGES": retrieved_passages,
                "KG_RESULTS": kg_results,
                "OPTIONAL_SEEDED_TEXT": getattr(request, "seeded_input", None)
            }, indent=2))
        ]

        try:
            print("🔄 Calling LLM for hypotheses...")
            response = self.llm.invoke(messages)
            response_content = getattr(response, "content", str(response))
            
            print(f"📄 Raw LLM response length: {len(response_content)}")

            # Clean response text
            cleaned_content = self._clean_json_response(response_content)
            print(f"🧹 Cleaned JSON length: {len(cleaned_content)}")

            # Parse JSON
            parsed_response = json.loads(cleaned_content)
            print("✅ Successfully parsed LLM response")

            # Validate and convert to HypothesisResponse
            if "hypotheses" in parsed_response:
                hypotheses_list = []
                for i, hyp_data in enumerate(parsed_response["hypotheses"]):
                    try:
                        if "suggested_experiment" not in hyp_data:
                            hyp_data["suggested_experiment"] = {
                                "model": "Not specified",
                                "intervention": "Not specified", 
                                "primary_outcome": "Not specified",
                                "design_summary": "Not specified"
                            }
                        
                        hypothesis = Hypothesis(**hyp_data)
                        hypotheses_list.append(hypothesis)
                    except Exception as e:
                        print(f"⚠️ Failed to parse hypothesis {i}: {e}")
                        continue

                return HypothesisResponse(
                    query=parsed_response.get("query", request.query),
                    summary=summary,
                    hypotheses=hypotheses_list,
                    evidence=evidence,
                    kg_triples=kg_triples,
                    note=parsed_response.get("note", "Hypotheses generated successfully with research summary")
                )
            else:
                print("❌ No 'hypotheses' key in LLM response")
                return self._create_fallback_hypothesis(request.query, evidence, summary)

        except json.JSONDecodeError as e:
            print(f"❌ JSON decode error: {e}")
            return self._create_fallback_hypothesis(request.query, evidence, summary)
        except Exception as e:
            print(f"❌ Error in LLM generation: {e}")
            return self._create_fallback_hypothesis(request.query, evidence, summary)