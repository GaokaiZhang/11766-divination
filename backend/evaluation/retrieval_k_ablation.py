"""
Retrieval precision ablation: vary k (number of retrieved documents) and
measure precision@k across all three divination systems.

This answers: "How does retrieval quality change as we retrieve more or fewer
documents?" It characterizes the precision-recall tradeoff of the RAG pipeline.

Runs fully offline — no API key needed, only the local ChromaDB index.

Usage:
    python -m backend.evaluation.retrieval_k_ablation
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.evaluation.retrieval_eval import (
    evaluate_tarot_retrieval,
    evaluate_bazi_retrieval,
    evaluate_iching_retrieval,
    evaluate_iching_retrieval_filtered,
)


def run_k_ablation(k_values: list[int] = None) -> dict:
    """Run retrieval evaluation at multiple k values."""
    from backend.rag.indexer import build_index, get_collection

    if k_values is None:
        k_values = [1, 3, 5, 8, 10]

    print("Building RAG index...")
    build_index(verbose=False)
    col = get_collection()
    print(f"Index contains {col.count()} documents\n")

    results = {}

    for k in k_values:
        print(f"--- Evaluating precision@{k} ---")
        tarot = evaluate_tarot_retrieval(col, k=k)
        bazi = evaluate_bazi_retrieval(col, k=k)
        iching_embed = evaluate_iching_retrieval(col, k=k)
        iching_filter = evaluate_iching_retrieval_filtered(col, k=k)

        pk = f"precision@{k}"

        # Overall production: tarot + bazi + iching_filtered
        prod_q = tarot["total_queries"] + bazi["total_queries"] + iching_filter["total_queries"]
        prod_h = tarot["hits"] + bazi["hits"] + iching_filter["hits"]

        entry = {
            "k": k,
            "tarot": {
                "queries": tarot["total_queries"],
                "hits": tarot["hits"],
                "precision": tarot[pk],
            },
            "bazi": {
                "queries": bazi["total_queries"],
                "hits": bazi["hits"],
                "precision": bazi[pk],
            },
            "iching_embedding": {
                "queries": iching_embed["total_queries"],
                "hits": iching_embed["hits"],
                "precision": iching_embed[pk],
            },
            "iching_filtered": {
                "queries": iching_filter["total_queries"],
                "hits": iching_filter["hits"],
                "precision": iching_filter[pk],
            },
            "overall_production": {
                "queries": prod_q,
                "hits": prod_h,
                "precision": round(prod_h / prod_q, 4) if prod_q else 0,
            },
        }
        results[k] = entry

        print(f"  Tarot:            {tarot[pk]:.1%}")
        print(f"  Bazi:             {bazi[pk]:.1%}")
        print(f"  I Ching (embed):  {iching_embed[pk]:.1%}")
        print(f"  I Ching (filter): {iching_filter[pk]:.1%}")
        print(f"  Overall (prod):   {prod_h}/{prod_q} = {prod_h/prod_q:.1%}")
        print()

    return results


def print_latex_table(results: dict) -> None:
    """Print a LaTeX-formatted table for the report."""
    k_values = sorted(results.keys())

    print("\n% LaTeX table for report")
    print("\\begin{table}[h]")
    print("\\centering")
    print("\\small")
    cols = "l" + "r" * len(k_values)
    print(f"\\begin{{tabular}}{{{cols}}}")
    print("\\toprule")
    header = "System & " + " & ".join(f"$k={k}$" for k in k_values) + " \\\\"
    print(header)
    print("\\midrule")

    for sys_key, sys_name in [
        ("tarot", "Tarot"),
        ("bazi", "Bazi"),
        ("iching_embedding", "I Ching (embedding)"),
        ("iching_filtered", "I Ching (filtered)"),
        ("overall_production", "\\textbf{Overall (production)}"),
    ]:
        vals = []
        for k in k_values:
            p = results[k][sys_key]["precision"]
            vals.append(f"{p:.1%}".replace("%", "\\%"))
        row = f"{sys_name} & " + " & ".join(vals) + " \\\\"
        print(row)

    print("\\bottomrule")
    print("\\end{tabular}")
    print("\\caption{Retrieval precision at varying $k$ values. Higher $k$ increases")
    print("recall but may dilute precision.}")
    print("\\label{tab:k-ablation}")
    print("\\end{table}")


def main():
    k_values = [1, 3, 5, 8, 10]
    results = run_k_ablation(k_values)

    # Save results
    out_path = Path(__file__).parent.parent.parent / "retrieval_k_ablation_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Results saved to {out_path}")

    print_latex_table(results)


if __name__ == "__main__":
    main()
