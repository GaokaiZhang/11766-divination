"""
Build (or rebuild) the ChromaDB vector index from local JSON data files.
Run directly:  python -m backend.rag.indexer
"""
import json
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

DATA_DIR = Path(__file__).parent.parent.parent / "data"
CHROMA_DIR = Path(__file__).parent.parent.parent / ".chroma_db"

from typing import Optional
_client: Optional[chromadb.PersistentClient] = None


def get_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return _client


def get_collection(name: str = "divination") -> chromadb.Collection:
    return get_client().get_or_create_collection(
        name, embedding_function=DefaultEmbeddingFunction()
    )


# ---------------------------------------------------------------------------
# Tarot indexing
# ---------------------------------------------------------------------------

def _index_tarot(col: chromadb.Collection) -> int:
    total = 0

    # Card meanings (78 cards x 2 orientations)
    path = DATA_DIR / "tarot" / "cards.json"
    with open(path) as f:
        cards: list[dict] = json.load(f)["cards"]

    docs, ids, metas = [], [], []
    for card in cards:
        for orientation in ("upright", "reversed"):
            entry = card.get(orientation, {})
            meaning = entry.get("meaning", "")
            keywords = ", ".join(entry.get("keywords", []))
            text = (
                f"{card['name']} ({orientation}): {meaning} "
                f"Keywords: {keywords}"
            ).strip()
            docs.append(text)
            ids.append(f"tarot|{card['id']}|{orientation}")
            metas.append({"system": "tarot", "card": card["name"],
                          "orientation": orientation})

    col.upsert(documents=docs, ids=ids, metadatas=metas)
    total += len(docs)

    # Cross-card interaction patterns
    for fname in ("interactions.json", "spreads.json"):
        path = DATA_DIR / "tarot" / fname
        if not path.exists():
            continue
        with open(path) as f:
            data = json.load(f)
        d, i, m = [], [], []
        for entry in data.get("entries", []):
            d.append(entry["text"])
            i.append(f"tarot|{fname.removesuffix('.json')}|{entry['id']}")
            m.append({"system": "tarot", **entry.get("meta", {})})
        col.upsert(documents=d, ids=i, metadatas=m)
        total += len(d)

    return total


# ---------------------------------------------------------------------------
# Bazi indexing
# ---------------------------------------------------------------------------

def _index_bazi(col: chromadb.Collection) -> int:
    total = 0
    for fname in ("stems.json", "branches.json", "combinations.json",
                   "ten_gods.json", "hidden_stems.json", "branch_relationships.json"):
        path = DATA_DIR / "bazi" / fname
        if not path.exists():
            continue
        with open(path) as f:
            data = json.load(f)

        docs, ids, metas = [], [], []
        for entry in data.get("entries", []):
            docs.append(entry["text"])
            ids.append(f"bazi|{fname.removesuffix('.json')}|{entry['id']}")
            metas.append({"system": "bazi", **entry.get("meta", {})})

        col.upsert(documents=docs, ids=ids, metadatas=metas)
        total += len(docs)
    return total


# ---------------------------------------------------------------------------
# I Ching indexing
# ---------------------------------------------------------------------------

def _index_iching(col: chromadb.Collection) -> int:
    path = DATA_DIR / "iching" / "hexagrams.json"
    if not path.exists():
        return 0
    with open(path) as f:
        data = json.load(f)

    docs, ids, metas = [], [], []
    for h in data["hexagrams"]:
        num = h["number"]
        name = f"{h['chinese']} ({h['pinyin']}) — {h['english']}"

        # Overview document (1 per hexagram) — combines the hexagram
        # identity, trigram composition, and judgment/image texts into one
        # semantically rich document that anchors hexagram-level retrieval.
        jtext = h.get("judgment", {}).get("text", "")
        itext = h.get("image", {}).get("text", "")
        trigrams = (
            f"Upper: {h.get('upper_trigram', {}).get('symbolic', '')} "
            f"({h.get('upper_trigram', {}).get('nature', '')}), "
            f"Lower: {h.get('lower_trigram', {}).get('symbolic', '')} "
            f"({h.get('lower_trigram', {}).get('nature', '')})"
        )
        overview = (
            f"Hexagram {num} {name}. "
            f"Trigrams: {trigrams}. "
            f"Judgment: {jtext} "
            f"Image: {itext}"
        )
        docs.append(overview)
        ids.append(f"iching|overview|{num}")
        metas.append({"system": "iching", "hexagram": num,
                      "type": "overview"})

        # Symbolic description (1 doc per hexagram)
        if h.get("symbolic_description"):
            docs.append(
                f"Hexagram {num} {name}: {h['symbolic_description']}"
            )
            ids.append(f"iching|symbolic|{num}")
            metas.append({"system": "iching", "hexagram": num,
                          "type": "symbolic"})

        # Judgment with commentary (1 doc per hexagram)
        jcomm = h.get("judgment", {}).get("commentary", "")
        if jtext:
            docs.append(
                f"Hexagram {num} {name} — Judgment: {jtext} "
                f"Commentary: {jcomm}"
            )
            ids.append(f"iching|judgment|{num}")
            metas.append({"system": "iching", "hexagram": num,
                          "type": "judgment"})

        # Image with commentary (1 doc per hexagram)
        icomm = h.get("image", {}).get("commentary", "")
        if itext:
            docs.append(
                f"Hexagram {num} {name} — Image: {itext} "
                f"Commentary: {icomm}"
            )
            ids.append(f"iching|image|{num}")
            metas.append({"system": "iching", "hexagram": num,
                          "type": "image"})

        # Individual line texts (6 docs per hexagram)
        for line_num in ("1", "2", "3", "4", "5", "6"):
            line = h.get("lines", {}).get(line_num, {})
            ltext = line.get("text", "")
            lcomm = line.get("commentary", "")
            if ltext:
                docs.append(
                    f"Hexagram {num} {name} — Line {line_num}: {ltext} "
                    f"Commentary: {lcomm}"
                )
                ids.append(f"iching|line|{num}_{line_num}")
                metas.append({"system": "iching", "hexagram": num,
                              "type": "line", "line": int(line_num)})

    col.upsert(documents=docs, ids=ids, metadatas=metas)
    return len(docs)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_index(verbose: bool = True) -> None:
    col = get_collection()
    n_tarot = _index_tarot(col)
    n_bazi = _index_bazi(col)
    n_iching = _index_iching(col)
    if verbose:
        print(f"Index built — tarot: {n_tarot}, bazi: {n_bazi}, "
              f"iching: {n_iching} docs (total: {n_tarot + n_bazi + n_iching})")


if __name__ == "__main__":
    build_index()
