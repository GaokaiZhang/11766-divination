"""Tests for the Tarot divination system."""
import json
from pathlib import Path

import pytest

from backend.divination.tarot import TarotSystem, SPREAD_POSITIONS
from backend.divination.base import UserBirthInfo


@pytest.fixture
def tarot():
    return TarotSystem()


@pytest.fixture
def user():
    return UserBirthInfo(name="Test")


class TestTarotDataset:
    def test_78_cards_loaded(self, tarot):
        assert len(tarot._cards) == 78

    def test_22_major_arcana(self, tarot):
        major = [c for c in tarot._cards if c["arcana"] == "major"]
        assert len(major) == 22

    def test_56_minor_arcana(self, tarot):
        minor = [c for c in tarot._cards if c["arcana"] == "minor"]
        assert len(minor) == 56

    def test_14_per_suit(self, tarot):
        for suit in ("wands", "cups", "swords", "pentacles"):
            cards = [c for c in tarot._cards if c.get("suit") == suit]
            assert len(cards) == 14, f"{suit} has {len(cards)} cards, expected 14"

    def test_all_cards_have_meanings(self, tarot):
        for card in tarot._cards:
            assert "upright" in card, f"{card['name']} missing upright"
            assert "reversed" in card, f"{card['name']} missing reversed"
            assert card["upright"].get("meaning"), f"{card['name']} upright has no meaning"
            assert card["reversed"].get("meaning"), f"{card['name']} reversed has no meaning"

    def test_unique_ids(self, tarot):
        ids = [c["id"] for c in tarot._cards]
        assert len(ids) == len(set(ids)), "Duplicate card IDs found"


class TestTarotDraw:
    def test_draw_returns_correct_count(self, tarot):
        drawn = tarot.draw(3, seed=42)
        assert len(drawn) == 3

    def test_draw_no_duplicates(self, tarot):
        drawn = tarot.draw(5, seed=42)
        names = [c["name"] for c in drawn]
        assert len(names) == len(set(names))

    def test_draw_has_orientation(self, tarot):
        drawn = tarot.draw(3, seed=42)
        for card in drawn:
            assert "is_reversed" in card
            assert isinstance(card["is_reversed"], bool)

    def test_deterministic_with_seed(self, tarot):
        draw1 = tarot.draw(3, seed=99)
        draw2 = tarot.draw(3, seed=99)
        assert [c["name"] for c in draw1] == [c["name"] for c in draw2]

    def test_different_seeds_differ(self, tarot):
        draw1 = tarot.draw(3, seed=1)
        draw2 = tarot.draw(3, seed=2)
        names1 = [c["name"] for c in draw1]
        names2 = [c["name"] for c in draw2]
        # Extremely unlikely to be the same
        assert names1 != names2


class TestTarotCompute:
    def test_returns_divination_result(self, tarot, user):
        result = tarot.compute(user, seed=42)
        assert result.system == "tarot"
        assert result.summary
        assert result.symbols
        assert result.raw

    def test_summary_contains_card_names(self, tarot, user):
        result = tarot.compute(user, seed=42)
        # At least one card name should appear in the summary
        card_names = {c["name"] for c in tarot._cards}
        found = any(name in result.summary for name in card_names)
        assert found, "No card name found in summary"

    def test_raw_has_cards_and_positions(self, tarot, user):
        result = tarot.compute(user, n_cards=3, seed=42)
        assert "cards" in result.raw
        assert "positions" in result.raw
        assert len(result.raw["cards"]) == 3
        assert result.raw["positions"] == ["Past", "Present", "Future"]

    def test_spread_positions(self, tarot, user):
        for n, expected_positions in SPREAD_POSITIONS.items():
            result = tarot.compute(user, n_cards=n, seed=42)
            assert result.raw["positions"] == expected_positions

    def test_no_birth_required(self):
        system = TarotSystem()
        assert system.requires_birth_date is False
        assert system.requires_birth_time is False


class TestTarotDistribution:
    def test_uniform_draw_distribution(self, tarot):
        """Over many draws, each card should appear roughly equally."""
        from collections import Counter
        counts = Counter()
        n_draws = 1000
        for i in range(n_draws):
            drawn = tarot.draw(1, seed=i)
            counts[drawn[0]["name"]] += 1

        # With 78 cards and 1000 draws, expected ~12.8 per card
        # Allow wide range but no card should be 0 or > 50
        assert all(v > 0 for v in counts.values()), "Some cards never drawn"
        assert all(v < 50 for v in counts.values()), "Some cards drawn too often"
