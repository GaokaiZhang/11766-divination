"""
RAG retrieval precision evaluation — runs fully offline, no API key needed.

For each Tarot card, Bazi element, and I Ching hexagram, we query the index
with the symbol name and check whether the correct document appears in the
top-k results. This produces precision@k metrics that demonstrate the
retrieval surface is correctly aligned.

Usage:
    python -m backend.evaluation.retrieval_eval
"""
import json
import sys
from pathlib import Path

# Allow running as script
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def evaluate_tarot_retrieval(col, k: int = 3) -> dict:
    """For each Tarot card, query by name and check if correct doc is in top-k."""
    data_path = Path(__file__).parent.parent.parent / "data" / "tarot" / "cards.json"
    cards = json.load(open(data_path))["cards"]

    hits, total = 0, 0
    misses = []

    for card in cards:
        for orientation in ("upright", "reversed"):
            query = f"{card['name']} {orientation}"
            results = col.query(
                query_texts=[query],
                n_results=k,
                where={"system": "tarot"},
            )
            retrieved_ids = set(results["ids"][0])
            expected_id = f"tarot|{card['id']}|{orientation}"

            total += 1
            if expected_id in retrieved_ids:
                hits += 1
            else:
                misses.append((card["name"], orientation, list(retrieved_ids)[:2]))

    return {
        "system": "tarot",
        "total_queries": total,
        "hits": hits,
        f"precision@{k}": round(hits / total, 4) if total else 0,
        "sample_misses": misses[:5],
    }


def evaluate_bazi_retrieval(col, k: int = 3) -> dict:
    """For each Bazi stem/branch, query by name and check if correct doc is in top-k."""
    data_dir = Path(__file__).parent.parent.parent / "data" / "bazi"
    hits, total = 0, 0
    misses = []

    for fname in ("stems.json", "branches.json"):
        data = json.load(open(data_dir / fname))
        for entry in data["entries"]:
            # Query using the element name from the entry metadata
            meta = entry.get("meta", {})
            query_parts = [meta.get("name", ""), meta.get("element", ""),
                           meta.get("animal", "")]
            query = " ".join(p for p in query_parts if p)
            if not query:
                continue

            results = col.query(
                query_texts=[query],
                n_results=k,
                where={"system": "bazi"},
            )
            retrieved_ids = set(results["ids"][0])
            expected_id = f"bazi|{fname.removesuffix('.json')}|{entry['id']}"

            total += 1
            if expected_id in retrieved_ids:
                hits += 1
            else:
                misses.append((query, expected_id, list(retrieved_ids)[:2]))

    return {
        "system": "bazi",
        "total_queries": total,
        "hits": hits,
        f"precision@{k}": round(hits / total, 4) if total else 0,
        "sample_misses": misses[:5],
    }


def evaluate_iching_retrieval(col, k: int = 3) -> dict:
    """For each hexagram, query by name and check if judgment doc is in top-k."""
    data_path = Path(__file__).parent.parent.parent / "data" / "iching" / "hexagrams.json"
    hexagrams = json.load(open(data_path))["hexagrams"]

    hits, total = 0, 0
    misses = []

    for h in hexagrams:
        # Include hexagram number — matches the indexed document format
        # ("Hexagram {num} {name}") and avoids ambiguity from short
        # poetic English names like "Responding" or "Needing".
        query = f"Hexagram {h['number']} {h['chinese']} {h['pinyin']} {h['english']}"
        results = col.query(
            query_texts=[query],
            n_results=k,
            where={"system": "iching"},
        )
        retrieved_ids = set(results["ids"][0])
        # Check if any of the hexagram's docs appear
        expected_ids = {
            f"iching|overview|{h['number']}",
            f"iching|judgment|{h['number']}",
            f"iching|symbolic|{h['number']}",
            f"iching|image|{h['number']}",
        }

        total += 1
        if expected_ids & retrieved_ids:
            hits += 1
        else:
            misses.append((h["english"], list(expected_ids)[:1], list(retrieved_ids)[:2]))

    return {
        "system": "iching",
        "total_queries": total,
        "hits": hits,
        f"precision@{k}": round(hits / total, 4) if total else 0,
        "sample_misses": misses[:5],
    }


def evaluate_iching_retrieval_filtered(col, k: int = 3) -> dict:
    """Production-mode eval: uses metadata filtering by hexagram number.

    This mirrors the actual production pipeline, where the retriever knows
    which hexagram was cast and filters by hexagram number in ChromaDB's
    where clause.
    """
    data_path = Path(__file__).parent.parent.parent / "data" / "iching" / "hexagrams.json"
    hexagrams = json.load(open(data_path))["hexagrams"]

    hits, total = 0, 0
    misses = []

    for h in hexagrams:
        query = f"Hexagram {h['number']} {h['english']} judgment image"
        results = col.query(
            query_texts=[query],
            n_results=k,
            where={"$and": [{"system": "iching"}, {"hexagram": h["number"]}]},
        )
        retrieved_ids = set(results["ids"][0])
        expected_ids = {
            f"iching|overview|{h['number']}",
            f"iching|judgment|{h['number']}",
            f"iching|symbolic|{h['number']}",
            f"iching|image|{h['number']}",
        }

        total += 1
        if expected_ids & retrieved_ids:
            hits += 1
        else:
            misses.append((h["english"], list(expected_ids)[:1], list(retrieved_ids)[:2]))

    return {
        "system": "iching_filtered",
        "total_queries": total,
        "hits": hits,
        f"precision@{k}": round(hits / total, 4) if total else 0,
        "sample_misses": misses[:5],
    }


def main():
    from backend.rag.indexer import build_index, get_collection

    print("Building RAG index...")
    build_index(verbose=True)
    col = get_collection()

    print(f"\nIndex contains {col.count()} documents")

    k = 3
    print(f"\n{'='*60}")
    print(f"RAG Retrieval Evaluation (precision@{k})")
    print(f"{'='*60}")

    results = []
    for name, func in [
        ("Tarot", evaluate_tarot_retrieval),
        ("Bazi", evaluate_bazi_retrieval),
        ("I Ching (embedding only)", evaluate_iching_retrieval),
        ("I Ching (with metadata filter)", evaluate_iching_retrieval_filtered),
    ]:
        print(f"\nEvaluating {name}...")
        r = func(col, k=k)
        results.append(r)
        precision_key = f"precision@{k}"
        print(f"  Queries: {r['total_queries']}")
        print(f"  Hits:    {r['hits']}")
        print(f"  {precision_key}: {r[precision_key]:.1%}")
        if r.get("sample_misses"):
            print(f"  Sample misses:")
            for miss in r["sample_misses"][:3]:
                print(f"    - {miss[0]}")

    # Overall (using filtered I Ching for production accuracy)
    prod_results = [r for r in results if r["system"] != "iching"]
    total_q = sum(r["total_queries"] for r in prod_results)
    total_h = sum(r["hits"] for r in prod_results)
    print(f"\n{'='*60}")
    print(f"Production precision@{k}: {total_h}/{total_q} = {total_h/total_q:.1%}")
    print(f"{'='*60}")

    # Save results
    out_path = Path(__file__).parent.parent.parent / "retrieval_eval_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
