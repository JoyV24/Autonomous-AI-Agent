# import_kg.py
import pandas as pd
from neo4j import GraphDatabase
import os
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

class Neo4jImporter:
    def __init__(self):
        # Correctly get variables from environment or use a default string
        self.uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = os.getenv("NEO4J_USER", "neo4j")
        self.password = os.getenv("NEO4J_PASSWORD", "password") # Use your actual password
        self.driver = None # Initialize driver to None
        try:
            self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            self.driver.verify_connectivity()
            print("✅ Successfully connected to Neo4j.")
        except Exception as e:
            print(f"❌ Failed to connect to Neo4j: {e}")

    def close(self):
        if self.driver is not None:
            self.driver.close()
            print("Connection to Neo4j closed.")

    def import_triples_from_csv(self, csv_file: str):
        """Import triples from CSV file into Neo4j"""
        if not self.driver:
            print("❌ Cannot import: Neo4j driver not connected.")
            return False

        try:
            df = pd.read_csv(csv_file)
            # 💡 ROBUSTNESS FIX: Strip whitespace from column names
            df.columns = df.columns.str.strip().str.lower()
            print(f"Detected CSV columns: {list(df.columns)}")

            imported_count = 0
            with self.driver.session() as session:
                for index, row in df.iterrows():
                    subject = str(row.get('subject', '')).strip()
                    relation = str(row.get('relation', '')).strip()
                    obj = str(row.get('object', '')).strip()

                    # 💡 DEBUGGING: Print the values being read from each row
                    print(f"--- Reading Row {index+1} ---")
                    print(f"  - Subject: '{subject}'")
                    print(f"  - Relation: '{relation}'")
                    print(f"  - Object: '{obj}'")

                    # This is the condition that decides whether to import the row
                    if subject and relation and obj:
                        pmids_field = row.get('pmids', '')
                        pmids = []
                        if pd.notna(pmids_field) and str(pmids_field).strip():
                            pmids = [p.strip() for p in str(pmids_field).split(';') if p.strip()]

                        cypher = """
                        MERGE (s:Entity {name: $subject})
                        MERGE (o:Entity {name: $object})
                        MERGE (s)-[r:RELATION {type: $relation}]->(o)
                        """
                        params = {"subject": subject, "object": obj, "relation": relation}

                        if pmids:
                            cypher += "\nSET r.pmids = $pmids"
                            params["pmids"] = pmids

                        session.run(cypher, **params)
                        imported_count += 1
                        print("  - ✅ STATUS: Imported")
                    else:
                        # 💡 DEBUGGING: Explicitly state why a row is skipped
                        print("  - ❌ STATUS: Skipped (Reason: Subject, Relation, or Object is empty)")

            print(f"\n✅ Import process finished. Successfully imported {imported_count} triples!")
            return True

        except FileNotFoundError:
            print(f"❌ Import failed: The file '{csv_file}' was not found.")
            return False
        except Exception as e:
            print(f"❌ An unexpected error occurred during import: {e}")
            return False

# --- Main execution block ---
if __name__ == "__main__":
    importer = Neo4jImporter()
    # Only attempt import if connection was successful
    if importer.driver:
        importer.import_triples_from_csv("kg_data.csv")
        importer.close()