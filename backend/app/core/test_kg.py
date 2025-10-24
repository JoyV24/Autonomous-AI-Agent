# test_kg.py
import sys
import os
sys.path.append('.')

from kg_pipeline import KGPipeline

def test_kg_connection():
    print("Testing Neo4j connection...")
    
    kg = KGPipeline()
    
    if kg.is_ready():
        print("✅ Neo4j connection successful!")
        
        # Test a simple query
        triples = kg.query_kg("alzheimer", limit=5)
        print(f"Found {len(triples)} triples")
        
        for triple in triples:
            print(f"  {triple['subject']} -- {triple['relation']} --> {triple['object']}")
    else:
        print("❌ Neo4j connection failed!")

if __name__ == "__main__":
    test_kg_connection()