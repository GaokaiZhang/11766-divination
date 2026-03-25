"""
Comparison runner: RAG system vs. baseline (simple LLM prompting).

Usage:
    python -m backend.evaluation.compare

Generates a side-by-side evaluation report showing where the full RAG
pipeline outperforms (or matches) simple prompting. This directly addresses
the instructor's feedback: "An evaluation against simple LLM prompting will
go a long way in justifying the project's relevance."
"""
import json
from pathlib import Path

from .baseline import BaselineLLM
from .judge import LLMJudge
from ..divination.base import UserBirthInfo, DivinationResult
from ..divination.tarot import TarotSystem
from ..divination.bazi import BaziSystem
from ..divination.iching import IChingSystem
from ..llm.client import DivinationLLM
from ..user.profile import UserProfile

# ---- Test cases ----

TAROT_CASES = [
    {"name": "Alice", "question": "I'm considering a career change but I'm scared."},
    {"name": "Ben", "question": "I just went through a breakup and I feel lost."},
    {"name": "Cara", "question": "I've been feeling creatively stuck for months."},
    {"name": "David", "question": "I'm about to become a parent and I don't feel ready."},
    {"name": "Eva", "question": "I keep having the same argument with my partner."},
]

BAZI_CASES = [
    {
        "name": "Lin",
        "birth_date": "1990-06-15",
        "birth_time": "14:30",
        "question": "I feel like I never finish what I start.",
    },
    {
        "name": "Wei",
        "birth_date": "1985-12-03",
        "birth_time": "08:00",
        "question": "I'm torn between stability and freedom.",
    },
    {
        "name": "Jun",
        "birth_date": "1998-03-22",
        "birth_time": "22:15",
        "question": "Why do I keep attracting the same kind of relationship?",
    },
]


def run_tarot_comparison(
    rag_llm: DivinationLLM,
    baseline_llm: BaselineLLM,
    judge: LLMJudge,
    tarot: TarotSystem,
    seed: int = 42,
) -> list[dict]:
    """Run all Tarot test cases and compare RAG vs baseline."""
    results = []
    for i, case in enumerate(TAROT_CASES):
        print(f"  Tarot case {i+1}/{len(TAROT_CASES)}: {case['name']}...")

        # RAG system: offline computation + RAG retrieval + grounded prompting
        user_info = UserBirthInfo(name=case["name"])
        reading = tarot.compute(user_info, seed=seed + i)
        profile = UserProfile(user_id=f"eval_{case['name']}", name=case["name"])
        messages = [{"role": "user", "content": case["question"]}]
        response_rag = rag_llm.chat(messages, reading, profile)

        # Baseline: simple prompting
        response_baseline = baseline_llm.generate_tarot(
            case["name"], case["question"]
        )

        # Judge: individual scores
        scores_rag = judge.evaluate_grounding(reading.summary, response_rag)
        scores_baseline = judge.evaluate_grounding(
            "No structured reading provided (baseline generated its own)",
            response_baseline,
        )

        # Judge: head-to-head
        comparison = judge.compare_responses(
            case["question"], response_rag, response_baseline
        )

        results.append({
            "system": "tarot",
            "case": case,
            "reading_summary": reading.summary,
            "response_rag": response_rag,
            "response_baseline": response_baseline,
            "scores_rag": scores_rag,
            "scores_baseline": scores_baseline,
            "comparison": comparison,
        })
    return results


def run_bazi_comparison(
    rag_llm: DivinationLLM,
    baseline_llm: BaselineLLM,
    judge: LLMJudge,
    bazi: BaziSystem,
) -> list[dict]:
    """Run all Bazi test cases and compare RAG vs baseline."""
    results = []
    for i, case in enumerate(BAZI_CASES):
        print(f"  Bazi case {i+1}/{len(BAZI_CASES)}: {case['name']}...")

        # RAG system
        user_info = UserBirthInfo(
            name=case["name"],
            birth_date=case["birth_date"],
            birth_time=case["birth_time"],
        )
        reading = bazi.compute(user_info)
        profile = UserProfile(
            user_id=f"eval_{case['name']}",
            name=case["name"],
            birth_date=case["birth_date"],
            birth_time=case["birth_time"],
        )
        messages = [{"role": "user", "content": case["question"]}]
        response_rag = rag_llm.chat(messages, reading, profile)

        # Baseline
        response_baseline = baseline_llm.generate_bazi(
            case["name"], case["birth_date"], case["birth_time"], case["question"]
        )

        # Judge: grounding
        scores_rag = judge.evaluate_grounding(reading.summary, response_rag)
        scores_baseline = judge.evaluate_grounding(
            "LLM self-generated Bazi chart (no verified computation)",
            response_baseline,
        )

        # Judge: Bazi accuracy (does the baseline even get the pillars right?)
        accuracy_baseline = judge.evaluate_bazi_accuracy(
            case["birth_date"], case["birth_time"], response_baseline
        )
        accuracy_rag = judge.evaluate_bazi_accuracy(
            case["birth_date"], case["birth_time"], response_rag
        )

        # Judge: head-to-head
        comparison = judge.compare_responses(
            case["question"], response_rag, response_baseline
        )

        results.append({
            "system": "bazi",
            "case": case,
            "reading_summary": reading.summary,
            "response_rag": response_rag,
            "response_baseline": response_baseline,
            "scores_rag": scores_rag,
            "scores_baseline": scores_baseline,
            "accuracy_rag": accuracy_rag,
            "accuracy_baseline": accuracy_baseline,
            "comparison": comparison,
        })
    return results


