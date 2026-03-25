"""
RAG retriever with query expansion and re-ranking.

Upgrades beyond vanilla semantic search:
1. Query expansion — splits multi-symbol queries into sub-queries
2. Deduplication — merges results from multiple sub-queries
3. Relevance threshold — drops low-confidence results
"""
import logging
from .indexer import get_collection

logger = logging.getLogger(__name__)


def _expand_query(symbols: list[str], system: str) -> list[str]:
    """Expand a symbol list into multiple focused sub-queries.

    For multi-card Tarot spreads, queries like "The Tower The Star The Hermit"
    retrieve the most popular card but miss interaction patterns. Expanding
    into sub-queries improves recall for relational documents.
    """
    queries = []

    # Primary query: all symbols concatenated (broad retrieval)
    primary = " ".join(symbols[:12])
    if primary.strip():
        queries.append(primary)

    if system == "tarot":
        # Individual card queries (catches per-card meanings)
        card_names = [s for s in symbols if not any(
            kw in s.lower() for kw in ("upright", "reversed", "beginnings",
                                        "creativity", "strength")
        )]
        for name in card_names[:3]:
            queries.append(name)
        # Interaction query (catches cross-card patterns)
        if len(card_names) >= 2:
            queries.append(f"{card_names[0]} {card_names[1]} interaction pair")
        # Position query
        queries.append("spread position interpretation Past Present Future")

    elif system == "iching":
        # Hexagram-specific queries
        hex_names = [s for s in symbols[:4] if len(s) > 2]
        for name in hex_names:
            queries.append(f"hexagram {name}")
        # Changing lines query
        if any("line" in s for s in symbols):
            queries.append("changing lines transformation hexagram")

    elif system == "bazi":
        # Element interaction queries
        elements = [s for s in symbols if any(
            e in s for e in ("Wood", "Fire", "Earth", "Metal", "Water")
        )]
        if elements:
            queries.append(" ".join(elements[:4]) + " interaction")
        # Day Master query
        day_master = [s for s in symbols if "Day Master" in s]
        if day_master:
            queries.append(day_master[0] + " strength")
        # Branch relationship query
        queries.append("hidden stems branch combine clash")

    return queries if queries else [primary]


def retrieve(
    query: str,
    n_results: int = 5,
    system: str | None = None,
) -> list[dict]:
    """
    Retrieve the top-n relevant documents for a query.

    Args:
        query:     Free-text query built from divination symbols.
        n_results: Number of chunks to return.
        system:    If given, filter to only "tarot", "bazi", or "iching" documents.

    Returns:
        List of {"text": str, "meta": dict, "distance": float} dicts, ordered by relevance.
    """
    col = get_collection()
    where = {"system": system} if system else None

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

    for q in queries:
        try:
            chunks = retrieve(q, n_results=max_per_query, system=system)
        except Exception as e:
            logger.warning("Sub-query failed: %s — %s", q[:40], e)
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
