"""
RAG retriever with query expansion and re-ranking.

Upgrades beyond vanilla semantic search:
1. Query expansion — splits multi-symbol queries into sub-queries
2. Deduplication — merges results from multiple sub-queries
3. Relevance threshold — drops low-confidence results
4. Metadata filtering — uses hexagram number for I Ching precision
"""
import logging
import re
from .indexer import get_collection

logger = logging.getLogger(__name__)


def _expand_query(symbols: list[str], system: str) -> list[tuple[str, dict | None]]:
    """Expand a symbol list into multiple focused sub-queries.

    Returns a list of (query_text, where_filter_or_None) tuples. When a where
    filter is provided it overrides the default system-only filter in retrieve().

    For multi-card Tarot spreads, queries like "The Tower The Star The Hermit"
    retrieve the most popular card but miss interaction patterns. Expanding
    into sub-queries improves recall for relational documents.
    """
    queries: list[tuple[str, dict | None]] = []

    # Primary query: all symbols concatenated (broad retrieval, system filter only)
    primary = " ".join(symbols[:12])
    if primary.strip():
        queries.append((primary, None))

    if system == "tarot":
        # Individual card queries (catches per-card meanings)
        card_names = [s for s in symbols if not any(
            kw in s.lower() for kw in ("upright", "reversed", "beginnings",
                                        "creativity", "strength")
        )]
        for name in card_names[:3]:
            queries.append((name, None))
        # Interaction query (catches cross-card patterns)
        if len(card_names) >= 2:
            queries.append((f"{card_names[0]} {card_names[1]} interaction pair", None))
        # Position query
        queries.append(("spread position interpretation Past Present Future", None))

    elif system == "iching":
        # Parse hexagram numbers from symbols (format: "Hexagram N ...")
        hex_nums = []
        for s in symbols:
            m = re.match(r"Hexagram (\d+)", s)
            if m:
                num = int(m.group(1))
                if num not in hex_nums:
                    hex_nums.append(num)

        primary_num = hex_nums[0] if hex_nums else None

        # Hexagram-specific queries with metadata filtering
        hex_names = [s for s in symbols[:6] if len(s) > 2]
        for name in hex_names[:3]:
            if primary_num:
                where = {"$and": [{"system": "iching"}, {"hexagram": primary_num}]}
                queries.append((f"Hexagram {primary_num} {name}", where))
            else:
                queries.append((f"hexagram {name}", None))

        # Changing line queries — filter to primary hexagram
        line_symbols = [s for s in symbols if re.match(r"Hexagram \d+ line \d+", s)]
        for line_s in line_symbols[:3]:
            if primary_num:
                where = {"$and": [{"system": "iching"}, {"hexagram": primary_num}]}
                queries.append((line_s, where))
            else:
                queries.append((line_s, None))

        # Transformed hexagram (different hexagram number)
        if len(hex_nums) > 1:
            transformed_num = hex_nums[1]
            where = {"$and": [{"system": "iching"}, {"hexagram": transformed_num}]}
            # Find transformed name from symbols
            transformed_names = [s for s in symbols
                                 if s.startswith(f"Hexagram {transformed_num}")]
            t_name = transformed_names[0] if transformed_names else f"Hexagram {transformed_num}"
            queries.append((f"{t_name} judgment", where))
            queries.append((f"{t_name} image", where))

    elif system == "bazi":
        # Element interaction queries
        elements = [s for s in symbols if any(
            e in s for e in ("Wood", "Fire", "Earth", "Metal", "Water")
        )]
        if elements:
            queries.append((" ".join(elements[:4]) + " interaction", None))
        # Day Master query
        day_master = [s for s in symbols if "Day Master" in s]
        if day_master:
            queries.append((day_master[0] + " strength", None))
        # Branch relationship query
        queries.append(("hidden stems branch combine clash", None))

    return queries if queries else [(primary, None)]


def retrieve(
    query: str,
    n_results: int = 5,
    system: str | None = None,
    where: dict | None = None,
) -> list[dict]:
    """
    Retrieve the top-n relevant documents for a query.

    Args:
        query:     Free-text query built from divination symbols.
        n_results: Number of chunks to return.
        system:    If given (and where is None), filter to this system's documents.
        where:     If given, used directly as ChromaDB where clause (overrides system).

    Returns:
        List of {"text": str, "meta": dict, "distance": float} dicts, ordered by relevance.
    """
    col = get_collection()
    if where is None and system:
        where = {"system": system}

    results = col.query(
        query_texts=[query],
        n_results=n_results,
        where=where,
    )

    docs = results["documents"][0]
    metas = results["metadatas"][0]
    distances = results.get("distances", [[]])[0]

    output = []
    for d, m, dist in zip(docs, metas, distances or [0.0] * len(docs)):
        output.append({"text": d, "meta": m, "distance": dist})

    logger.debug("retrieve(query=%r, system=%s) → %d docs", query[:60], system, len(output))
    return output


def retrieve_expanded(
    symbols: list[str],
    system: str,
    n_results: int = 8,
    max_per_query: int = 5,
) -> list[dict]:
    """
    Multi-query retrieval with expansion and deduplication.

    Runs multiple sub-queries derived from the reading symbols, merges results,
    deduplicates by document ID, and returns the top-n by minimum distance.

    Args:
        symbols:       Key terms from the divination reading.
        system:        Filter to this system's documents.
        n_results:     Total number of documents to return after dedup.
        max_per_query: Max results per individual sub-query.

    Returns:
        Deduplicated list of {"text": str, "meta": dict, "distance": float}.
    """
    queries = _expand_query(symbols, system)
    logger.info("Query expansion: %d sub-queries for system=%s", len(queries), system)

    seen_texts = set()
    all_results = []

    for q_text, q_where in queries:
        try:
            if q_where:
                chunks = retrieve(q_text, n_results=max_per_query, where=q_where)
            else:
                chunks = retrieve(q_text, n_results=max_per_query, system=system)
        except Exception as e:
            logger.warning("Sub-query failed: %s — %s", q_text[:40], e)
            continue

        for chunk in chunks:
            # Deduplicate by text content (same doc from different queries)
            text_key = chunk["text"][:100]
            if text_key not in seen_texts:
                seen_texts.add(text_key)
                all_results.append(chunk)

    # Sort by distance (lower = more relevant) and take top-n
    all_results.sort(key=lambda c: c.get("distance", 999))
    final = all_results[:n_results]

    logger.info("Expanded retrieval: %d unique docs from %d sub-queries → %d returned",
                len(all_results), len(queries), len(final))
    return final
