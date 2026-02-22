"""Tests for FAISS search integration — Decision #11A."""

import pytest
from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings

from tools import _passes_filter


# ── Fixtures ─────────────────────────────────────────────────────────────────


SAMPLE_PRODUCTS = [
    {
        "metadata": {
            "id": "1001", "title": "ركنة مودرن رمادي", "clean_title": "ركنة مودرن رمادي",
            "price": 15000, "compare_at_price": 18000, "discount_pct": 17,
            "product_type": "ركنة", "vendor": "Chic Homz",
            "cover": "", "url": "https://chichomz.com/products/modern-sofa",
            "tags": ["مودرن", "رمادي"],
        },
        "text": "ركنة مودرن رمادي خشب زان",
    },
    {
        "metadata": {
            "id": "1002", "title": "سرير خشب كلاسيك", "clean_title": "سرير خشب كلاسيك",
            "price": 8500, "compare_at_price": 0, "discount_pct": 0,
            "product_type": "سرير", "vendor": "Royal",
            "cover": "", "url": "https://chichomz.com/products/classic-bed",
            "tags": ["كلاسيك"],
        },
        "text": "سرير خشب كلاسيك 180×200",
    },
    {
        "metadata": {
            "id": "1003", "title": "ترابيزة رخام", "clean_title": "ترابيزة رخام",
            "price": 4200, "compare_at_price": 5000, "discount_pct": 16,
            "product_type": "ترابيزة", "vendor": "Lux",
            "cover": "", "url": "https://chichomz.com/products/marble-table",
            "tags": ["رخام"],
        },
        "text": "طقم ترابيزات رخام 3 قطع",
    },
    {
        "metadata": {
            "id": "1004", "title": "دولاب غرفة نوم", "clean_title": "دولاب غرفة نوم",
            "price": 12000, "compare_at_price": 0, "discount_pct": 0,
            "product_type": "دولاب", "vendor": "Chic Homz",
            "cover": "", "url": "https://chichomz.com/products/bedroom-wardrobe",
            "tags": ["غرفة نوم"],
        },
        "text": "دولاب غرفة نوم 6 ضلف",
    },
    {
        "metadata": {
            "id": "1005", "title": "كنبة صغيرة", "clean_title": "كنبة صغيرة",
            "price": 3500, "compare_at_price": 0, "discount_pct": 0,
            "product_type": "كنبة", "vendor": "Cozy",
            "cover": "", "url": "https://chichomz.com/products/small-sofa",
            "tags": ["كنبة", "صغير"],
        },
        "text": "كنبة صغيرة 2 مقعد قماش",
    },
]


@pytest.fixture(scope="module")
def faiss_store():
    """Build a small in-memory FAISS index for testing."""
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )

    docs = []
    for item in SAMPLE_PRODUCTS:
        meta = dict(item["metadata"])
        for field in ("price", "compare_at_price", "discount_pct"):
            if field in meta:
                meta[field] = float(meta[field])
        docs.append(Document(page_content=item["text"], metadata=meta))

    return FAISS.from_documents(docs, embeddings)


# ── FAISS search tests ───────────────────────────────────────────────────────


def test_faiss_search_returns_results(faiss_store):
    results = faiss_store.similarity_search("ركنة", k=3)
    assert len(results) > 0
    assert any(
        "ركنة" in r.metadata.get("product_type", "") or "ركنة" in r.page_content
        for r in results
    )


def test_faiss_search_has_metadata_fields(faiss_store):
    results = faiss_store.similarity_search("سرير", k=1)
    assert len(results) > 0
    meta = results[0].metadata
    for field in ("id", "title", "price", "product_type"):
        assert field in meta


# ── Post-filter tests ────────────────────────────────────────────────────────


def test_post_filter_price_max():
    assert _passes_filter({"price": 3500}, {"price_max": 5000}) is True
    assert _passes_filter({"price": 3500}, {"price_max": 3000}) is False


def test_post_filter_price_min():
    assert _passes_filter({"price": 3500}, {"price_min": 3000}) is True
    assert _passes_filter({"price": 3500}, {"price_min": 4000}) is False


def test_post_filter_product_type():
    assert _passes_filter({"product_type": "ركنة"}, {"product_type": "ركنة"}) is True
    assert _passes_filter({"product_type": "سرير"}, {"product_type": "ركنة"}) is False


def test_post_filter_discount():
    assert _passes_filter({"discount_pct": 17}, {"has_discount": True}) is True
    assert _passes_filter({"discount_pct": 0}, {"has_discount": True}) is False


def test_post_filter_empty_filters():
    assert _passes_filter({"price": 5000}, {}) is True
