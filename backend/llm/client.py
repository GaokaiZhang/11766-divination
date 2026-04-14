import json
import logging
import os
import time

from openai import OpenAI

from ..divination.base import DivinationResult
from ..rag.retriever import retrieve, retrieve_expanded
from ..user.profile import UserProfile
from .prompts import (
    READING_CONTEXT_TEMPLATE,
    SYSTEM_NAMES,
    SYSTEM_PROMPT,
    THEME_EXTRACTION_PROMPT,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Guardrails
# ---------------------------------------------------------------------------

# Topics the system should refuse to engage with
SAFETY_TRIGGERS = [
    "suicide", "self-harm", "kill myself", "end my life", "want to die",
    "hurt myself", "not worth living",
]

SAFETY_RESPONSE = (
    "I can hear that you're going through something really difficult right now. "
    "I'm a reflective companion, not a counselor, and what you're describing "
    "deserves real human support. Please reach out to the 988 Suicide & Crisis "
    "Lifeline (call or text 988) or the Crisis Text Line (text HOME to 741741). "
    "You don't have to carry this alone."
)

OUTPUT_GUARDRAIL_PHRASES = [
    "I am a doctor", "medical advice", "I diagnose", "you should take",
    "prescription", "as your therapist", "clinical assessment",
]


def _check_input_safety(text: str) -> str | None:
    """Return a safety response if the input contains crisis signals, else None."""
    lower = text.lower()
    for trigger in SAFETY_TRIGGERS:
        if trigger in lower:
            logger.warning("Safety trigger detected in user input")
            return SAFETY_RESPONSE
    return None


def _check_output_safety(text: str) -> str:
    """Scrub LLM output that oversteps into medical/clinical territory."""
    lower = text.lower()
    for phrase in OUTPUT_GUARDRAIL_PHRASES:
        if phrase in lower:
            logger.warning("Output guardrail triggered: %s", phrase)
            return text + (
                "\n\n*For clinical or medical concerns, please consult "
                "a qualified professional.*"
            )
    return text


# ---------------------------------------------------------------------------
# Token estimation (lightweight, no tiktoken dependency)
# ---------------------------------------------------------------------------

def _estimate_tokens(text: str) -> int:
    """Rough token count (~4 chars per token for English)."""
    return len(text) // 4


def _truncate_messages(
    messages: list[dict], max_tokens: int = 6000
) -> list[dict]:
    """Keep the most recent messages that fit within a token budget.

    Preserves the first two messages (user question + assistant initial response)
    and the most recent messages, trimming from the middle.
    """
    if not messages:
        return messages

    total = sum(_estimate_tokens(m.get("content", "")) for m in messages)
    if total <= max_tokens:
        return messages

    logger.info("Truncating conversation: %d estimated tokens → %d budget", total, max_tokens)

    # Keep the opening exchange and the most recent messages
    keep_start = messages[:2]
    keep_end = messages[-6:]

    # If even the kept messages exceed budget, just keep the last few
    kept_tokens = sum(_estimate_tokens(m.get("content", "")) for m in keep_start + keep_end)
    if kept_tokens > max_tokens:
        return messages[-4:]

    # Avoid duplicates if conversation is short
    if len(messages) <= len(keep_start) + len(keep_end):
        return messages

    return keep_start + [
        {"role": "system", "content": "[Earlier conversation trimmed for context length]"}
    ] + keep_end


# ---------------------------------------------------------------------------
# Main LLM client
# ---------------------------------------------------------------------------

class DivinationLLM:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o",
    ):
        self.client = OpenAI(api_key=api_key or os.environ["OPENAI_API_KEY"])
        self.model = model

    # ------------------------------------------------------------------
    # Context assembly (with expanded RAG retrieval)
    # ------------------------------------------------------------------

    def _build_system_context(
        self, result: DivinationResult, user: UserProfile, n_rag: int = 8
    ) -> str:
        # Use expanded retrieval for better coverage
        if result.symbols:
            chunks = retrieve_expanded(
                result.symbols, system=result.system, n_results=n_rag
            )
        else:
            chunks = retrieve(
                result.summary[:200], n_results=n_rag, system=result.system
            )

        rag_text = "\n\n".join(c["text"] for c in chunks)

        birth_parts = []
        if user.birth_date:
            birth_parts.append(f"Birth date: {user.birth_date}")
        if user.birth_time:
            birth_parts.append(f"Birth time: {user.birth_time}")
        if user.birth_location:
            birth_parts.append(f"Birth location: {user.birth_location}")
        birth_info = "\n".join(birth_parts) + "\n" if birth_parts else ""

        past_themes = ""
        if user.themes:
            past_themes = f"Recurring themes from past sessions: {', '.join(user.themes)}\n"

        context = READING_CONTEXT_TEMPLATE.format(
            system=SYSTEM_NAMES.get(result.system, result.system.capitalize()),
            reading_summary=result.summary,
            rag_context=rag_text,
            name=user.name,
            birth_info=birth_info,
            past_themes=past_themes,
        )
        return SYSTEM_PROMPT + "\n\n" + context

    # ------------------------------------------------------------------
    # Chat (with guardrails + context management + logging)
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: list[dict],
        result: DivinationResult,
        user: UserProfile,
    ) -> str:
        # Input safety check on the latest user message
        if messages:
            last_user_msg = next(
                (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
            )
            safety = _check_input_safety(last_user_msg)
            if safety:
                return safety

        system_content = self._build_system_context(result, user)

        # Context window management: truncate long conversations
        trimmed = _truncate_messages(messages, max_tokens=6000)

        start = time.time()
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system_content}] + trimmed,
                temperature=0.8,
                max_tokens=900,
            )
        except Exception:
            # Retry with backoff for rate limits during evaluation
            import time as _time
            from openai import RateLimitError
            _time.sleep(3)
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system_content}] + trimmed,
                temperature=0.8,
                max_tokens=900,
            )
        elapsed_ms = int((time.time() - start) * 1000)

        reply = response.choices[0].message.content
        usage = response.usage

        logger.info(
            "LLM call: model=%s, prompt_tokens=%s, completion_tokens=%s, "
            "total_tokens=%s, latency=%dms",
            self.model,
            usage.prompt_tokens if usage else "?",
            usage.completion_tokens if usage else "?",
            usage.total_tokens if usage else "?",
            elapsed_ms,
        )

        # Output safety check
        reply = _check_output_safety(reply)

        return reply

    # ------------------------------------------------------------------
    # Theme extraction (structured output with JSON)
    # ------------------------------------------------------------------

    def extract_themes(self, conversation: list[dict]) -> list[str]:
        """Extract 1–3 thematic phrases from the conversation for the user profile."""
        formatted = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in conversation
        )
        start = time.time()
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": THEME_EXTRACTION_PROMPT.format(conversation=formatted),
                }
            ],
            temperature=0.0,
            max_tokens=80,
            response_format={"type": "json_object"},
        )
        elapsed_ms = int((time.time() - start) * 1000)
        logger.info("Theme extraction: latency=%dms", elapsed_ms)

        raw = response.choices[0].message.content.strip()
        try:
            parsed = json.loads(raw)
            # Handle both {"themes": [...]} and bare [...]
            if isinstance(parsed, list):
                return [t for t in parsed if isinstance(t, str)]
            if isinstance(parsed, dict) and "themes" in parsed:
                return [t for t in parsed["themes"] if isinstance(t, str)]
            return []
        except json.JSONDecodeError:
            logger.warning("Theme extraction failed to parse JSON: %s", raw[:100])
            return []
