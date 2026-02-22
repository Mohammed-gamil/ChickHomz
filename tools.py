"""
Search tools for the Chic Homz sales agent.

Integrates:
  - Product type classification (product_search.py) for metadata pre-filtering
  - Pinecone vector search with product_type metadata filter
  - FAISS fallback with post-filtering
  - Relevance filter: cosine similarity < 0.75 threshold

Embeddings: HuggingFace paraphrase-multilingual-MiniLM-L12-v2 (384-dim, free)
"""

import os
from typing import Optional

from langchain_core.tools import tool
from langchain_huggingface import HuggingFaceEmbeddings

from product_search import get_catalog, classify_query_to_types

EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
INDEX_NAME = "chichomz-store-index"
TOP_K_RETRIEVE = 30
SIMILARITY_THRESHOLD = 0.75  # Discard docs below this cosine similarity

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
        pt_filter = filters["product_type"]
        meta_pt = meta.get("product_type", "")
        if isinstance(pt_filter, list):
            if meta_pt not in pt_filter:
                return False
        elif meta_pt != pt_filter:
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
        pt = filters["product_type"]
        if isinstance(pt, list) and len(pt) > 0:
            pfilter["product_type"] = {"$in": pt}
        elif isinstance(pt, str):
            pfilter["product_type"] = {"$eq": pt}

    return pfilter


def _doc_to_product(doc, score: float = None) -> dict:
    """Convert a LangChain Document to a flat product dict."""
    meta = doc.metadata
    url = meta.get("url", "")
    handle = ""
    if "/products/" in url:
        handle = url.split("/products/")[-1].rstrip("/")

    product = {
        "id": str(meta.get("id", "")),
        "title": meta.get("clean_title") or meta.get("title", ""),
        "clean_title": meta.get("clean_title") or meta.get("title", ""),
        "price": float(meta.get("price", 0) or 0),
        "compare_price": float(meta.get("compare_at_price", 0) or 0),
        "compare_at_price": float(meta.get("compare_at_price", 0) or 0),
        "discount_pct": int(float(meta.get("discount_pct", 0) or 0)),
        "product_type": meta.get("product_type", ""),
        "cover": meta.get("cover", ""),
        "url": url,
        "handle": handle,
        "tags": meta.get("tags", []),
        "text": doc.page_content[:1500],
        "vendor": meta.get("vendor", ""),
        "dimensions": meta.get("dimensions", ""),
    }
    if score is not None:
        product["similarity_score"] = round(score, 4)
    return product


# ── Tools ─────────────────────────────────────────────────────────────────────


@tool
def search_products(
    query: str,
    filters: Optional[dict] = None,
    top_k: int = TOP_K_RETRIEVE,
) -> list[dict]:
    """
    Vector similarity search against the Chic Homz product catalog (11,939 products).

    Automatically applies product_type metadata pre-filter when the query
    contains a recognizable product category. Discards results below
    similarity threshold 0.75.

    Args:
        query: The search query (Arabic or English)
        filters: Optional metadata filters e.g. {"product_type": ["مرايا", "طقم مرايا"], "price_max": 3000}
        top_k: Number of results to return

    Returns:
        List of product dicts with id, title, price, discount_pct, url, cover, text, tags
    """
    if not query or not query.strip():
        return []

    store, backend = _get_vectorstore()

    # Auto-detect product_type from query if not explicitly filtered
    active_filters = dict(filters) if filters else {}
    if "product_type" not in active_filters:
        _, type_index = get_catalog()
        if type_index:
            detected_types = classify_query_to_types(query, type_index)
            if detected_types:
                active_filters["product_type"] = detected_types

    try:
        if backend == "pinecone":
            pfilter = _build_pinecone_filter(active_filters)
            # Use similarity_search_with_score for relevance filtering
            results_with_scores = store.similarity_search_with_score(
                query,
                k=top_k,
                filter=pfilter if pfilter else None,
            )
            # Filter by similarity threshold
            # Pinecone returns (doc, score) where score is cosine similarity (higher = better)
            filtered = []
            for doc, score in results_with_scores:
                # Pinecone scores: higher = more similar (0 to 1)
                if score >= SIMILARITY_THRESHOLD:
                    filtered.append((doc, score))

            if len(filtered) < 2:
                # If fewer than 2 relevant docs, include all but mark as low-confidence
                filtered = results_with_scores[:top_k]

            return [_doc_to_product(doc, score) for doc, score in filtered]
        else:
            # FAISS: over-fetch then post-filter
            active = {k: v for k, v in active_filters.items() if v is not None}
            fetch_k = top_k * 5 if active else top_k
            candidates = store.similarity_search(query, k=fetch_k)

            if active:
                results = [
                    d for d in candidates if _passes_filter(d.metadata, active)
                ][:top_k]
                if not results:
                    results = candidates[:top_k]
            else:
                results = candidates[:top_k]

            return [_doc_to_product(d) for d in results]
    except Exception as e:
        print(f"⚠️ Search error: {e}")
        return []


@tool
def search_products_with_metadata_filter(
    semantic_query: str,
    product_types: list[str],
    price_max: Optional[float] = None,
    price_min: Optional[float] = None,
    has_discount: Optional[bool] = None,
    top_k: int = 10,
) -> list[dict]:
    """
    Metadata-filtered vector search. Use this when the query enrichment
    step has identified specific product_types and built a semantic query.

    Args:
        semantic_query: Enriched Arabic search query for vector similarity
        product_types: List of product_type values to pre-filter (e.g. ["مرايا", "طقم مرايا"])
        price_max: Maximum price filter
        price_min: Minimum price filter
        has_discount: Only return discounted products
        top_k: Number of results to return

    Returns:
        List of product dicts sorted by similarity
    """
    filters = {}
    if product_types:
        filters["product_type"] = product_types
    if price_max is not None:
        filters["price_max"] = price_max
    if price_min is not None:
        filters["price_min"] = price_min
    if has_discount is not None:
        filters["has_discount"] = has_discount

    return search_products.invoke({
        "query": semantic_query,
        "filters": filters,
        "top_k": top_k,
    })


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
