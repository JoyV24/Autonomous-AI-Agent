# add_sample_triples.py
from neo4j import GraphDatabase
import os
from dotenv import load_dotenv

load_dotenv()

class TripleAdder:
    def __init__(self):
        self.uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = os.getenv("NEO4J_USER", "neo4j")
        self.password = os.getenv("NEO4J_PASSWORD", "password")
        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
    
    def add_alzheimer_triples(self):
        """Add Alzheimer's disease related triples"""
        triples = [
            # Amyloid pathway
            {"subject": "Amyloid beta", "relation": "ACCUMULATES_IN", "object": "Neurons", "pmids": ["12345678", "23456789"]},
            {"subject": "Amyloid beta", "relation": "FORMS", "object": "Plaques", "pmids": ["34567890"]},
            {"subject": "Amyloid beta", "relation": "TRIGGERS", "object": "Neuroinflammation", "pmids": ["45678901"]},
            {"subject": "Plaques", "relation": "DISRUPTS", "object": "Neuronal communication", "pmids": ["56789012"]},
            
            # Tau pathology
            {"subject": "Tau protein", "relation": "HYPERPHOSPHORYLATES", "object": "Tau protein", "pmids": ["67890123"]},
            {"subject": "Tau protein", "relation": "FORMS", "object": "Neurofibrillary tangles", "pmids": ["78901234"]},
            {"subject": "Neurofibrillary tangles", "relation": "IMPAIRS", "object": "Neuronal transport", "pmids": ["89012345"]},
            
            # Inflammation
            {"subject": "Microglia", "relation": "ACTIVATES", "object": "Neuroinflammation", "pmids": ["90123456"]},
            {"subject": "Neuroinflammation", "relation": "DAMAGES", "object": "Neurons", "pmids": ["11223344"]},
            {"subject": "Cytokines", "relation": "INCREASES", "object": "Neuroinflammation", "pmids": ["22334455"]},
            
            # Risk factors
            {"subject": "APOE4", "relation": "INCREASES_RISK", "object": "Alzheimer's Disease", "pmids": ["33445566"]},
            {"subject": "Age", "relation": "PREDISPOSES_TO", "object": "Alzheimer's Disease", "pmids": ["44556677"]},
            
            # Protective factors
            {"subject": "BDNF", "relation": "PROTECTS", "object": "Neurons", "pmids": ["55667788"]},
            {"subject": "Exercise", "relation": "INCREASES", "object": "BDNF", "pmids": ["66778899"]},
            
            # Symptoms
            {"subject": "Alzheimer's Disease", "relation": "CAUSES", "object": "Memory loss", "pmids": ["77889900"]},
            {"subject": "Alzheimer's Disease", "relation": "LEADS_TO", "object": "Cognitive decline", "pmids": ["88990011"]}
        ]
        
        added_count = 0
        with self.driver.session() as session:
            for triple in triples:
                cypher = """
                MERGE (s:Entity {name: $subject})
                MERGE (o:Entity {name: $object})
                MERGE (s)-[r:RELATION {type: $relation}]->(o)
                SET r.pmids = $pmids
                """
                session.run(cypher, 
                          subject=triple["subject"],
                          object=triple["object"], 
                          relation=triple["relation"],
                          pmids=triple["pmids"])
                added_count += 1
                print(f"Added: {triple['subject']} -- {triple['relation']} --> {triple['object']}")
        
        print(f"✅ Added {added_count} triples!")
        return added_count
    
    def close(self):
        self.driver.close()

# Run the script
if __name__ == "__main__":
    adder = TripleAdder()
    adder.add_alzheimer_triples()
    adder.close()