from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class UserBirthInfo:
    name: str
    birth_date: str | None = None        # YYYY-MM-DD
    birth_time: str | None = None        # HH:MM, 24-hour
    birth_location: str | None = None    # free-text, used for display / future tz correction

    def missing_for(self, system: "DivinationSystem") -> list[str]:
        missing = []
        if system.requires_birth_date and not self.birth_date:
            missing.append("birth_date")
        if system.requires_birth_time and not self.birth_time:
            missing.append("birth_time")
        return missing


@dataclass
class DivinationResult:
    system: str                  # "tarot" | "bazi" | "iching"
    raw: dict[str, Any]          # full structured output for frontend rendering
    summary: str                 # human-readable text injected into LLM system prompt
    symbols: list[str]           # key terms used to build the RAG query


class DivinationSystem(ABC):
    name: str = ""
    requires_birth_date: bool = False
    requires_birth_time: bool = False

    @abstractmethod
    def compute(self, user_info: UserBirthInfo, **kwargs) -> DivinationResult:
        """Run the divination computation and return a structured result."""
        ...

    @abstractmethod
    def clarification_question(self, missing: list[str]) -> str:
        """Return a natural-language question to ask the user for the given missing fields."""
        ...
