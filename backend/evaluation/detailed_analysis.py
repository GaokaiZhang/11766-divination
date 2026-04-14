"""
Detailed analysis of three-way evaluation results.

Produces per-system breakdowns, per-dimension head-to-head tallies,
and error patterns for inclusion in the final report.

Usage:
    python -m backend.evaluation.detailed_analysis
"""
import json
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def load_results() -> list[dict]:
    path = Path(__file__).parent.parent.parent / "evaluation_results.json"
    with open(path) as f:
        return json.load(f)


def per_system_scores(results: list[dict]) -> None:
    """Print average scores broken down by divination system."""
    dims = ["symbol_accuracy", "source_grounding",
            "combinatorial_specificity", "reflective_depth", "overall"]
    conditions = [("rag", "scores_rag"), ("baseline", "scores_baseline"),
                  ("stuffing", "scores_stuffing")]

    systems = defaultdict(lambda: {c: {d: [] for d in dims} for c, _ in conditions})

    for r in results:
        sys_name = r["system"]
        for cond, key in conditions:
            for dim in dims:
                if dim in r.get(key, {}):
                    systems[sys_name][cond][dim].append(r[key][dim])

    print("=" * 70)
    print("PER-SYSTEM AVERAGE SCORES")
    print("=" * 70)

    for sys_name in ["tarot", "bazi", "iching"]:
        data = systems[sys_name]
        n_cases = len(data["rag"]["overall"])
        print(f"\n--- {sys_name.upper()} ({n_cases} cases) ---")
        print(f"{'Dimension':<30} {'RAG':>8} {'Baseline':>10} {'Stuffing':>10}")
        print("-" * 60)
        for dim in dims:
            def avg(lst):
                return sum(lst) / len(lst) if lst else 0
            print(f"{dim:<30} {avg(data['rag'][dim]):>8.2f} "
                  f"{avg(data['baseline'][dim]):>10.2f} "
                  f"{avg(data['stuffing'][dim]):>10.2f}")


def per_dimension_headtohead(results: list[dict]) -> None:
    """Tally per-dimension wins for both comparison pairs."""
    dims = ["symbol_accuracy", "source_grounding",
            "combinatorial_specificity", "reflective_depth", "overall_preference"]

    for comp_key, label_a, label_b in [
        ("comparison_rag_vs_baseline", "RAG", "Baseline"),
        ("comparison_rag_vs_stuffing", "RAG", "Stuffing"),
    ]:
        print(f"\n{'='*70}")
        print(f"HEAD-TO-HEAD: {label_a} vs {label_b} (per dimension)")
        print(f"{'='*70}")
        print(f"{'Dimension':<30} {label_a+' wins':>10} {label_b+' wins':>12} {'Ties':>8}")
        print("-" * 62)

        for dim in dims:
            a_wins, b_wins, ties = 0, 0, 0
            for r in results:
                comp = r.get(comp_key, {})
                dim_data = comp.get(dim, {})
                winner = dim_data.get("winner", "tie")
                if winner == "A":
                    a_wins += 1
                elif winner == "B":
                    b_wins += 1
                else:
                    ties += 1
            print(f"{dim:<30} {a_wins:>10} {b_wins:>12} {ties:>8}")


def per_system_headtohead(results: list[dict]) -> None:
    """Per-system head-to-head overall preference."""
    print(f"\n{'='*70}")
    print("PER-SYSTEM HEAD-TO-HEAD (overall preference)")
    print(f"{'='*70}")

    for sys_name in ["tarot", "bazi", "iching"]:
        sys_results = [r for r in results if r["system"] == sys_name]
        print(f"\n--- {sys_name.upper()} ({len(sys_results)} cases) ---")

        for comp_key, label_a, label_b in [
            ("comparison_rag_vs_baseline", "RAG", "Baseline"),
            ("comparison_rag_vs_stuffing", "RAG", "Stuffing"),
        ]:
            a_wins, b_wins, ties = 0, 0, 0
            for r in sys_results:
                w = r.get(comp_key, {}).get("overall_preference", {}).get("winner", "tie")
                if w == "A":
                    a_wins += 1
                elif w == "B":
                    b_wins += 1
                else:
                    ties += 1
            print(f"  {label_a} vs {label_b}: {label_a} {a_wins}, {label_b} {b_wins}, Ties {ties}")


