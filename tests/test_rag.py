"""Tests for RAG data integrity — ensures all data files parse correctly."""
import json
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).parent.parent / "data"


class TestTarotData:
    def test_cards_json_valid(self):
        data = json.load(open(DATA_DIR / "tarot" / "cards.json"))
        assert len(data["cards"]) == 78

    def test_interactions_json_valid(self):
        data = json.load(open(DATA_DIR / "tarot" / "interactions.json"))
        entries = data["entries"]
        assert len(entries) > 0
        for e in entries:
            assert "id" in e and "text" in e and "meta" in e

    def test_spreads_json_valid(self):
        data = json.load(open(DATA_DIR / "tarot" / "spreads.json"))
        entries = data["entries"]
        assert len(entries) > 0
        for e in entries:
            assert "id" in e and "text" in e


class TestBaziData:
    @pytest.mark.parametrize("filename,min_entries", [
        ("stems.json", 10),
        ("branches.json", 12),
        ("combinations.json", 5),
        ("ten_gods.json", 10),
        ("hidden_stems.json", 12),
        ("branch_relationships.json", 20),
    ])
    def test_bazi_file_valid(self, filename, min_entries):
        data = json.load(open(DATA_DIR / "bazi" / filename))
        entries = data["entries"]
        assert len(entries) >= min_entries, f"{filename} has {len(entries)} entries"
        for e in entries:
            assert "id" in e and "text" in e, f"Missing fields in {filename}"


class TestIChingData:
    def test_hexagrams_json_valid(self):
        data = json.load(open(DATA_DIR / "iching" / "hexagrams.json"))
        assert len(data["hexagrams"]) == 64

    def test_all_hexagrams_have_lines(self):
        data = json.load(open(DATA_DIR / "iching" / "hexagrams.json"))
        for h in data["hexagrams"]:
            assert len(h.get("lines", {})) == 6, f"#{h['number']} missing lines"

    def test_all_line_texts_nonempty(self):
        data = json.load(open(DATA_DIR / "iching" / "hexagrams.json"))
        for h in data["hexagrams"]:
            for line_num in ("1", "2", "3", "4", "5", "6"):
                text = h["lines"][line_num].get("text", "")
                assert text, f"#{h['number']} line {line_num} has no text"


class TestTotalDocCount:
    def test_total_documents_at_least_800(self):
        """Verify our total RAG document count matches expectations."""
        total = 0

        # Tarot cards
        cards = json.load(open(DATA_DIR / "tarot" / "cards.json"))["cards"]
        total += len(cards) * 2

        # Tarot extras
        for f in ("interactions.json", "spreads.json"):
            total += len(json.load(open(DATA_DIR / "tarot" / f))["entries"])

        # Bazi
        for f in ("stems.json", "branches.json", "combinations.json",
                   "ten_gods.json", "hidden_stems.json", "branch_relationships.json"):
            total += len(json.load(open(DATA_DIR / "bazi" / f))["entries"])

        # I Ching
        hexs = json.load(open(DATA_DIR / "iching" / "hexagrams.json"))["hexagrams"]
        total += sum(1 for h in hexs if h.get("symbolic_description"))
        total += sum(1 for h in hexs if h.get("judgment", {}).get("text"))
        total += sum(1 for h in hexs if h.get("image", {}).get("text"))
        total += sum(1 for h in hexs
                     for l in h.get("lines", {}).values() if l.get("text"))

        assert total >= 800, f"Only {total} documents, expected >= 800"
