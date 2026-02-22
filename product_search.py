"""
RAG Product Type Extractor + Metadata-Filtered Search
=====================================================
Extracts all unique product_types from chichomz_rag_ready.json
then uses them to:
  1. Build a product_type → products index
  2. Classify any user query to the right product_type(s)
  3. Pre-filter the RAG search by product_type before vector similarity
"""

import json
import os
from collections import defaultdict
from difflib import SequenceMatcher


# ─────────────────────────────────────────────────────────────
# STEP 1: LOAD DATA + EXTRACT UNIQUE PRODUCT TYPES
# ─────────────────────────────────────────────────────────────

def load_catalog(json_path: str) -> tuple[list[dict], dict[str, list[dict]]]:
    """
    Loads the JSON catalog and builds:
      - all_products: flat list of all products
      - type_index:   dict mapping product_type → list of products
    """
    with open(json_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    all_products = []
    type_index = defaultdict(list)

    for item in raw:
        metadata = item.get("metadata", {})
        product_type = metadata.get("product_type", "").strip()

        if not product_type:
            product_type = "__UNCATEGORIZED__"

        product = {
            "product_type": product_type,
            "clean_title":       metadata.get("clean_title", metadata.get("title", "")),
            "price":             metadata.get("price"),
            "compare_at_price":  metadata.get("compare_at_price"),
            "discount_pct":      metadata.get("discount_pct", 0),
            "vendor":            metadata.get("vendor", ""),
            "tags":              metadata.get("tags", []),
            "cover":             metadata.get("cover", ""),
            "url":               metadata.get("url", ""),
            "dimensions":        metadata.get("dimensions", ""),
            "text":              item.get("text", ""),
        }

        all_products.append(product)
        type_index[product_type].append(product)

    return all_products, dict(type_index)


# ─────────────────────────────────────────────────────────────
# STEP 2: PRINT UNIQUE PRODUCT TYPES SUMMARY
# ─────────────────────────────────────────────────────────────

def print_product_types_summary(type_index: dict[str, list]):
    """Prints all unique product types sorted by count descending."""
    sorted_types = sorted(type_index.items(), key=lambda x: -len(x[1]))

    print("=" * 55)
    print(f"  UNIQUE PRODUCT TYPES: {len(type_index)}")
    print("=" * 55)
    print(f"  {'COUNT':>6}   TYPE")
    print("-" * 55)
    for pt, products in sorted_types:
        print(f"  {len(products):>6}   {pt}")
    print("=" * 55)


# ─────────────────────────────────────────────────────────────
# STEP 3: QUERY → PRODUCT TYPE CLASSIFIER
# ─────────────────────────────────────────────────────────────

QUERY_TO_TYPE_MAP = {
    # Living room furniture
    "ركنة":                  ["ركنة", "ركنة سرير"],
    "كنبة":                  ["كنبة", "كنبة سرير", "كنبة استقبال", "كنبة وكرسي"],
    "انتريه":                ["انتريه", "أنتريه", "طقم أنتريه", "طقم انتريه", "طقم انتظار"],
    "كرسي":                  ["كرسي", "كرسي سفرة", "كرسي بار", "كرسي مكتب",
                              "كرسي ليزي بوي", "كرسي هزاز", "كرسى", "كرسي طفل"],
    "فوتيه":                 ["فوتيه"],
    "بوف":                   ["بوف", "كرسي وبوف", "كرسيين و بوف"],
    "شيزلونج":               ["شيزلونج"],
    "بين باج":               ["بين باج"],

    # Tables
    "ترابيزة قهوة":          ["ترابيزة قهوة", "كوفي كورنر", "طقم ترابيزات قهوة"],
    "ترابيزة تليفزيون":      ["ترابيزة تليفزيون", "ترابيزة تليفزيون مع ترابيزة قهوة",
                              "وحدة تليفزيون", "ترابيزة تليفزيون مع وحدة معلقة"],
    "ترابيزة جانبية":        ["ترابيزة جانبية", "طقم ترابيزات جانبية"],
    "ترابيزة":               ["ترابيزة", "طقم ترابيزات"],
    "مكتب":                  ["مكتب", "مكتب مدير", "مكتب استقبال", "مكتب أطفال"],

    # Dining
    "سفرة":                  ["سفرة", "سفرة كبيرة", "ترابيزة سفرة", "غرفة سفرة",
                              "ترابيزة مع كرسيين", "ترابيزة وكرسيين"],
    # Dining with chairs (only if user explicitly mentions كرسي سفرة or a full set)
    "سفرة وكراسي":           ["سفرة", "سفرة كبيرة", "ترابيزة سفرة", "غرفة سفرة",
                              "كرسي سفرة", "ترابيزة مع كرسيين", "ترابيزة وكرسيين"],

    # Bedroom
    "سرير":                  ["سرير", "سرير دورين", "سرير مع كومود", "كرسي سرير",
                              "ركنة سرير", "غرفة نوم", "غرف نوم"],
    "دولاب":                 ["دولاب", "دولاب و خزانة"],
    "كومود":                 ["كومود"],
    "تسريحة":                ["تسريحة", "دريسنج"],
    "مرتبة":                 ["مرتبة", "واقى مرتبة"],
    "خدادية":                ["خدادية"],

    # Storage & Display
    "وحدة أدراج":            ["وحدة أدراج", "وحدة ادراج", "وحدة درج"],
    "وحدة عرض":              ["وحدة عرض"],
    "مكتبة":                 ["مكتبة", "أرفف حائط", "وحدة أرفف", "وحدة ارفف"],
    "بوفيه":                 ["بوفيه"],
    "وحدة تخزين":            ["وحدة تخزين", "وحدة تخزين مطبخ", "وحدة تخزين حمام"],
    "وحدة مدخل":             ["وحدة مدخل", "جزامة", "بانكيت جزامة", "شماعة", "مشاية"],
    "كونسول":                ["كونسول", "مرايا مع كونسول"],

    # Mirrors
    "مرايا":                 ["مرايا", "طقم مرايا", "برواز مرايا", "مرايا مع كونسول"],
    "مرآة":                  ["مرايا", "طقم مرايا", "برواز مرايا"],

    # Lighting
    "مصباح":                 ["مصباح سقف", "مصباح أرضي", "لمبة"],
    "نجفة":                  ["نجفة"],
    "أبليك":                 ["أبليك"],
    "اباجورة":               ["اباجورة ترابيزة", "أباجورة أرضية", "أباجورة", "اباجورة"],
    "إضاءة":                 ["إضاءة", "اضاءة"],

    # Decor
    "تابلوه":                ["تابلوه", "مجموعة تابلوهات"],
    "ديكور حائط":            ["ديكور حائط"],
    "سجادة":                 ["سجادة", "سجادة ديكور", "رانر"],
    "فازة":                  ["فازة"],
    "قطع ديكور":             ["قطع ديكور", "حامل شمع", "مبخرة", "فانوس"],
    "نباتات":                ["نباتات", "حامل نباتات"],
    "كوشن":                  ["كوشن", "وسادة"],
    "فواطة":                 ["فواطة"],

    # Outdoor
    "أثاث خارجي":            ["أثاث خارجي", "أثاث خارجي - كبير", "أثاث خارجي - وسط",
                              "أثاث خارجي - VIB", "طقم أثاث خارجي", "طقم خارجي",
                              "طقم خارجي - كبير", "طقم خارجي كبير", "مرجيحة",
                              "مرجيحة - كبيرة", "أرجوحة", "شمسية"],

    # Kitchen
    "مطبخ":                  ["مطبخ", "وحدة مطبخ", "وحدة تخزين مطبخ", "عربة المطبخ",
                              "تروللي تقديم", "أدوات مطبخ"],

    # Bathroom
    "حمام":                  ["وحدة حمام", "وحدة تخزين حمام", "حامل فوط"],

    # Bar
    "كرسي بار":              ["كرسي بار"],
    "بانكيت":                ["بانكيت", "بانكيت جزامة"],
}


def _extract_negations(query: str) -> list[str]:
    """
    Extracts explicitly excluded product keywords from a query.
    Handles: مش عايز كراسي / بدون كراسي / من غير كرسي / مش محتاج سرير
    Returns list of words/phrases after each negation signal.
    """
    # Sorted longest-first so "مش عايز" matches before "مش"
    NEGATION_SIGNALS = sorted([
        "مش عايز", "مش عايزة", "مش محتاج", "مش محتاجة",
        "بدون", "من غير", "لا أريد", "مش",
    ], key=len, reverse=True)

    excluded = []
    for signal in NEGATION_SIGNALS:
        pos = query.find(signal)
        if pos != -1:
            after = query[pos + len(signal):].strip()
            words = after.split()
            # Capture the first 1-2 words after negation signal
            for i in range(min(2, len(words))):
                excluded.append(words[i])
            if len(words) >= 2:
                excluded.append(words[0] + " " + words[1])
    return excluded


# Type groups for negation resolution
_NEGATION_TYPE_GROUPS = {
    "كرسي":     ["كرسي", "كرسي سفرة", "كرسي بار", "كرسي مكتب",
                  "كرسي ليزي بوي", "كرسي هزاز", "كرسى", "كرسي طفل",
                  "ترابيزة مع كرسيين", "ترابيزة وكرسيين"],
    "كراسي":    ["كرسي", "كرسي سفرة", "كرسي بار", "كرسي مكتب",
                  "كرسي ليزي بوي", "كرسي هزاز", "كرسى", "كرسي طفل",
                  "ترابيزة مع كرسيين", "ترابيزة وكرسيين"],
    "كرسيين":   ["كرسي", "كرسي سفرة", "ترابيزة مع كرسيين", "ترابيزة وكرسيين"],
    "ركنة":     ["ركنة", "ركنة سرير"],
    "كنبة":     ["كنبة", "كنبة سرير", "كنبة استقبال", "كنبة وكرسي"],
    "سرير":     ["سرير", "سرير دورين", "سرير مع كومود"],
    "مصباح":    ["مصباح سقف", "مصباح أرضي", "لمبة"],
}


def classify_query_to_types(user_query: str, type_index: dict) -> list[str]:
    """
    Maps a user query to a list of product_type values to pre-filter RAG search.

    Strategy:
      1. Direct keyword match from QUERY_TO_TYPE_MAP
      2. Fuzzy match against known product types if no direct match
      3. Falls back to empty list (caller does broad search)
    """
    matched_types = []
    query_lower = user_query.lower()

    # 0. Detect explicit negations — things the user does NOT want
    excluded_types: set[str] = set()
    for negated_word in _extract_negations(user_query):
        negated_lower = negated_word.strip().lower()
        for kw, types in _NEGATION_TYPE_GROUPS.items():
            if kw in negated_lower or negated_lower in kw:
                excluded_types.update(types)

    # 1. Direct keyword match
    for keyword, types in QUERY_TO_TYPE_MAP.items():
        if keyword in query_lower:
            for t in types:
                if t in type_index and t not in matched_types and t not in excluded_types:
                    matched_types.append(t)

    if matched_types:
        return matched_types

    # 2. Fuzzy match against actual type names in index
    all_types = list(type_index.keys())
    for pt in all_types:
        if pt in excluded_types:
            continue
        ratio = SequenceMatcher(None, query_lower, pt).ratio()
        if ratio > 0.6:
            matched_types.append(pt)

    if matched_types:
        return matched_types

    # 3. No match — return empty list (caller should do broad search)
    return []


# ─────────────────────────────────────────────────────────────
# STEP 4: METADATA-FILTERED PRODUCT SEARCH
# ─────────────────────────────────────────────────────────────

def search_by_product_types(
    type_index: dict[str, list[dict]],
    product_types: list[str],
    max_results: int = 10,
    min_discount: int = 0,
    max_price: float = None,
    sort_by: str = "discount",   # "discount" | "price_asc" | "price_desc"
) -> list[dict]:
    """
    Returns filtered + sorted products from the given product_types.
    """
    pool = []
    for pt in product_types:
        pool.extend(type_index.get(pt, []))

    if min_discount > 0:
        pool = [p for p in pool if (p.get("discount_pct") or 0) >= min_discount]

    if max_price is not None:
        pool = [p for p in pool if p.get("price") is not None and p["price"] <= max_price]

    if sort_by == "discount":
        pool.sort(key=lambda p: -(p.get("discount_pct") or 0))
    elif sort_by == "price_asc":
        pool.sort(key=lambda p: p.get("price") or float("inf"))
    elif sort_by == "price_desc":
        pool.sort(key=lambda p: -(p.get("price") or 0))

    return pool[:max_results]


# ─────────────────────────────────────────────────────────────
# STEP 5: FULL PIPELINE FUNCTION (use in LangGraph retriever node)
# ─────────────────────────────────────────────────────────────

def rag_pre_filter(
    user_query: str,
    type_index: dict[str, list[dict]],
    max_results: int = 10,
    **search_kwargs,
) -> dict:
    """
    Main function to call from the LangGraph retriever node.

    1. Classifies the query → product_type(s)
    2. Filters the catalog to only those types
    3. Returns filtered candidates ready for vector reranking

    Returns dict with:
      - matched_types:  which product types were detected
      - candidates:     list of filtered products
      - fallback:       True if no type matched
    """
    matched_types = classify_query_to_types(user_query, type_index)
    fallback = False

    if not matched_types:
        top_types = sorted(type_index, key=lambda t: -len(type_index[t]))[:5]
        matched_types = top_types
        fallback = True

    candidates = search_by_product_types(
        type_index=type_index,
        product_types=matched_types,
        max_results=max_results,
        **search_kwargs,
    )

    return {
        "matched_types": matched_types,
        "candidates":    candidates,
        "fallback":      fallback,
    }


# ─────────────────────────────────────────────────────────────
# SINGLETON CATALOG LOADER
# ─────────────────────────────────────────────────────────────

_catalog_cache: tuple[list[dict], dict[str, list[dict]]] | None = None

def get_catalog() -> tuple[list[dict], dict[str, list[dict]]]:
    """Returns (all_products, type_index). Loads once, caches."""
    global _catalog_cache
    if _catalog_cache is None:
        json_path = os.path.join(os.path.dirname(__file__), "chichomz_rag_ready.json")
        if not os.path.exists(json_path):
            return [], {}
        _catalog_cache = load_catalog(json_path)
    return _catalog_cache


# ─────────────────────────────────────────────────────────────
# DEMO / TEST
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    JSON_PATH = "chichomz_rag_ready.json"

    if not os.path.exists(JSON_PATH):
        print(f"[ERROR] File not found: {JSON_PATH}")
        exit(1)

    print("\nLoading catalog...")
    all_products, type_index = load_catalog(JSON_PATH)
    print(f"Loaded {len(all_products)} products.\n")

    print_product_types_summary(type_index)

    test_queries = [
        "عايز سفرة مدورة رخام لفردين",
        "كنبة ركنة للصالة",
        "مرايا حلوة للمدخل",
        "ترابيزة تليفزيون باللون الأسود",
        "سرير لغرفة الأطفال",
    ]

    print("\n" + "=" * 55)
    print("  TEST QUERIES")
    print("=" * 55)

    for query in test_queries:
        result = rag_pre_filter(query, type_index, max_results=3)
        print(f"\nQuery: {query}")
        print(f"  Matched types : {result['matched_types']}")
        print(f"  Fallback used : {result['fallback']}")
        print(f"  Top candidates ({len(result['candidates'])}):")
        for p in result["candidates"]:
            disc = f"  (-{p['discount_pct']}%)" if p.get("discount_pct") else ""
            print(f"    • {p['clean_title']}  |  {p['price']} ج.م{disc}")
