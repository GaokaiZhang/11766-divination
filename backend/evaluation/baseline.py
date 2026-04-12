"""
Baseline: simple LLM prompting with NO RAG, NO structured computation.

This module sends the same user input directly to the LLM and asks it to
produce a divination reading and interpretation purely from parametric
knowledge. Used as the control condition in our evaluation.
"""
import os

from openai import OpenAI


BASELINE_TAROT_PROMPT = """\
You are a Tarot reader. The user has asked for a three-card Past/Present/Future \
spread. Draw three random Tarot cards (from the standard 78-card Rider-Waite-Smith \
deck), assign each an orientation (upright or reversed), and give a personalized \
reading based on the cards you chose.

Ground your interpretation in the specific cards and their traditional meanings. \
Be warm, specific, and end with one follow-up question to deepen reflection.

User's name: {name}
User's question: {question}
"""

BASELINE_BAZI_PROMPT = """\
You are a Bazi (Four Pillars of Destiny) practitioner. The user has provided \
their birth date{time_clause}. Calculate their Four Pillars (Year, Month, Day, \
Hour) using the Chinese sexagenary cycle. Identify their Day Master element and \
give a personalized interpretation.

Ground your interpretation in the specific Heavenly Stems, Earthly Branches, \
and element interactions present in the chart. Be warm, specific, and end with \
one follow-up question to deepen reflection.

User's name: {name}
Birth date: {birth_date}
{birth_time_line}User's question: {question}
"""

BASELINE_ICHING_PROMPT = """\
You are an I Ching (Book of Changes / 易经) practitioner. The user has asked \
for a hexagram reading. Cast a hexagram using the three-coin method: for each \
of the six lines (bottom to top), toss three coins. Identify any changing lines \
and the resulting transformed hexagram if applicable.

Ground your interpretation in the specific hexagram's judgment, image, and any \
relevant changing line texts from the Wilhelm/Baynes translation. If there is a \
transformed hexagram, interpret the movement from the primary to the transformed \
hexagram. Be warm, specific, and end with one follow-up question to deepen \
reflection.

User's name: {name}
User's question: {question}
"""


class BaselineLLM:
    """LLM-only divination with no RAG or offline computation."""

    def __init__(self, api_key: str | None = None, model: str = "gpt-4o"):
        self.client = OpenAI(api_key=api_key or os.environ["OPENAI_API_KEY"])
        self.model = model

    def _create(self, prompt: str) -> str:
        from .retry_util import retry_on_rate_limit
        resp = retry_on_rate_limit(
            self.client.chat.completions.create,
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.85,
            max_tokens=800,
        )
        return resp.choices[0].message.content

    def generate_tarot(self, name: str, question: str) -> str:
        return self._create(BASELINE_TAROT_PROMPT.format(name=name, question=question))

    def generate_bazi(
        self, name: str, birth_date: str, birth_time: str | None, question: str
    ) -> str:
        time_clause = f" and birth time" if birth_time else ""
        birth_time_line = f"Birth time: {birth_time}\n" if birth_time else ""
        return self._create(BASELINE_BAZI_PROMPT.format(
            name=name, birth_date=birth_date, question=question,
            time_clause=time_clause, birth_time_line=birth_time_line,
        ))

    def generate_iching(self, name: str, question: str) -> str:
        return self._create(BASELINE_ICHING_PROMPT.format(name=name, question=question))
