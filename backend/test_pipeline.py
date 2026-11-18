"""簡易管線回歸測試：uv run python test_pipeline.py"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from pipeline import MAX_INPUT_CHARS, build_deck, write_deck_json


SAMPLE = """# 專案目標

專案目標是把長文轉成一疊可翻閱的卡片，方便快速掌握重點。

# 介面布局

畫面包含標題列、左側統計與主題列表，以及右側卡片檢視區。

## 互動邏輯

卡片需要支援上一張與下一張按鈕，並根據主題切換可見卡片。

未來會改成讀取 deck.json。
"""


def test_build_deck_shape() -> None:
    deck, _ = build_deck(SAMPLE)
    assert deck.stats.paragraphCount == len(deck.paragraphs)
    assert deck.stats.topicCount == len(deck.topics)
    assert deck.stats.cardCount == len(deck.cards)
    assert deck.stats.topicCount >= 1
    assert deck.stats.topicCount <= 5
    for p in deck.paragraphs:
        assert p.id.startswith("p")
        assert 1 <= len(p.keywords) <= 5
        assert len(p.summary) <= 61
    for t in deck.topics:
        assert t.id.startswith("t")
        assert all(mid.startswith("p") for mid in t.memberIds)
    for c in deck.cards:
        assert c.id.startswith("c")
        assert 1 <= len(c.bullets) <= 5
        assert any(t.id == c.topicId for t in deck.topics)


def test_deterministic() -> None:
    d1, _ = build_deck(SAMPLE)
    d2, _ = build_deck(SAMPLE)
    assert d1.model_dump() == d2.model_dump()


def test_empty_and_long() -> None:
    try:
        build_deck("   ")
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "輸入為空" in str(exc)

    try:
        build_deck("x" * (MAX_INPUT_CHARS + 1))
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "輸入過長" in str(exc)


def test_write_utf8_no_bom() -> None:
    deck, _ = build_deck(SAMPLE)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "deck.json"
        write_deck_json(deck, path)
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")
        data = json.loads(raw.decode("utf-8"))
        assert data["stats"]["paragraphCount"] == deck.stats.paragraphCount


def test_split_card_when_many_members() -> None:
    # 每段一段落；低閾值 + max_topics=1 併成單一主題後應拆成上下兩卡
    lines = [f"這是第 {i} 段內容，用來測試拆卡與分群邏輯。" for i in range(10)]
    deck, _ = build_deck("\n\n".join(lines), topic_threshold=0.0, max_topics=1)
    assert deck.stats.topicCount == 1
    assert deck.stats.paragraphCount == 10
    assert deck.stats.cardCount == 2
    assert deck.cards[0].title.endswith("（上）")
    assert deck.cards[1].title.endswith("（下）")


if __name__ == "__main__":
    test_build_deck_shape()
    test_deterministic()
    test_empty_and_long()
    test_write_utf8_no_bom()
    test_split_card_when_many_members()
    print("all tests passed")