ICHING_CASES = [
    {"name": "Mei", "question": "I'm stuck between two life paths and can't decide."},
    {"name": "Hao", "question": "I feel like I've lost my sense of purpose."},
    {"name": "Yuki", "question": "Something in my life needs to end but I'm afraid to let go."},
]


def run_iching_comparison(
    rag_llm: DivinationLLM,
    baseline_llm: BaselineLLM,
    judge: LLMJudge,
    iching: IChingSystem,
    seed: int = 42,
) -> list[dict]:
    """Run all I Ching test cases and compare RAG vs baseline."""
    results = []
    for i, case in enumerate(ICHING_CASES):
        print(f"  I Ching case {i+1}/{len(ICHING_CASES)}: {case['name']}...")

        # RAG system: offline hexagram casting + RAG retrieval + grounded prompting
        user_info = UserBirthInfo(name=case["name"])
        reading = iching.compute(user_info, seed=seed + i)
        profile = UserProfile(user_id=f"eval_{case['name']}", name=case["name"])
        messages = [{"role": "user", "content": case["question"]}]
        response_rag = rag_llm.chat(messages, reading, profile)

        # Baseline: simple prompting (LLM generates its own hexagram)
        response_baseline = baseline_llm.generate_iching(
            case["name"], case["question"]
        )

        # Judge: individual scores
        scores_rag = judge.evaluate_grounding(reading.summary, response_rag)
        scores_baseline = judge.evaluate_grounding(
            "LLM self-generated hexagram (no verified casting or Wilhelm text)",
            response_baseline,
        )

        # Judge: head-to-head
        comparison = judge.compare_responses(
            case["question"], response_rag, response_baseline
        )

        results.append({
            "system": "iching",
            "case": case,
            "reading_summary": reading.summary,
            "response_rag": response_rag,
            "response_baseline": response_baseline,
            "scores_rag": scores_rag,
            "scores_baseline": scores_baseline,
            "comparison": comparison,
        })
    return results


def print_summary(all_results: list[dict]) -> None:
    """Print a human-readable summary of the comparison."""
    print("\n" + "=" * 70)
    print("EVALUATION SUMMARY: RAG System vs. Simple LLM Prompting")
    print("=" * 70)

    # Aggregate scores
    rag_scores = {"symbol_grounding": [], "specificity": [], "reflection_quality": [], "warmth": [], "overall": []}
    baseline_scores = {"symbol_grounding": [], "specificity": [], "reflection_quality": [], "warmth": [], "overall": []}
    comparison_wins = {"A": 0, "B": 0, "tie": 0}

    for r in all_results:
        for dim in rag_scores:
            if dim in r["scores_rag"]:
                rag_scores[dim].append(r["scores_rag"][dim])
            if dim in r["scores_baseline"]:
                baseline_scores[dim].append(r["scores_baseline"][dim])
        winner = r["comparison"].get("overall_preference", {}).get("winner", "tie")
        comparison_wins[winner] = comparison_wins.get(winner, 0) + 1

    print("\n--- Average Scores (1-5) ---")
    print(f"{'Dimension':<25} {'RAG System':>12} {'Baseline':>12}")
    print("-" * 50)
    for dim in rag_scores:
        avg_rag = sum(rag_scores[dim]) / len(rag_scores[dim]) if rag_scores[dim] else 0
        avg_base = sum(baseline_scores[dim]) / len(baseline_scores[dim]) if baseline_scores[dim] else 0
        print(f"{dim:<25} {avg_rag:>12.2f} {avg_base:>12.2f}")

    print(f"\n--- Head-to-Head (LLM Judge Overall Preference) ---")
    total = sum(comparison_wins.values())
    print(f"RAG System wins: {comparison_wins.get('A', 0)}/{total}")
    print(f"Baseline wins:   {comparison_wins.get('B', 0)}/{total}")
    print(f"Ties:            {comparison_wins.get('tie', 0)}/{total}")

    # Bazi accuracy
    bazi_results = [r for r in all_results if r["system"] == "bazi"]
    if bazi_results:
        print(f"\n--- Bazi Computational Accuracy ---")
        rag_correct = sum(1 for r in bazi_results if r.get("accuracy_rag", {}).get("pillars_correct", False))
        base_correct = sum(1 for r in bazi_results if r.get("accuracy_baseline", {}).get("pillars_correct", False))
        print(f"RAG System (offline computation): {rag_correct}/{len(bazi_results)} pillars correct")
        print(f"Baseline (LLM-generated):         {base_correct}/{len(bazi_results)} pillars correct")


def main():
    print("Initializing evaluation pipeline...")
    rag_llm = DivinationLLM()
    baseline_llm = BaselineLLM()
    judge = LLMJudge()
    tarot = TarotSystem()
    bazi = BaziSystem()
    iching = IChingSystem()

    print("\nRunning Tarot comparisons...")
    tarot_results = run_tarot_comparison(rag_llm, baseline_llm, judge, tarot)

    print("\nRunning Bazi comparisons...")
    bazi_results = run_bazi_comparison(rag_llm, baseline_llm, judge, bazi)

    print("\nRunning I Ching comparisons...")
    iching_results = run_iching_comparison(rag_llm, baseline_llm, judge, iching)

    all_results = tarot_results + bazi_results + iching_results

    # Save full results
    out_path = Path(__file__).parent.parent.parent / "evaluation_results.json"
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\nFull results saved to {out_path}")

    print_summary(all_results)


if __name__ == "__main__":
    main()
