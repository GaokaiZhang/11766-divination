"""Tests for the I Ching divination system."""
import pytest

from backend.divination.iching import (
    IChingSystem,
    _three_coin_toss,
    _lines_to_binary,
    _transform_lines,
)
from backend.divination.base import UserBirthInfo


@pytest.fixture
def iching():
    return IChingSystem()


@pytest.fixture
def user():
    return UserBirthInfo(name="Test")


class TestIChingDataset:
    def test_64_hexagrams_loaded(self, iching):
        assert len(iching._hexagrams) == 64

    def test_64_binary_lookups(self, iching):
        assert len(iching._by_binary) == 64

    def test_all_hexagrams_have_required_fields(self, iching):
        for h in iching._hexagrams:
            assert h.get("number"), f"Missing number"
            assert h.get("chinese"), f"#{h['number']} missing chinese"
            assert h.get("english"), f"#{h['number']} missing english"
            assert h.get("binary"), f"#{h['number']} missing binary"
            assert h.get("judgment", {}).get("text"), f"#{h['number']} missing judgment"
            assert h.get("image", {}).get("text"), f"#{h['number']} missing image"

    def test_all_hexagrams_have_6_lines(self, iching):
        for h in iching._hexagrams:
            lines = h.get("lines", {})
            assert len(lines) == 6, f"#{h['number']} has {len(lines)} lines"
            for i in range(1, 7):
                assert str(i) in lines, f"#{h['number']} missing line {i}"

    def test_binary_strings_are_6_digits(self, iching):
        for h in iching._hexagrams:
            assert len(h["binary"]) == 6, f"#{h['number']} binary: {h['binary']}"
            assert all(c in "01" for c in h["binary"])

    def test_unique_binaries(self, iching):
        binaries = [h["binary"] for h in iching._hexagrams]
        assert len(binaries) == len(set(binaries))


class TestCoinToss:
    def test_values_in_range(self):
        import random
        rng = random.Random(42)
        for _ in range(100):
            val = _three_coin_toss(rng)
            assert val in (6, 7, 8, 9)

    def test_all_values_possible(self):
        """Over many tosses, all four values should appear."""
        import random
        rng = random.Random(42)
        seen = set()
        for _ in range(1000):
            seen.add(_three_coin_toss(rng))
        assert seen == {6, 7, 8, 9}


class TestLineConversions:
    def test_lines_to_binary(self):
        # Yang lines (7, 9) → 1, Yin lines (6, 8) → 0
        assert _lines_to_binary([7, 8, 7, 8, 7, 8]) == "101010"
        assert _lines_to_binary([9, 6, 9, 6, 9, 6]) == "101010"
        assert _lines_to_binary([7, 7, 7, 7, 7, 7]) == "111111"
        assert _lines_to_binary([8, 8, 8, 8, 8, 8]) == "000000"

    def test_transform_lines(self):
        # 6 (old yin) → 7 (young yang), 9 (old yang) → 8 (young yin)
        assert _transform_lines([6, 7, 8, 9, 7, 8]) == [7, 7, 8, 8, 7, 8]
        # No changing lines → same output
        assert _transform_lines([7, 8, 7, 8, 7, 8]) == [7, 8, 7, 8, 7, 8]


class TestIChingCast:
    def test_cast_returns_6_lines(self, iching):
        cast = iching.cast(seed=42)
        assert len(cast["lines"]) == 6
        assert all(v in (6, 7, 8, 9) for v in cast["lines"])

    def test_cast_deterministic(self, iching):
        cast1 = iching.cast(seed=42)
        cast2 = iching.cast(seed=42)
        assert cast1["lines"] == cast2["lines"]

    def test_changing_lines_identified(self, iching):
        cast = iching.cast(seed=42)
        expected_changing = [i + 1 for i, v in enumerate(cast["lines"]) if v in (6, 9)]
        assert cast["changing"] == expected_changing

    def test_transformed_binary_when_changing(self, iching):
        # Find a seed that produces changing lines
        for seed in range(100):
            cast = iching.cast(seed=seed)
            if cast["changing"]:
                assert cast["transformed_binary"] is not None
                assert cast["transformed_binary"] != cast["primary_binary"]
                break

    def test_no_transformed_when_no_changing(self, iching):
        # Find a seed with no changing lines (all 7s and 8s)
        for seed in range(1000):
            cast = iching.cast(seed=seed)
            if not cast["changing"]:
                assert cast["transformed_binary"] is None
                break


class TestIChingCompute:
    def test_returns_divination_result(self, iching, user):
        result = iching.compute(user, seed=42)
        assert result.system == "iching"
        assert result.summary
        assert result.symbols
        assert result.raw

    def test_primary_hexagram_in_raw(self, iching, user):
        result = iching.compute(user, seed=42)
        primary = result.raw["primary"]
        assert "number" in primary
        assert "chinese" in primary
        assert "english" in primary
        assert 1 <= primary["number"] <= 64

    def test_summary_contains_hexagram_name(self, iching, user):
        result = iching.compute(user, seed=42)
        primary = result.raw["primary"]
        assert primary["english"] in result.summary

    def test_no_birth_required(self):
        system = IChingSystem()
        assert system.requires_birth_date is False
        assert system.requires_birth_time is False

    def test_changing_lines_in_summary(self, iching, user):
        """If there are changing lines, they should appear in the summary."""
        for seed in range(100):
            result = iching.compute(user, seed=seed)
            if result.raw["changing"]:
                assert "Changing lines" in result.summary
                break