def score_gap_analysis(results: list[dict]) -> None:
    """Find dimensions with the largest/smallest gaps between conditions."""
    dims = ["symbol_accuracy", "source_grounding",
            "combinatorial_specificity", "reflective_depth", "overall"]

    print(f"\n{'='*70}")
    print("SCORE GAP ANALYSIS (RAG vs Context-Stuffing)")
    print(f"{'='*70}")

    for dim in dims:
        rag_scores = [r["scores_rag"][dim] for r in results if dim in r.get("scores_rag", {})]
        stuff_scores = [r["scores_stuffing"][dim] for r in results if dim in r.get("scores_stuffing", {})]
        if rag_scores and stuff_scores:
            rag_avg = sum(rag_scores) / len(rag_scores)
            stuff_avg = sum(stuff_scores) / len(stuff_scores)
            gap = stuff_avg - rag_avg
            print(f"  {dim:<30}: Stuffing {stuff_avg:.2f} - RAG {rag_avg:.2f} = gap {gap:+.2f}")

    print(f"\n{'='*70}")
    print("SCORE GAP ANALYSIS (RAG vs Baseline)")
    print(f"{'='*70}")

    for dim in dims:
        rag_scores = [r["scores_rag"][dim] for r in results if dim in r.get("scores_rag", {})]
        base_scores = [r["scores_baseline"][dim] for r in results if dim in r.get("scores_baseline", {})]
        if rag_scores and base_scores:
            rag_avg = sum(rag_scores) / len(rag_scores)
            base_avg = sum(base_scores) / len(base_scores)
            gap = rag_avg - base_avg
            print(f"  {dim:<30}: RAG {rag_avg:.2f} - Baseline {base_avg:.2f} = gap {gap:+.2f}")


def latex_per_system_table(results: list[dict]) -> None:
    """Generate LaTeX table for per-system scores."""
    dims = ["symbol_accuracy", "source_grounding",
            "combinatorial_specificity", "reflective_depth", "overall"]
    dim_labels = {
        "symbol_accuracy": "Symbol accuracy",
        "source_grounding": "Source grounding",
        "combinatorial_specificity": "Comb.\\ specificity",
        "reflective_depth": "Reflective depth",
        "overall": "Overall",
    }

    print("\n% LaTeX: Per-system breakdown")
    print("\\begin{table}[h]")
    print("\\centering")
    print("\\small")
    print("\\begin{tabular}{ll rrr}")
    print("\\toprule")
    print("System & Dimension & RAG & Baseline & Stuffing \\\\")
    print("\\midrule")

    for sys_name in ["tarot", "bazi", "iching"]:
        sys_results = [r for r in results if r["system"] == sys_name]
        n = len(sys_results)
        label = {"tarot": "Tarot", "bazi": "Bazi", "iching": "I Ching"}[sys_name]

        for i, dim in enumerate(dims):
            def avg(key):
                vals = [r[key][dim] for r in sys_results if dim in r.get(key, {})]
                return sum(vals) / len(vals) if vals else 0

            r_val = avg("scores_rag")
            b_val = avg("scores_baseline")
            s_val = avg("scores_stuffing")

            sys_col = f"{label} ({n})" if i == 0 else ""
            print(f"{sys_col} & {dim_labels[dim]} & {r_val:.2f} & {b_val:.2f} & {s_val:.2f} \\\\")

        if sys_name != "iching":
            print("\\midrule")

    print("\\bottomrule")
    print("\\end{tabular}")
    print("\\caption{Per-system average scores (1--5 scale).}")
    print("\\label{tab:per-system-scores}")
    print("\\end{table}")


def main():
    results = load_results()
    print(f"Loaded {len(results)} evaluation results\n")

    per_system_scores(results)
    per_dimension_headtohead(results)
    per_system_headtohead(results)
    score_gap_analysis(results)
    latex_per_system_table(results)


if __name__ == "__main__":
    main()
