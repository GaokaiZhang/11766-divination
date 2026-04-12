"""
LLM-as-Judge evaluation.

Replaces the expensive human evaluation (5 raters x 30 responses) with
automated metrics that can be run at scale. Addresses instructor feedback
on both Method (feasibility of human eval) and Engagement (justifying
RAG vs. simple prompting).

v2: Redesigned evaluation dimensions to focus on content quality where RAG
demonstrably helps, with explicit justification for each dimension and
anchor examples to reduce score compression.
"""
import json
import os

from openai import OpenAI


GROUNDING_PROMPT = """\
You are an evaluation judge for divination reading responses. Below is a \
divination reading (Tarot, Bazi, or I Ching) and an LLM-generated response. \
Assess the response's content quality on the dimensions below.

=== Reading ===
{reading}

=== Response ===
{response}

Rate each dimension on a 1-5 scale using the anchor examples below. Return \
ONLY a JSON object.

**SCORING ANCHORS (use these to calibrate — do NOT default to 4):**

symbol_accuracy: Does the response correctly name and interpret the specific \
symbols drawn?
  5 = Every symbol's meaning matches traditional sources (e.g., "The Tower \
represents sudden upheaval" is correct); no fabricated meanings.
  3 = Most symbols correct, but one meaning is vague or slightly off \
(e.g., describes The Tower as "a change in perspective" — softer than traditional).
  1 = Fabricates meanings (e.g., invents card names, confuses hexagram line \
texts, gets Bazi pillar elements wrong).

source_grounding: Does the response reference or paraphrase specific \
traditional texts, commentaries, or established meanings?
  5 = Directly quotes or closely paraphrases traditional sources (e.g., \
Wilhelm's "The Creative works sublime success" for Hexagram 1, or describes \
RWS card imagery accurately).
  3 = Uses general traditional concepts ("this hexagram relates to perseverance") \
without specific textual reference.
  1 = No reference to traditional sources; entirely improvised interpretation.

combinatorial_specificity: Does the interpretation account for how multiple \
symbols interact (card pairs, element clashes, changing lines, pillar \
relationships)?
  5 = Rich multi-symbol interpretation (e.g., "The tension between your Tower \
and Star cards suggests disruption followed by renewal"; or identifies how Day \
Master element interacts with other pillars).
  3 = Symbols interpreted individually, sequentially, without interaction.
  1 = Generic advice that could apply to any symbol combination.

reflective_depth: Does the response connect the reading's specific symbols to \
the user's question in a way that invites genuine self-examination?
  5 = Deep personal connection: uses specific symbol meanings to ask a \
thought-provoking follow-up tied to the user's stated concern.
  3 = Acknowledges the user's question but follow-up is surface-level or \
loosely connected to symbols.
  1 = No connection to user's question; robotic summary of symbols.

overall: Holistic quality — would this be a satisfying, accurate divination \
reading for a real user seeking self-reflection?
  5 = Excellent: accurate, grounded in tradition, personally meaningful.
  3 = Adequate: mostly correct but lacks depth or personal connection.
  1 = Poor: inaccurate, generic, or unhelpful.

Return:
{{
  "symbol_accuracy": <1-5>,
  "symbol_accuracy_rationale": "<which symbols were correct/incorrect?>",
  "source_grounding": <1-5>,
  "source_grounding_rationale": "<what traditional sources were referenced?>",
  "combinatorial_specificity": <1-5>,
  "combinatorial_specificity_rationale": "<how were symbol interactions handled?>",
  "reflective_depth": <1-5>,
  "reflective_depth_rationale": "<how did the response connect to the user?>",
  "overall": <1-5>
}}
"""

