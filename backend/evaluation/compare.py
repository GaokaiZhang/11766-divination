"""
Three-way comparison: RAG system vs. baseline vs. context-stuffing.

Usage:
    python -m backend.evaluation.compare

Conditions:
  A) RAG: offline computation + selective retrieval + grounded prompting
  B) Baseline: simple LLM prompting, no external data or computation
  C) Context-stuffing: offline computation + ALL curated docs in prompt (no retrieval)

Condition C isolates retrieval's contribution from curated data's contribution.
If C matches A, the value is the data. If A > C, selective retrieval adds value.

Addresses instructor midpoint feedback:
  - "Evaluate against simple LLM prompting" → A vs B
  - "Investigate how RAG actually helped" → A vs B vs C
  - "Context-stuffing baseline could be interesting" → condition C
"""
import json
from pathlib import Path

from .baseline import BaselineLLM
from .context_stuffing import ContextStuffingLLM
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
    stuffing_llm: ContextStuffingLLM,
    judge: LLMJudge,
    tarot: TarotSystem,
    seed: int = 42,
) -> list[dict]:
    """Run all Tarot test cases and compare RAG vs baseline vs context-stuffing."""
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

        # Context-stuffing: offline computation + ALL docs in prompt
        response_stuffing = stuffing_llm.generate(
            "tarot", case["name"], case["question"], reading.summary
        )

        # Judge: individual scores
        scores_rag = judge.evaluate_grounding(reading.summary, response_rag)
        scores_baseline = judge.evaluate_grounding(
            "No structured reading provided (baseline generated its own)",
            response_baseline,
        )
        scores_stuffing = judge.evaluate_grounding(reading.summary, response_stuffing)

        # Judge: head-to-head RAG vs baseline
        comparison_ab = judge.compare_responses(
            case["question"], reading.summary,
            response_rag, response_baseline
        )
        # Judge: head-to-head RAG vs context-stuffing
        comparison_ac = judge.compare_responses(
            case["question"], reading.summary,
            response_rag, response_stuffing
        )

        results.append({
            "system": "tarot",
            "case": case,
            "reading_summary": reading.summary,
            "response_rag": response_rag,
            "response_baseline": response_baseline,
            "response_stuffing": response_stuffing,
            "scores_rag": scores_rag,
            "scores_baseline": scores_baseline,
            "scores_stuffing": scores_stuffing,
            "comparison_rag_vs_baseline": comparison_ab,
            "comparison_rag_vs_stuffing": comparison_ac,
        })
    return results


