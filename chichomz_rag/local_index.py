"""
Local FAISS index builder/loader from chichomz_rag_ready.json.

On first run  → builds FAISS index and saves to disk (faiss_index/).
On later runs → loads from disk (fast).
"""

import json
import os
import pathlib

from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings

_ROOT      = pathlib.Path(__file__).parent.parent
_DATA_FILE = _ROOT / "chichomz_rag_ready.json"
_INDEX_DIR = _ROOT / "faiss_index"

EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def _make_embeddings() -> HuggingFaceEmbeddings:
    return HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)


def _load_documents() -> list[Document]:
    print(f"📂 Loading {_DATA_FILE} …")
    with open(_DATA_FILE, encoding="utf-8") as f:
        data = json.load(f)

    docs = []
    for item in data:
        meta = item.get("metadata", {})
        # Pinecone-style: tags & skus → lists of str
        for field in ("tags", "skus"):
            val = meta.get(field, [])
            if isinstance(val, list):
                meta[field] = [str(v) for v in val]
        # price fields → float
        for field in ("price", "compare_at_price", "discount_pct"):
            if field in meta:
                try:
                    meta[field] = float(meta[field])
                except (ValueError, TypeError):
                    meta[field] = 0.0
        docs.append(Document(page_content=item.get("text", ""), metadata=meta))

    print(f"✅ {len(docs)} documents loaded.")
    return docs


def get_faiss_store(embeddings: HuggingFaceEmbeddings | None = None) -> FAISS:
    """Return a FAISS vectorstore — load from disk or build fresh."""
    if embeddings is None:
        embeddings = _make_embeddings()

    if _INDEX_DIR.exists() and any(_INDEX_DIR.iterdir()):
        print(f"⚡ Loading FAISS index from {_INDEX_DIR} …")
        store = FAISS.load_local(
            str(_INDEX_DIR),
            embeddings,
            allow_dangerous_deserialization=True,
        )
        print("✅ FAISS index loaded.")
        return store

    # Build from scratch
    docs = _load_documents()
    print("🔄 Building FAISS index (first run) …")
    store = FAISS.from_documents(documents=docs, embedding=embeddings)
    _INDEX_DIR.mkdir(parents=True, exist_ok=True)
    store.save_local(str(_INDEX_DIR))
    print(f"💾 FAISS index saved to {_INDEX_DIR}")
    return store
