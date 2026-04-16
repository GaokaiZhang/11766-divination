"""
RAG component ablation — measures the marginal contribution of the two
non-trivial pieces of the retrieval pipeline:

  * query expansion  (retriever._expand_query)
  * metadata filters (ChromaDB `where` clauses, I Ching hexagram number)

For each divination system we generate N synthetic readings with a seeded
RNG, extract the canonical symbol list the reading would feed to RAG, then
run four retrieval variants and score each against the gold document IDs
derived from the reading.

Variants
    full                : retrieve_expanded — current production pipeline
    no_expansion        : single primary query with system filter
    no_metadata_filter  : retrieve_expanded, with hexagram filters stripped
    no_system_filter    : single primary query, no filter at all (floor)

Metric
    recall@k over the set of gold documents for each reading, averaged
    across readings. Recall is the right metric here because each reading
    has a *set* of expected docs (3 tarot cards x orientation; 6 I-Ching
    docs for primary+transformed hexagrams). Precision@k isn't well-defined
    when |gold| differs from k.

Usage
    python -m backend.evaluation.rag_ablation
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.divination import SYSTEMS, UserBirthInfo
from backend.rag import retriever as rr
from backend.rag.indexer import build_index, get_collection


# ---------------------------------------------------------------------------
# Sample readings + gold label extraction
# ---------------------------------------------------------------------------

def _gen_tarot_cases(n: int, seed: int = 0) -> list[dict]:
    rng = random.Random(seed)
    cases = []
    for _ in range(n):
        # Seed the system RNG so compute() picks deterministic cards.
        random.seed(rng.random())
        result = SYSTEMS["tarot"].compute(UserBirthInfo(name="Eval"))
        gold = set()
        for card in result.raw["cards"]:
            orient = "reversed" if card["is_reversed"] else "upright"
            gold.add(f"tarot|{card['id']}|{orient}")
        cases.append({"symbols": result.symbols, "gold": gold})
    return cases


def _gen_iching_cases(n: int, seed: int = 0) -> list[dict]:
    rng = random.Random(seed)
    cases = []
    for _ in range(n):
        random.seed(rng.random())
        result = SYSTEMS["iching"].compute(UserBirthInfo(name="Eval"))
        prim_obj = result.raw.get("primary") or {}
        trans_obj = result.raw.get("transformed") or {}
        prim = prim_obj.get("number")
        trans = trans_obj.get("number")
        nums = {n for n in (prim, trans) if n is not None}
        gold = set()
        for num in nums:
            for t in ("overview", "judgment", "image"):
                gold.add(f"iching|{t}|{num}")
        cases.append({
            "symbols": result.symbols,
            "gold": gold,
            "primary": prim,
            "transformed": trans,
        })
    return cases


# ---------------------------------------------------------------------------
# Retrieval variants
# ---------------------------------------------------------------------------

def _primary_query(symbols: list[str]) -> str:
    return " ".join(symbols[:12])


def _run_full(case: dict, system: str, k: int) -> list[str]:
    chunks = rr.retrieve_expanded(case["symbols"], system=system, n_results=k)
    return [c["id"] for c in chunks]


def _run_no_expansion(case: dict, system: str, k: int) -> list[str]:
    chunks = rr.retrieve(
        _primary_query(case["symbols"]), n_results=k, system=system
    )
    return [c["id"] for c in chunks]


def _run_no_metadata_filter(case: dict, system: str, k: int) -> list[str]:
    """retrieve_expanded, but strip hexagram filters (I Ching) so only the
    system-level filter survives. For tarot/bazi this is identical to full."""
    original_expand = rr._expand_query

    def patched(symbols, sys_name):
        queries = original_expand(symbols, sys_name)
        stripped = []
        for qtext, qwhere in queries:
            if isinstance(qwhere, dict):
                # Collapse any {$and: [{system: ...}, {hexagram: ...}]} back to
                # a system-only filter handled by retrieve()'s default path.
                qwhere = None
            stripped.append((qtext, qwhere))
        return stripped

    rr._expand_query = patched
    try:
        chunks = rr.retrieve_expanded(case["symbols"], system=system, n_results=k)
    finally:
        rr._expand_query = original_expand
    return [c["id"] for c in chunks]


def _run_no_system_filter(case: dict, system: str, k: int) -> list[str]:
    chunks = rr.retrieve(
        _primary_query(case["symbols"]), n_results=k, system=None, where=None
    )
    return [c["id"] for c in chunks]


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _recall(retrieved: list[str], gold: set[str]) -> float:
    if not gold:
        return 0.0
    return len(set(retrieved) & gold) / len(gold)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

VARIANTS: dict[str, Callable] = {
    "full":                _run_full,
    "no_expansion":        _run_no_expansion,
    "no_metadata_filter":  _run_no_metadata_filter,
    "no_system_filter":    _run_no_system_filter,
}


def run_ablation(
    system: str, cases: list[dict], k: int
) -> dict[str, float]:
    recalls: dict[str, list[float]] = {name: [] for name in VARIANTS}
    for case in cases:
        for name, fn in VARIANTS.items():
            ids = fn(case, system, k)
            recalls[name].append(_recall(ids, case["gold"]))
    return {n: round(sum(rs) / len(rs), 4) for n, rs in recalls.items()}


def main():
    print("Building RAG index...")
    build_index(verbose=False)
    col = get_collection()
    print(f"Index contains {col.count()} documents\n")

    n_cases = 30
    k_values = [3, 5, 8]

    all_results: dict = {}

    for system, gen in [("tarot", _gen_tarot_cases), ("iching", _gen_iching_cases)]:
        print(f"=== {system.upper()} ablation (n={n_cases}) ===")
        cases = gen(n_cases, seed=42)
        sys_results: dict = {}
        for k in k_values:
            scores = run_ablation(system, cases, k)
            sys_results[k] = scores
            print(f"  k={k}: " + "  ".join(
                f"{name}={val:.1%}" for name, val in scores.items()
            ))
        all_results[system] = sys_results
        print()

    # Deltas at k=5 (representative)
    print("=== Component contribution at k=5 (full - ablated) ===")
    for system, by_k in all_results.items():
        scores = by_k[5]
        full = scores["full"]
        print(f"  {system}:")
        for name in ("no_expansion", "no_metadata_filter", "no_system_filter"):
            delta = full - scores[name]
            print(f"    {name:20s}: {scores[name]:.1%}  (Δ vs full: {delta:+.1%})")

    out_path = Path(__file__).parent.parent.parent / "rag_ablation_results.json"
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
