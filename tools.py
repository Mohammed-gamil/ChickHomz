"""
Search tools for the Chic Homz sales agent.

Auto-detects backend:
  - PINECONE_API_KEY set → Pinecone (server-side filtering)
  - otherwise            → local FAISS from chichomz_rag_ready.json (post-filtering)

Embeddings: HuggingFace paraphrase-multilingual-MiniLM-L12-v2 (384-dim, free)
"""

import os
from typing import Optional

from langchain_core.tools import tool
from langchain_huggingface import HuggingFaceEmbeddings

EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
INDEX_NAME = "chichomz-store-index"
TOP_K_RETRIEVE = 30

# ── Singletons (avoid re-creating on every call) ─────────────────────────────

_embeddings = None
_vectorstore = None
_backend = None


def _get_embeddings() -> HuggingFaceEmbeddings:
    global _embeddings
    if _embeddings is None:
        _embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    return _embeddings


def _get_vectorstore():
    """Return (vectorstore, backend_name). Lazy-initialized singleton."""
    global _vectorstore, _backend
    if _vectorstore is not None:
        return _vectorstore, _backend

    emb = _get_embeddings()

    if os.getenv("PINECONE_API_KEY"):
        from langchain_pinecone import PineconeVectorStore

        _vectorstore = PineconeVectorStore(index_name=INDEX_NAME, embedding=emb)
        _backend = "pinecone"
        print("✅ Search backend: Pinecone")
    else:
        from chichomz_rag.local_index import get_faiss_store

        _vectorstore = get_faiss_store(emb)
        _backend = "faiss"
        print("✅ Search backend: local FAISS")

    return _vectorstore, _backend


# ── Filtering helpers ─────────────────────────────────────────────────────────


def _passes_filter(meta: dict, filters: dict) -> bool:
    """Post-filter check for FAISS backend (no native metadata filtering)."""
    if filters.get("product_type"):
        if meta.get("product_type") != filters["product_type"]:
            return False
    if filters.get("price_max") is not None:
        if float(meta.get("price", 0) or 0) > filters["price_max"]:
            return False
    if filters.get("price_min") is not None:
        if float(meta.get("price", 0) or 0) < filters["price_min"]:
            return False
    if filters.get("has_discount") is True:
        if float(meta.get("discount_pct", 0) or 0) <= 0:
            return False
    return True


def _build_pinecone_filter(filters: dict) -> dict:
    """Build Pinecone-native filter dict from simplified filter spec."""
    pfilter = {}
    if not filters:
        return pfilter

    if "price_max" in filters or "price_min" in filters:
        price_cond = {}
        if "price_max" in filters:
            price_cond["$lte"] = filters["price_max"]
        if "price_min" in filters:
            price_cond["$gte"] = filters["price_min"]
        pfilter["price"] = price_cond

    if "product_type" in filters:
        pfilter["product_type"] = {"$eq": filters["product_type"]}

    return pfilter


def _doc_to_product(doc) -> dict:
    """Convert a LangChain Document to a flat product dict."""
    meta = doc.metadata
    url = meta.get("url", "")
    handle = ""
    if "/products/" in url:
        handle = url.split("/products/")[-1].rstrip("/")

    return {
        "id": str(meta.get("id", "")),
        "title": meta.get("clean_title") or meta.get("title", ""),
        "price": float(meta.get("price", 0) or 0),
        "compare_price": float(meta.get("compare_at_price", 0) or 0),
        "discount_pct": int(float(meta.get("discount_pct", 0) or 0)),
        "product_type": meta.get("product_type", ""),
        "cover": meta.get("cover", ""),
        "url": url,
        "handle": handle,
        "tags": meta.get("tags", []),
        "text": doc.page_content[:1000],
        "vendor": meta.get("vendor", ""),
    }


# ── Tools ─────────────────────────────────────────────────────────────────────


@tool
def search_products(
    query: str,
    filters: Optional[dict] = None,
    top_k: int = TOP_K_RETRIEVE,
) -> list[dict]:
    """
    Vector similarity search against the Chic Homz product catalog (11,939 products).

    Args:
        query: The search query (Arabic or English)
        filters: Optional metadata filters e.g. {"product_type": "مرايا", "price_max": 3000}
        top_k: Number of results to return

    Returns:
        List of product dicts with id, title, price, discount_pct, url, cover, text, tags
    """
    if not query or not query.strip():
        return []

    store, backend = _get_vectorstore()

    try:
        if backend == "pinecone":
            pfilter = _build_pinecone_filter(filters or {})
            results = store.similarity_search(
                query,
                k=top_k,
                filter=pfilter if pfilter else None,
            )
        else:
            # FAISS: over-fetch then post-filter
            active = {k: v for k, v in (filters or {}).items() if v is not None}
            fetch_k = top_k * 5 if active else top_k
            candidates = store.similarity_search(query, k=fetch_k)

            if active:
                results = [
                    d for d in candidates if _passes_filter(d.metadata, active)
                ][:top_k]
                # Fallback to unfiltered if filters are too strict
                if not results:
                    results = candidates[:top_k]
            else:
                results = candidates[:top_k]
    except Exception as e:
        print(f"⚠️ Search error: {e}")
        return []

    return [_doc_to_product(d) for d in results]


@tool
def get_product_by_id(product_id: str) -> dict:
    """Retrieve a specific product by its Shopify ID. Only works with Pinecone backend."""
    if not os.getenv("PINECONE_API_KEY"):
        return {"error": "Product lookup by ID requires Pinecone backend"}

    try:
        from pinecone import Pinecone

        pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
        index = pc.Index(INDEX_NAME)
        result = index.fetch(ids=[str(product_id)])
        if str(product_id) in result.vectors:
            return result.vectors[str(product_id)].metadata
    except Exception as e:
        print(f"⚠️ Product lookup error: {e}")

    return {}
