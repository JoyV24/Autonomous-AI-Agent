# app/core/kg_pipeline.py
import os
import logging
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

try:
    from neo4j import GraphDatabase
    from neo4j.graph import Node, Relationship
    NEO4J_AVAILABLE = True
except Exception:
    GraphDatabase = None
    Node = Relationship = None
    NEO4J_AVAILABLE = False
    logger.warning("neo4j python driver not available. Install neo4j package to enable KG features.")


class KGPipeline:
    def __init__(self, uri: Optional[str] = None, user: Optional[str] = None, password: Optional[str] = None):
        self.driver = None
        if not NEO4J_AVAILABLE:
            logger.warning("Neo4j driver is not installed; KGPipeline will be disabled.")
            return

        uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = user or os.getenv("NEO4J_USER", "neo4j")
        password = password or os.getenv("NEO4J_PASSWORD")

        if not password:
            logger.warning("NEO4J_PASSWORD not set. KGPipeline will not connect until credentials are provided.")
            return

        try:
            self.driver = GraphDatabase.driver(uri, auth=(user, password))
            with self.driver.session() as s:
                s.run("RETURN 1")
            logger.info("Connected to Neo4j at %s", uri)
        except Exception as e:
            logger.exception("Failed to connect to Neo4j: %s", e)
            self.driver = None

    def close(self):
        if self.driver:
            try:
                self.driver.close()
            except Exception:
                pass

    def is_ready(self) -> bool:
        return self.driver is not None

    def execute_cypher(self, cypher_query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        if not self.is_ready():
            raise RuntimeError("Neo4j driver not connected")

        params = parameters or {}
        try:
            with self.driver.session() as session:
                result = session.run(cypher_query, **params)
                records = []
                for rec in result:
                    d = {}
                    for k in rec.keys():
                        val = rec.get(k)
                        d[k] = self._neo4j_value_to_basic(val)
                    records.append(d)
                return records
        except Exception as e:
            logger.exception("Cypher execution failed: %s", e)
            raise

    def _neo4j_value_to_basic(self, value):
        # primitives
        if value is None or isinstance(value, (str, int, float, bool)):
            return value

        # Node
        try:
            if Node is not None and isinstance(value, Node):
                props = dict(value._properties) if hasattr(value, "_properties") else dict(value)
                return {"__neo4j_node__": True, "labels": list(value.labels), "properties": props}
            if Relationship is not None and isinstance(value, Relationship):
                props = dict(value._properties) if hasattr(value, "_properties") else dict(value)
                return {"__neo4j_rel__": True, "type": value.type, "properties": props}
        except Exception:
            pass

        # fallback
        try:
            return dict(value)
        except Exception:
            try:
                return list(value)
            except Exception:
                return str(value)

    # ---------------------------
    # Helpers using new property-existence checks (IS NOT NULL)
    # ---------------------------

    def _extract_entities(self, query: str) -> List[str]:
        if not query:
            return ["disease", "treatment", "gene"]
        tokens = [t.strip().lower() for t in query.replace(",", " ").split() if len(t.strip()) > 2]
        seen = []
        for t in tokens:
            if t not in seen:
                seen.append(t)
            if len(seen) >= 6:
                break
        return seen or ["disease"]

    def query_kg(self, query: str, limit: int = 10, entities: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        if not self.is_ready():
            raise RuntimeError("Neo4j driver not connected")

        entities_to_search = entities or self._extract_entities(query)

        # Simplified query without the non-existent SUPPORTED_BY relationship
        cypher = """
        MATCH (s)-[r]->(o)
        WHERE any(entity IN $entities WHERE
            ((s.name IS NOT NULL AND toLower(s.name) CONTAINS toLower(entity)))
            OR ((s.title IS NOT NULL AND toLower(s.title) CONTAINS toLower(entity)))
            OR ((s.abstract IS NOT NULL AND toLower(s.abstract) CONTAINS toLower(entity)))
            OR ((o.name IS NOT NULL AND toLower(o.name) CONTAINS toLower(entity)))
            OR ((o.title IS NOT NULL AND toLower(o.title) CONTAINS toLower(entity)))
            OR ((o.abstract IS NOT NULL AND toLower(o.abstract) CONTAINS toLower(entity)))
            OR (toLower(type(r)) CONTAINS toLower(entity))
        )
        RETURN
            coalesce(s.name, s.title, '') AS subject,
            type(r) AS relation,
            coalesce(o.name, o.title, '') AS object,
            [] AS supporting_pmids
        LIMIT $limit
        """

        try:
            results = self.execute_cypher(cypher, {"entities": entities_to_search, "limit": limit})
            triples = []
            for rec in results:
                subj = rec.get("subject") or ""
                rel = rec.get("relation") or ""
                obj = rec.get("object") or ""
                supporting_pmids = rec.get("supporting_pmids") or []
                pmids = [str(x) for x in supporting_pmids if x is not None] if isinstance(supporting_pmids, (list, tuple)) else []
                triples.append({
                    "subject": subj,
                    "relation": rel,
                    "object": obj,
                    "supporting_pmids": pmids
                })
            return triples
        except Exception as e:
            logger.exception("query_kg failed: %s", e)
            return []

    def get_entities(self, entity_type: Optional[str] = None, search_term: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        if not self.is_ready():
            raise RuntimeError("Neo4j driver not connected")

        label_filter_clause = ""
        params = {"limit": limit}
        if entity_type:
            label_filter_clause = "WHERE any(l IN labels(n) WHERE toLower(l) = toLower($label))"
            params["label"] = entity_type

        search_clause = ""
        if search_term:
            # Only search on existing properties: name and title
            search_clause = "AND ((n.name IS NOT NULL AND toLower(n.name) CONTAINS toLower($term)) OR (n.title IS NOT NULL AND toLower(n.title) CONTAINS toLower($term)))"
            params["term"] = search_term

        # Use only existing properties: name and title (no 'label' property)
        cypher = f"""
        MATCH (n)
        {label_filter_clause}
        {search_clause}
        RETURN labels(n) AS labels, coalesce(n.name, n.title, '') AS label_value, properties(n) AS properties
        LIMIT $limit
        """

        try:
            recs = self.execute_cypher(cypher, params)
            out = []
            for r in recs:
                out.append({
                    "labels": r.get("labels", []),
                    "label_value": r.get("label_value", ""),
                    "properties": r.get("properties", {})
                })
            return out
        except Exception as e:
            logger.exception("get_entities failed: %s", e)
            return []

    def get_relations(self, limit: int = 20) -> List[str]:
        if not self.is_ready():
            raise RuntimeError("Neo4j driver not connected")
        cypher = "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType LIMIT $limit"
        try:
            recs = self.execute_cypher(cypher, {"limit": limit})
            return [r.get("relationshipType") for r in recs if r.get("relationshipType")]
        except Exception as e:
            logger.exception("get_relations failed: %s", e)
            return []

    def get_entity_neighborhood(self, entity: str, hops: int = 1, limit: int = 50) -> Dict[str, Any]:
        if not self.is_ready():
            raise RuntimeError("Neo4j driver not connected")

        cypher = f"""
        MATCH (c)
        WHERE (c.name IS NOT NULL AND toLower(c.name) = toLower($entity))
           OR (c.title IS NOT NULL AND toLower(c.title) = toLower($entity))
           OR (toLower($entity) IN [x IN labels(c) | toLower(x)])
        CALL {{
            WITH c
            MATCH (c)-[r*1..{hops}]-(n)
            RETURN collect(distinct n) as nodes, collect(distinct relationships((c)-[r]-(n))) as rels
        }}
        RETURN c, nodes, rels
        LIMIT 1
        """
        try:
            recs = self.execute_cypher(cypher, {"entity": entity})
            if not recs:
                return {"nodes": [], "relationships": []}
            r = recs[0]
            nodes = r.get("nodes") or []
            rels = r.get("rels") or []
            nodes_clean = [self._neo4j_value_to_basic(n) for n in nodes]
            rels_clean = [self._neo4j_value_to_basic(rv) for rv in rels]
            return {"nodes": nodes_clean, "relationships": rels_clean}
        except Exception as e:
            logger.exception("get_entity_neighborhood failed: %s", e)
            return {"nodes": [], "relationships": []}

    def find_paths_between_entities(self, entity1: str, entity2: str, max_path_length: int = 3, limit: int = 5) -> List[Dict[str, Any]]:
        if not self.is_ready():
            raise RuntimeError("Neo4j driver not connected")

        cypher = f"""
        MATCH p = shortestPath((a)-[*..{max_path_length}]-(b))
        WHERE
            ((a.name IS NOT NULL AND toLower(a.name) = toLower($e1)) OR (a.title IS NOT NULL AND toLower(a.title) = toLower($e1)) OR (toLower($e1) IN [x IN labels(a) | toLower(x)]))
            AND
            ((b.name IS NOT NULL AND toLower(b.name) = toLower($e2)) OR (b.title IS NOT NULL AND toLower(b.title) = toLower($e2)) OR (toLower($e2) IN [x IN labels(b) | toLower(x)]))
        RETURN p LIMIT $limit
        """
        try:
            recs = self.execute_cypher(cypher, {"e1": entity1, "e2": entity2, "limit": limit})
            out = []
            for r in recs:
                p = r.get("p")
                out.append(self._neo4j_value_to_basic(p))
            return out
        except Exception as e:
            logger.exception("find_paths_between_entities failed: %s", e)
            return []

    def get_statistics(self) -> Dict[str, Any]:
        if not self.is_ready():
            raise RuntimeError("Neo4j driver not connected")
        try:
            node_count = int(self.execute_cypher("MATCH (n) RETURN count(n) AS count")[0].get("count", 0))
            rel_count = int(self.execute_cypher("MATCH ()-[r]-() RETURN count(r) AS count")[0].get("count", 0))
            labels = self.execute_cypher("CALL db.labels() YIELD label RETURN label LIMIT 100")
            rel_types = self.execute_cypher("CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType LIMIT 100")
            return {
                "node_count": node_count,
                "relationship_count": rel_count,
                "labels": [l.get("label") for l in labels if l.get("label")],
                "relationship_types": [r.get("relationshipType") for r in rel_types if r.get("relationshipType")]
            }
        except Exception as e:
            logger.exception("get_statistics failed: %s", e)
            return {"node_count": 0, "relationship_count": 0, "labels": [], "relationship_types": []}

    def health_check(self) -> bool:
        if not self.is_ready():
            return False
        try:
            self.execute_cypher("RETURN 1")
            return True
        except Exception:
            return False