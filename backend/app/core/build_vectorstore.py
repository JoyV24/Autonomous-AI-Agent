import pandas as pd
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.vectorstores import Chroma
from langchain.docstore.document import Document
from pathlib import Path
import os

# Paths
csv_path = Path("pubmed_results.csv")
vector_dir = Path("vector_store")
vector_dir.mkdir(exist_ok=True)

# 1. Load your data
df = pd.read_csv(csv_path)
print(f"Loaded {len(df)} documents.")

# 2. Create LangChain Document objects
docs = [
    Document(
        page_content=f"{row['Title']} {row['Abstract']}",
        metadata={"pmid": row.get("PMID", ""), "title": row.get("Title", "")}
    )
    for _, row in df.iterrows()
]

# 3. Create embeddings (can use sentence-transformers)
model_name = "sentence-transformers/all-MiniLM-L6-v2"
embedder = HuggingFaceEmbeddings(model_name=model_name)

# 4. Build Chroma vector store
vectorstore = Chroma.from_documents(docs, embedder, persist_directory=str(vector_dir))
vectorstore.persist()

print("✅ Vector store built and saved to:", vector_dir)