def run_bazi_comparison(
    rag_llm: DivinationLLM,
    baseline_llm: BaselineLLM,
    stuffing_llm: ContextStuffingLLM,
    judge: LLMJudge,
    bazi: BaziSystem,
) -> list[dict]:
    """Run all Bazi test cases and compare RAG vs baseline vs context-stuffing."""
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

        # Context-stuffing
        response_stuffing = stuffing_llm.generate(
            "bazi", case["name"], case["question"], reading.summary
        )

        # Judge: grounding
        scores_rag = judge.evaluate_grounding(reading.summary, response_rag)
        scores_baseline = judge.evaluate_grounding(
            "LLM self-generated Bazi chart (no verified computation)",
            response_baseline,
        )
        scores_stuffing = judge.evaluate_grounding(reading.summary, response_stuffing)

        # Judge: Bazi accuracy
        accuracy_baseline = judge.evaluate_bazi_accuracy(
            case["birth_date"], case["birth_time"], response_baseline
        )
        accuracy_rag = judge.evaluate_bazi_accuracy(
            case["birth_date"], case["birth_time"], response_rag
        )

        # Judge: head-to-head
        comparison_ab = judge.compare_responses(
            case["question"], reading.summary,
            response_rag, response_baseline
        )
        comparison_ac = judge.compare_responses(
            case["question"], reading.summary,
            response_rag, response_stuffing
        )

        results.append({
            "system": "bazi",
            "case": case,
            "reading_summary": reading.summary,
            "response_rag": response_rag,
            "response_baseline": response_baseline,
            "response_stuffing": response_stuffing,
            "scores_rag": scores_rag,
            "scores_baseline": scores_baseline,
            "scores_stuffing": scores_stuffing,
            "accuracy_rag": accuracy_rag,
            "accuracy_baseline": accuracy_baseline,
            "comparison_rag_vs_baseline": comparison_ab,
            "comparison_rag_vs_stuffing": comparison_ac,
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
    stuffing_llm: ContextStuffingLLM,
    judge: LLMJudge,
    iching: IChingSystem,
    seed: int = 42,
) -> list[dict]:
    """Run all I Ching test cases and compare RAG vs baseline vs context-stuffing."""
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

        # Context-stuffing: offline computation + ALL hexagram-level docs
        # (line texts excluded — exceed context window; noted as limitation)
        response_stuffing = stuffing_llm.generate(
            "iching", case["name"], case["question"], reading.summary
        )

        # Judge: individual scores
        scores_rag = judge.evaluate_grounding(reading.summary, response_rag)
        scores_baseline = judge.evaluate_grounding(
            "LLM self-generated hexagram (no verified casting or Wilhelm text)",
            response_baseline,
        )
        scores_stuffing = judge.evaluate_grounding(reading.summary, response_stuffing)

        # Judge: head-to-head
        comparison_ab = judge.compare_responses(
            case["question"], reading.summary,
            response_rag, response_baseline
        )
        comparison_ac = judge.compare_responses(
            case["question"], reading.summary,
            response_rag, response_stuffing
        )

        results.append({
            "system": "iching",
            "case": case,
            "reading_summary": reading.summary,
            "response_rag": response_rag,
            "response_baseline": response_baseline,
            "response_stuffing": response_stuffing,
            "scores_rag": scores_rag,
            "scores_baseline": scores_baseline,
            "scores_stuffing": scores_stuffing,
            "comparison_rag_vs_baseline": comparison_ab,
            "comparison_rag_vs_stuffing": comparison_ac,
        })
    return results


def _avg(vals: list) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _count_wins(results: list[dict], comparison_key: str) -> dict:
    """Count A/B/tie wins across a list of results for a comparison key."""
    wins = {"A": 0, "B": 0, "tie": 0}
    for r in results:
        comp = r.get(comparison_key, {})
        w = comp.get("overall_preference", {}).get("winner", "tie")
        wins[w] = wins.get(w, 0) + 1
    return wins


def print_summary(all_results: list[dict]) -> None:
    """Print a human-readable summary of the three-way comparison."""
    print("\n" + "=" * 70)
    print("EVALUATION SUMMARY: RAG vs. Baseline vs. Context-Stuffing")
    print("=" * 70)

    # Updated dimensions (v2) — content quality focused
    dims = ["symbol_accuracy", "source_grounding",
            "combinatorial_specificity", "reflective_depth", "overall"]

    scores = {
        "rag": {d: [] for d in dims},
        "baseline": {d: [] for d in dims},
        "stuffing": {d: [] for d in dims},
    }
    for r in all_results:
        for cond, key in [("rag", "scores_rag"), ("baseline", "scores_baseline"),
                          ("stuffing", "scores_stuffing")]:
            for dim in dims:
                if dim in r.get(key, {}):
                    scores[cond][dim].append(r[key][dim])

    print("\n--- Average Scores (1-5) ---")
    print(f"{'Dimension':<30} {'RAG':>8} {'Baseline':>10} {'Stuffing':>10}")
    print("-" * 60)
    for dim in dims:
        print(f"{dim:<30} {_avg(scores['rag'][dim]):>8.2f} "
              f"{_avg(scores['baseline'][dim]):>10.2f} "
              f"{_avg(scores['stuffing'][dim]):>10.2f}")

    # Head-to-head: RAG vs Baseline
    wins_ab = _count_wins(all_results, "comparison_rag_vs_baseline")
    total = sum(wins_ab.values())
    print(f"\n--- RAG vs. Baseline (head-to-head, {total} cases) ---")
    print(f"  RAG wins:      {wins_ab['A']}")
    print(f"  Baseline wins: {wins_ab['B']}")
    print(f"  Ties:          {wins_ab['tie']}")

    # Head-to-head: RAG vs Context-Stuffing
    wins_ac = _count_wins(all_results, "comparison_rag_vs_stuffing")
    total_ac = sum(wins_ac.values())
    print(f"\n--- RAG vs. Context-Stuffing (head-to-head, {total_ac} cases) ---")
    print(f"  RAG wins:      {wins_ac['A']}")
    print(f"  Stuffing wins: {wins_ac['B']}")
    print(f"  Ties:          {wins_ac['tie']}")

    # Bazi accuracy
    bazi_results = [r for r in all_results if r["system"] == "bazi"]
    if bazi_results:
        print(f"\n--- Bazi Computational Accuracy ---")
        rag_correct = sum(1 for r in bazi_results if r.get("accuracy_rag", {}).get("pillars_correct", False))
        base_correct = sum(1 for r in bazi_results if r.get("accuracy_baseline", {}).get("pillars_correct", False))
        print(f"  RAG (offline computation): {rag_correct}/{len(bazi_results)} pillars correct")
        print(f"  Baseline (LLM-generated):  {base_correct}/{len(bazi_results)} pillars correct")


def main():
    from dotenv import load_dotenv
    load_dotenv()

    print("Initializing evaluation pipeline...")
    rag_llm = DivinationLLM()
    baseline_llm = BaselineLLM()
    stuffing_llm = ContextStuffingLLM()
    judge = LLMJudge()
    tarot = TarotSystem()
    bazi = BaziSystem()
    iching = IChingSystem()

    print("\nRunning Tarot comparisons (RAG vs Baseline vs Context-Stuffing)...")
    tarot_results = run_tarot_comparison(rag_llm, baseline_llm, stuffing_llm, judge, tarot)

    print("\nRunning Bazi comparisons...")
    bazi_results = run_bazi_comparison(rag_llm, baseline_llm, stuffing_llm, judge, bazi)

    print("\nRunning I Ching comparisons...")
    iching_results = run_iching_comparison(rag_llm, baseline_llm, stuffing_llm, judge, iching)

    all_results = tarot_results + bazi_results + iching_results

    # Save full results
    out_path = Path(__file__).parent.parent.parent / "evaluation_results.json"
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\nFull results saved to {out_path}")

    print_summary(all_results)


if __name__ == "__main__":
    main()
