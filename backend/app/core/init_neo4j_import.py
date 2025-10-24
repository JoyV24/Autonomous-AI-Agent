from neo4j import GraphDatabase
import pandas as pd

# === CONFIG ===
CSV_PATH = "pubmed_results.csv"  # adjust path if needed
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = "joyabi2005"

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))

def load_papers(tx, pmid, title, abstract):
    tx.run(
        """
        MERGE (p:Paper {pmid: $pmid})
        SET p.title = $title,
            p.abstract = $abstract
        """,
        pmid=str(pmid), title=title, abstract=abstract
    )

df = pd.read_csv(CSV_PATH)

with driver.session() as session:
    for _, row in df.iterrows():
        session.execute_write(load_papers, row["PMID"], row["Title"], row["Abstract"])

print(f"✅ Loaded {len(df)} papers into Neo4j.")
