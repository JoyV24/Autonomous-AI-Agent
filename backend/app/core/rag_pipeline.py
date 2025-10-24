import logging
import shutil
from pathlib import Path
from typing import List

import pandas as pd
from langchain.docstore.document import Document
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.vectorstores import Chroma

# Configure logger for the module
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class RAGPipeline:
    """
    Responsible for:
     - initializing embeddings & loading a persisted Chroma vector store (if present)
     - building the vector index from a PubMed CSV
     - retrieving top-k results for a query
    """

    def __init__(
        self,
        chroma_dir: Path = Path("chroma_db"),
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    ):
        self.chroma_dir = Path(chroma_dir)
        self.model_name = model_name
        self.embeddings = None
        self.vectorstore = None
        self._initialize_embeddings_and_store()

    def _initialize_embeddings_and_store(self) -> None:
        """Create embedding model and load persisted Chroma store if available."""
        try:
            logger.info("Initializing embeddings model: %s", self.model_name)
            self.embeddings = HuggingFaceEmbeddings(model_name=self.model_name)

            if self.chroma_dir.exists() and any(self.chroma_dir.iterdir()):
                logger.info("Found existing Chroma directory: %s. Loading.", self.chroma_dir)
                self.vectorstore = Chroma(
                    persist_directory=str(self.chroma_dir),
                    embedding_function=self.embeddings,
                )
                logger.info("Vector store loaded successfully.")
            else:
                logger.info("No existing Chroma store found at: %s", self.chroma_dir)
        except Exception as e:
            logger.exception("Error initializing embeddings/vectorstore: %s", e)
            self.vectorstore = None

    def is_ready(self) -> bool:
        """Return True if vectorstore is available."""
        return self.vectorstore is not None

    def build_index(self, csv_path: Path) -> bool:
        """
        Build a Chroma index from a CSV file.
        Expected CSV columns (case-sensitive): 'PMID', 'Title', 'Abstract'
        Returns True on success.
        """
        csv_path = Path(csv_path)
        try:
            if not csv_path.exists():
                logger.error("CSV file not found: %s", csv_path)
                return False

            logger.info("Reading CSV: %s", csv_path)
            df = pd.read_csv(csv_path)

            required_cols = ["PMID", "Title", "Abstract"]
            if not all(col in df.columns for col in required_cols):
                logger.error("CSV missing required columns. Required: %s", required_cols)
                return False

            documents: List[str] = []
            metadatas: List[dict] = []

            for _, row in df.iterrows():
                pmid = str(row.get("PMID", "")).strip()
                if not pmid or pmid.lower() in {"nan", "none", ""}:
                    continue

                title = str(row.get("Title", "")).strip()
                abstract = str(row.get("Abstract", "")).strip()

                text = f"Title: {title}\n\nAbstract: {abstract}"
                documents.append(text)
                metadatas.append(
                    {
                        "pmid": pmid,
                        "title": title,
                        "abstract": abstract,
                        "source": "pubmed",
                    }
                )

            if not documents:
                logger.warning("No valid documents extracted from CSV.")
                return False

            if self.chroma_dir.exists():
                logger.info("Removing existing Chroma directory: %s", self.chroma_dir)
                shutil.rmtree(self.chroma_dir)

            logger.info("Creating new Chroma vector store. This may take a while...")
            vectorstore = Chroma.from_texts(
                texts=documents,
                metadatas=metadatas,
                embedding=self.embeddings,
                persist_directory=str(self.chroma_dir),
            )
            vectorstore.persist()

            self.vectorstore = Chroma(
                persist_directory=str(self.chroma_dir),
                embedding_function=self.embeddings,
            )
            logger.info("Chroma index built and persisted at: %s", self.chroma_dir)
            return True

        except Exception as e:
            logger.exception("Failed to build Chroma index: %s", e)
            return False

    def retrieve(self, query: str, k: int = 5):
        """
        Retrieve top-k similar documents from the vector store.
        Returns a list of doc-like objects (with metadata and score).
        """
        if not self.is_ready():
            logger.error("Attempted to retrieve but vectorstore is not ready.")
            return []

        try:
            results = self.vectorstore.similarity_search_with_score(query, k=k)
            output = []
            seen_pmids = set()
            for doc, score in results:
                meta = getattr(doc, "metadata", {}) or {}
                pmid = str(meta.get("pmid", "")).strip()
                if not pmid or pmid.lower() in {"nan", "none", ""}:
                    continue
                if pmid in seen_pmids:
                    continue
                seen_pmids.add(pmid)

                page_content = getattr(doc, "page_content", "")
                snippet = page_content[:300] + "..." if len(page_content) > 300 else page_content

                output.append(
                    {
                        "pmid": pmid,
                        "title": meta.get("title", "No title"),
                        "snippet": snippet,
                        "score": float(score),
                        "source": meta.get("source", "pubmed"),
                    }
                )
            return output
        except Exception as e:
            logger.exception("Error during retrieval: %s", e)
            return []