COMPARISON_PROMPT = """\
You are an evaluation judge comparing two divination reading responses. Both \
were generated for the same user question and reading. You do NOT know which \
system produced which response — evaluate purely on content quality.

=== User Question ===
{question}

=== Reading Context ===
{reading}

=== Response A ===
{response_a}

=== Response B ===
{response_b}

Compare the two responses on the dimensions below. For each, choose a winner \
or declare a tie. Focus on factual content quality, not stylistic differences \
like tone or sentence structure.

**Dimensions and what to look for:**

1. symbol_accuracy: Which response more accurately interprets the specific \
symbols in the reading? Look for fabricated meanings, confused symbols, or \
incorrect traditional interpretations.

2. source_grounding: Which response more faithfully references traditional \
texts and established meanings? Look for direct quotes, accurate paraphrases, \
or specific traditional concepts vs. vague improvisation.

3. combinatorial_specificity: Which response better interprets how the \
symbols interact with each other (not just individually)? Look for cross-symbol \
analysis, element interactions, card pair meanings, or changing-line dynamics.

4. reflective_depth: Which response more meaningfully connects the reading's \
specific symbols to the user's personal question? Look for symbol-grounded \
personalization, not generic advice.

5. overall_preference: Overall, which response provides a more accurate, \
specific, and personally meaningful divination reading?

Return ONLY a JSON object:
{{
  "symbol_accuracy": {{
    "winner": "A" or "B" or "tie",
    "rationale": "<specific evidence>"
  }},
  "source_grounding": {{
    "winner": "A" or "B" or "tie",
    "rationale": "<specific evidence>"
  }},
  "combinatorial_specificity": {{
    "winner": "A" or "B" or "tie",
    "rationale": "<specific evidence>"
  }},
  "reflective_depth": {{
    "winner": "A" or "B" or "tie",
    "rationale": "<specific evidence>"
  }},
  "overall_preference": {{
    "winner": "A" or "B" or "tie",
    "rationale": "<specific evidence>"
  }}
}}
"""

BAZI_ACCURACY_PROMPT = """\
You are an expert in Chinese Bazi (Four Pillars of Destiny). Below is a Bazi \
reading generated by an LLM from a user's birth information. Evaluate the \
computational correctness of the Four Pillars.

Birth date: {birth_date}
Birth time: {birth_time}

=== LLM-Generated Bazi Reading ===
{response}

Check:
1. Are the Four Pillars (Year/Month/Day/Hour Stem-Branch pairs) correct?
2. Is the Day Master element correctly identified?
3. Are the element interactions described accurately?

Return ONLY a JSON object:
{{
  "pillars_correct": true or false,
  "pillar_errors": "<describe any errors, or 'none'>",
  "day_master_correct": true or false,
  "element_interactions_accurate": true or false,
  "accuracy_score": <1-5>,
  "notes": "<any additional observations>"
}}
"""


class LLMJudge:
    """Automated evaluation using a secondary LLM as judge."""

    def __init__(self, api_key: str | None = None, model: str = "gpt-4o"):
        self.client = OpenAI(api_key=api_key or os.environ["OPENAI_API_KEY"])
        self.model = model

    def _call(self, prompt: str) -> dict:
        from .retry_util import retry_on_rate_limit
        resp = retry_on_rate_limit(
            self.client.chat.completions.create,
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=800,
        )
        raw = resp.choices[0].message.content.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(raw)

    def evaluate_grounding(self, reading: str, response: str) -> dict:
        """Score a single response on accuracy, grounding, specificity, depth."""
        prompt = GROUNDING_PROMPT.format(reading=reading, response=response)
        return self._call(prompt)

    def compare_responses(
        self, question: str, reading: str,
        response_rag: str, response_baseline: str
    ) -> dict:
        """Head-to-head comparison: RAG system vs. baseline."""
        prompt = COMPARISON_PROMPT.format(
            question=question,
            reading=reading,
            response_a=response_rag,
            response_b=response_baseline,
        )
        return self._call(prompt)

    def evaluate_bazi_accuracy(
        self, birth_date: str, birth_time: str | None, response: str
    ) -> dict:
        """Check if an LLM-generated Bazi reading is computationally correct."""
        prompt = BAZI_ACCURACY_PROMPT.format(
            birth_date=birth_date,
            birth_time=birth_time or "not provided",
            response=response,
        )
        return self._call(prompt)
