from .tarot import TarotSystem
from .bazi import BaziSystem
from .iching import IChingSystem
from .base import DivinationSystem, DivinationResult, UserBirthInfo

SYSTEMS: dict[str, DivinationSystem] = {
    "tarot": TarotSystem(),
    "bazi": BaziSystem(),
    "iching": IChingSystem(),
}

__all__ = ["TarotSystem", "BaziSystem", "IChingSystem", "DivinationSystem",
           "DivinationResult", "UserBirthInfo", "SYSTEMS"]
