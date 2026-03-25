from datetime import datetime

from .base import DivinationSystem, DivinationResult, UserBirthInfo

# Ten Heavenly Stems
STEMS = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
STEM_NAMES = ["Jiǎ", "Yǐ", "Bǐng", "Dīng", "Wù", "Jǐ", "Gēng", "Xīn", "Rén", "Guǐ"]
STEM_ELEMENTS = [
    "Yang Wood", "Yin Wood", "Yang Fire", "Yin Fire", "Yang Earth",
    "Yin Earth", "Yang Metal", "Yin Metal", "Yang Water", "Yin Water",
]

# Twelve Earthly Branches
BRANCHES = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
BRANCH_NAMES = ["Zǐ", "Chǒu", "Yín", "Mǎo", "Chén", "Sì", "Wǔ", "Wèi", "Shēn", "Yǒu", "Xū", "Hài"]
BRANCH_ELEMENTS = [
    "Yang Water", "Yin Earth", "Yang Wood", "Yin Wood", "Yang Earth", "Yin Fire",
    "Yang Fire", "Yin Earth", "Yang Metal", "Yin Metal", "Yang Earth", "Yin Water",
]

# Coarse birth-time → branch index mapping (for users who don't know exact hour)
TIME_OF_DAY_MAP = {
    "midnight": 0,   # 子 23:00–01:00
    "night": 11,     # 亥 21:00–23:00
    "morning": 2,    # 寅 03:00–05:00
    "dawn": 1,       # 丑 01:00–03:00
    "afternoon": 7,  # 未 13:00–15:00
    "evening": 9,    # 酉 17:00–19:00
}


class BaziSystem(DivinationSystem):
    name = "bazi"
    requires_birth_date = True
    requires_birth_time = True  # hour pillar needs birth time

    def _parse_dt(self, user_info: UserBirthInfo) -> datetime:
        if user_info.birth_time:
            return datetime.strptime(
                f"{user_info.birth_date} {user_info.birth_time}", "%Y-%m-%d %H:%M"
            )
        # Fallback to noon if time was not provided (only year/month/day pillars reliable)
        return datetime.strptime(user_info.birth_date, "%Y-%m-%d").replace(hour=12)

    def compute(self, user_info: UserBirthInfo, **kwargs) -> DivinationResult:
        try:
            import cnlunar
        except ImportError:
            raise RuntimeError(
                "cnlunar is not installed. Run: pip install cnlunar"
            )

        dt = self._parse_dt(user_info)
        lunar = cnlunar.Lunar(dt, godType="8char")

        # Extract the four pillar stem/branch indices from cnlunar attributes
        hour_char = lunar.twohour8Char  # e.g. "丁未"
        hour_stem_idx = STEMS.index(hour_char[0])
        hour_branch_idx = BRANCHES.index(hour_char[1])
        eight_char = [
            (lunar.yearHeavenNum, lunar.yearEarthNum),
            (lunar.monthHeavenNum, lunar.monthEarthNum),
            (lunar.dayHeavenNum, lunar.dayEarthNum),
            (hour_stem_idx, hour_branch_idx),
        ]

        pillar_labels = ["Year", "Month", "Day", "Hour"]
        lines, symbols = [], []

        for label, (s_idx, b_idx) in zip(pillar_labels, eight_char):
            stem_elem = STEM_ELEMENTS[s_idx]
            branch_elem = BRANCH_ELEMENTS[b_idx]
            lines.append(
                f"{label} Pillar: {STEM_NAMES[s_idx]} {STEMS[s_idx]} ({stem_elem})"
                f" / {BRANCH_NAMES[b_idx]} {BRANCHES[b_idx]} ({branch_elem})"
            )
            symbols += [stem_elem, branch_elem, f"{label} pillar"]

        # Day Stem = self element — highlighted as primary interpretive lens
        day_stem_elem = STEM_ELEMENTS[eight_char[2][0]]
        lines.append(f"\nDay Master (self-element): {day_stem_elem}")
        symbols.append(f"Day Master {day_stem_elem}")

        hour_note = "" if user_info.birth_time else " (Hour Pillar estimated — birth time not provided)"
        summary = "\n".join(lines) + hour_note

        return DivinationResult(
            system="bazi",
            raw={
                "eight_char": eight_char,
                "pillar_labels": pillar_labels,
                "birth_dt": dt.isoformat(),
                "hour_estimated": not bool(user_info.birth_time),
            },
            summary=summary,
            symbols=list(dict.fromkeys(symbols)),
        )

    def clarification_question(self, missing: list[str]) -> str:
        if "birth_date" in missing:
            return (
                "I'd need your birth date to calculate your Four Pillars. "
                "Do you know when you were born?"
            )
        if "birth_time" in missing:
            return (
                "For a complete Bazi reading, your birth hour makes a real difference — "
                "it determines your Hour Pillar and refines the whole picture. "
                "Do you know roughly what time of day you were born? "
                "Even morning, afternoon, evening, or night works as a starting point."
            )
        return ""
