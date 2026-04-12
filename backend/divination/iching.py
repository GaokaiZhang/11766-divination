"""
I Ching (易经) divination system.

Generates hexagrams using the three-coin method (or deterministic seed),
identifies changing lines, computes the transformed hexagram, and produces
a structured reading with symbols for RAG retrieval.

Data source: Richard Wilhelm translation (public domain) via
https://github.com/adamblvck/iching-wilhelm-dataset
"""
import json
import random
from pathlib import Path

from .base import DivinationSystem, DivinationResult, UserBirthInfo

DATA_PATH = Path(__file__).parent.parent.parent / "data" / "iching" / "hexagrams.json"

# Binary representation: bottom line = index 0, top line = index 5
# Each line is 6 (old yin, changing), 7 (young yang), 8 (young yin), or 9 (old yang, changing)
LINE_NAMES = {
    1: "初 (First / Bottom)",
    2: "二 (Second)",
    3: "三 (Third)",
    4: "四 (Fourth)",
    5: "五 (Fifth)",
    6: "上 (Sixth / Top)",
}


def _three_coin_toss(rng: random.Random) -> int:
    """Simulate three coin tosses. Returns 6, 7, 8, or 9.

    Each coin: heads=3, tails=2. Sum of 3 coins:
      6 = all tails (old yin, changing)
      7 = two tails + one heads (young yang)
      8 = two heads + one tail (young yin)
      9 = all heads (old yang, changing)
    """
    return sum(rng.choice([2, 3]) for _ in range(3))


def _lines_to_binary(lines: list[int]) -> str:
    """Convert line values to binary string (bottom to top).
    Yang (7, 9) = 1, Yin (6, 8) = 0.
    """
    return "".join("1" if v in (7, 9) else "0" for v in lines)


def _transform_lines(lines: list[int]) -> list[int]:
    """Apply changing lines: 6→7 (yin becomes yang), 9→8 (yang becomes yin)."""
    result = []
    for v in lines:
        if v == 6:
            result.append(7)
        elif v == 9:
            result.append(8)
        else:
            result.append(v)
    return result


class IChingSystem(DivinationSystem):
    name = "iching"
    requires_birth_date = False
    requires_birth_time = False

    def __init__(self):
        with open(DATA_PATH) as f:
            data = json.load(f)
        self._hexagrams: list[dict] = data["hexagrams"]
        # Build lookup by binary string
        self._by_binary: dict[str, dict] = {}
        for h in self._hexagrams:
            self._by_binary[h["binary"]] = h

    def _find_hexagram(self, binary: str) -> dict | None:
        return self._by_binary.get(binary)

    def cast(self, seed: int | None = None) -> dict:
        """Cast a hexagram using the three-coin method.

        Returns a dict with:
          - lines: list of 6 values (6/7/8/9)
          - changing: list of line positions (1-indexed) that are changing
          - primary_binary: binary string of the primary hexagram
          - transformed_binary: binary string after changing lines (or None)
        """
        rng = random.Random(seed)
        lines = [_three_coin_toss(rng) for _ in range(6)]
        changing = [i + 1 for i, v in enumerate(lines) if v in (6, 9)]

        primary_binary = _lines_to_binary(lines)
        transformed_binary = None
        if changing:
            transformed_lines = _transform_lines(lines)
            transformed_binary = _lines_to_binary(transformed_lines)

        return {
            "lines": lines,
            "changing": changing,
            "primary_binary": primary_binary,
            "transformed_binary": transformed_binary,
        }

    def compute(self, user_info: UserBirthInfo, seed: int | None = None,
                **kwargs) -> DivinationResult:
        cast = self.cast(seed)
        primary = self._find_hexagram(cast["primary_binary"])

        if not primary:
            # Fallback: shouldn't happen, but handle gracefully
            return DivinationResult(
                system="iching",
                raw=cast,
                summary="Could not find hexagram for this casting.",
                symbols=[],
            )

        # Build summary
        lines_desc = []
        for i, val in enumerate(cast["lines"]):
            pos = i + 1
            line_type = {6: "---x--- (old yin, changing)",
                         7: "------- (young yang)",
                         8: "--- --- (young yin)",
                         9: "---o--- (old yang, changing)"}[val]
            lines_desc.append(f"  Line {pos} {LINE_NAMES[pos]}: {line_type}")

        summary_parts = [
            f"Primary Hexagram: #{primary['number']} {primary['chinese']} "
            f"({primary['pinyin']}) — {primary['english']}",
            f"  {primary['unicode']}",
            f"  Upper trigram: {primary['upper_trigram']['symbolic']} "
            f"({primary['upper_trigram']['nature']})",
            f"  Lower trigram: {primary['lower_trigram']['symbolic']} "
            f"({primary['lower_trigram']['nature']})",
            f"\nJudgment: {primary['judgment']['text']}",
            f"\nImage: {primary['image']['text']}",
            f"\nLines cast:",
        ]
        summary_parts.extend(lines_desc)

        # Changing lines detail
        if cast["changing"]:
            summary_parts.append(f"\nChanging lines: {cast['changing']}")
            for pos in cast["changing"]:
                line_data = primary["lines"].get(str(pos), {})
                summary_parts.append(
                    f"  Line {pos}: {line_data.get('text', '(no text)')}"
                )

        # Transformed hexagram
        transformed = None
        if cast["transformed_binary"]:
            transformed = self._find_hexagram(cast["transformed_binary"])
            if transformed:
                summary_parts.append(
                    f"\nTransformed Hexagram: #{transformed['number']} "
                    f"{transformed['chinese']} ({transformed['pinyin']}) — "
                    f"{transformed['english']}"
                )
                summary_parts.append(
                    f"  Judgment: {transformed['judgment']['text']}"
                )

        summary = "\n".join(summary_parts)

        # Build symbols for RAG query — include hexagram numbers so the
        # retriever can construct precise queries and metadata filters.
        symbols = [
            f"Hexagram {primary['number']} {primary['english']}",
            primary["chinese"],
            primary["upper_trigram"]["symbolic"],
            primary["lower_trigram"]["symbolic"],
            primary["upper_trigram"]["nature"],
            primary["lower_trigram"]["nature"],
        ]
        if transformed:
            symbols.extend([
                f"Hexagram {transformed['number']} {transformed['english']}",
                transformed["chinese"],
                "changing lines",
                "transformation",
            ])
        # Add changing line positions with hexagram number for targeted retrieval
        for pos in cast["changing"]:
            symbols.append(f"Hexagram {primary['number']} line {pos}")

        raw = {
            "lines": cast["lines"],
            "changing": cast["changing"],
            "primary": {
                "number": primary["number"],
                "chinese": primary["chinese"],
                "pinyin": primary["pinyin"],
                "english": primary["english"],
                "unicode": primary["unicode"],
                "binary": cast["primary_binary"],
            },
            "transformed": None,
        }
        if transformed:
            raw["transformed"] = {
                "number": transformed["number"],
                "chinese": transformed["chinese"],
                "pinyin": transformed["pinyin"],
                "english": transformed["english"],
                "unicode": transformed["unicode"],
                "binary": cast["transformed_binary"],
            }

        return DivinationResult(
            system="iching",
            raw=raw,
            summary=summary,
            symbols=list(dict.fromkeys(symbols)),
        )

    def clarification_question(self, missing: list[str]) -> str:
        # I Ching doesn't require any user info
        return ""
