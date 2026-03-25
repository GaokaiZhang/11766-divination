import json
import random
from pathlib import Path

from .base import DivinationSystem, DivinationResult, UserBirthInfo

DATA_PATH = Path(__file__).parent.parent.parent / "data" / "tarot" / "cards.json"

# Default spread positions for 1-, 3-, and 5-card draws
SPREAD_POSITIONS = {
    1: ["Present"],
    3: ["Past", "Present", "Future"],
    5: ["Situation", "Challenge", "Foundation", "Approach", "Outcome"],
}


class TarotSystem(DivinationSystem):
    name = "tarot"
    requires_birth_date = False
    requires_birth_time = False

    def __init__(self):
        with open(DATA_PATH) as f:
            self._cards: list[dict] = json.load(f)["cards"]

    def draw(self, n: int = 3, seed: int | None = None) -> list[dict]:
        """Draw n unique cards, each with a randomly assigned orientation."""
        rng = random.Random(seed)
        drawn = rng.sample(self._cards, n)
        return [
            {**card, "is_reversed": rng.choice([True, False])}
            for card in drawn
        ]

    def compute(self, user_info: UserBirthInfo, n_cards: int = 3,
                seed: int | None = None) -> DivinationResult:
        cards = self.draw(n_cards, seed)
        positions = SPREAD_POSITIONS.get(n_cards, [f"Card {i+1}" for i in range(n_cards)])

        lines, symbols = [], []
        for pos, card in zip(positions, cards):
            orientation = "reversed" if card["is_reversed"] else "upright"
            meaning = card.get(orientation, {}).get("meaning", "")
            lines.append(f"{pos}: {card['name']} ({orientation}) — {meaning}")
            symbols.append(f"{card['name']} {orientation}")
            symbols.extend(card.get(orientation, {}).get("keywords", []))

        return DivinationResult(
            system="tarot",
            raw={"cards": cards, "positions": positions},
            summary="\n".join(lines),
            symbols=list(dict.fromkeys(symbols)),  # deduplicate, preserve order
        )

    def clarification_question(self, missing: list[str]) -> str:
        # Tarot never needs clarification
        return ""
