"""
Context-stuffing baseline: ALL curated documents stuffed into the system prompt.

This condition isolates retrieval's contribution from curated data's contribution.
If context-stuffing matches RAG performance, then the value comes from having
curated data, not from retrieval selecting the right docs. If RAG outperforms
context-stuffing, then selective retrieval adds value beyond data curation.

Token budgets (measured with tiktoken o200k_base):
  - Tarot:  176 docs, ~10k tokens — fits fully
  - Bazi:    85 docs, ~9k tokens — fits fully
  - I Ching: 640 docs, ~95k tokens — full set exceeds the API's 30k TPM
    rate limit. We stuff only the 64 overview docs (~7k tokens) and drop
    the symbolic, judgment, image, and line docs. This is a known
    limitation noted in the evaluation.
"""
import os

from openai import OpenAI

from ..rag.indexer import get_collection


def _load_system_docs(system: str, exclude_types: set[str] | None = None) -> str:
    """Load all RAG docs for a system as a single text block."""
    col = get_collection()
    where = {"system": system}
    results = col.get(where=where)

    docs = results["documents"]
    metas = results["metadatas"]

    if exclude_types:
        filtered = [(d, m) for d, m in zip(docs, metas)
                     if m.get("type") not in exclude_types]
        docs = [d for d, _ in filtered]

    return "\n\n---\n\n".join(docs)


CONTEXT_STUFFING_PROMPT = """\
You are a {system_name} practitioner. Below is a complete reference library of \
traditional {system_name} meanings and interpretations. Use ONLY this reference \
material to ground your reading — do not rely on your own knowledge of {system_name}.

The user has received the following reading from an offline computation system. \
Interpret this reading for them using the reference material below.

=== READING (computed offline) ===
{reading_summary}

=== COMPLETE REFERENCE LIBRARY ({doc_count} entries) ===
{all_docs}

=== END REFERENCE LIBRARY ===

Now give a personalized interpretation of this reading for the user. Ground your \
response in the specific symbols from the reading and the reference material above. \
Be warm and reflective. End with one follow-up question.

User's name: {name}
User's question: {question}
"""

SYSTEM_DISPLAY_NAMES = {
    "tarot": "Tarot",
    "bazi": "Bazi (Four Pillars of Destiny)",
    "iching": "I Ching (Book of Changes)",
}


class ContextStuffingLLM:
    """All curated docs in system prompt — no retrieval, but same curated data."""

    def __init__(self, api_key: str | None = None, model: str = "gpt-4o"):
        self.client = OpenAI(api_key=api_key or os.environ["OPENAI_API_KEY"])
        self.model = model
        # Pre-load docs for each system
        self._docs_cache: dict[str, tuple[str, int]] = {}

    def _get_docs(self, system: str) -> tuple[str, int]:
        """Return (docs_text, doc_count) for a system, cached."""
        if system not in self._docs_cache:
            # I Ching: use only overview docs — full set exceeds 30k TPM limit
            exclude = {"line", "symbolic", "judgment", "image"} if system == "iching" else None
            docs_text = _load_system_docs(system, exclude_types=exclude)
            doc_count = docs_text.count("\n\n---\n\n") + 1
            self._docs_cache[system] = (docs_text, doc_count)
        return self._docs_cache[system]

    def generate(
        self, system: str, name: str, question: str, reading_summary: str
    ) -> str:
        """Generate a reading with all system docs stuffed in context."""
        docs_text, doc_count = self._get_docs(system)
        prompt = CONTEXT_STUFFING_PROMPT.format(
            system_name=SYSTEM_DISPLAY_NAMES.get(system, system),
            reading_summary=reading_summary,
            all_docs=docs_text,
            doc_count=doc_count,
            name=name,
            question=question,
        )
        from .retry_util import retry_on_rate_limit
        resp = retry_on_rate_limit(
            self.client.chat.completions.create,
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.85,
            max_tokens=800,
        )
        return resp.choices[0].message.content
