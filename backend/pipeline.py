"""Core NLP pipeline: split → summarize → embed → cluster → cards → deck JSON."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import numpy as np

from models import Card, Deck, Paragraph, Stats, Topic

# 約 5k tokens 量級；中英混合保守上限
MAX_INPUT_CHARS = 50_000
EMBEDDING_DIM = 64

# 常見中英停用詞（精簡版）
_STOPWORDS = {
    "的",
    "了",
    "在",
    "是",
    "我",
    "有",
    "和",
    "就",
    "不",
    "人",
    "都",
    "一",
    "一個",
    "上",
    "也",
    "很",
    "到",
    "說",
    "要",
    "去",
    "你",
    "會",
    "著",
    "沒有",
    "看",
    "好",
    "自己",
    "這",
    "他",
    "她",
    "它",
    "們",
    "與",
    "及",
    "或",
    "而",
    "被",
    "把",
    "從",
    "對",
    "於",
    "為",
    "以",
    "等",
    "可以",
    "這個",
    "那個",
    "什麼",
    "如何",
    "以及",
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "to",
    "in",
    "on",
    "for",
    "is",
    "are",
    "was",
    "were",
    "be",
    "as",
    "by",
    "with",
    "that",
    "this",
    "it",
    "from",
    "at",
    "not",
}


def project_root() -> Path:
    """專案根目錄（backend/ 的上一層）。"""
    return Path(__file__).resolve().parent.parent


def deck_output_path() -> Path:
    return project_root() / "frontend" / "public" / "deck.json"


def split_paragraphs(text: str) -> list[str]:
    """依標題、空行、清單項目切分段落。"""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []

    lines = normalized.split("\n")
    chunks: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer
        joined = "\n".join(buffer).strip()
        if joined:
            chunks.append(joined)
        buffer = []

    heading_re = re.compile(r"^#{1,6}\s+\S")
    list_re = re.compile(r"^(\s*[-*+]|\s*\d+[.)])\s+\S")

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush()
            continue
        if heading_re.match(stripped) or list_re.match(line):
            flush()
            chunks.append(stripped)
            continue
        buffer.append(stripped)

    flush()

    # 合併過短的連續非標題碎片（避免切太碎），但保留清單/標題獨立
    if not chunks:
        return []

    return chunks


def _first_sentence(text: str, max_len: int = 60) -> str:
    cleaned = re.sub(r"\s+", " ", text.strip())
    # 去掉開頭 markdown 標記
    cleaned = re.sub(r"^#{1,6}\s+", "", cleaned)
    cleaned = re.sub(r"^([-*+]|\d+[.)])\s+", "", cleaned)

    # 以中文標點優先切句；英文句點需避免切斷檔名（如 deck.json）
    match = re.search(r".+?(?:[。！？!?]|[.](?!\w)|$)", cleaned)
    sentence = match.group(0).strip() if match else cleaned
    if len(sentence) > max_len:
        return sentence[: max_len - 1] + "…"
    return sentence or cleaned[:max_len]


def extract_keywords(text: str, max_keywords: int = 5) -> list[str]:
    """抽取 1–5 個關鍵詞（中英混合、頻率排序、deterministic）。"""
    cleaned = re.sub(r"^#{1,6}\s+", "", text.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"[`*_>\[\](){}|\\]", " ", cleaned)
    cleaned = re.sub(r"^([-*+]|\d+[.)])\s+", "", cleaned, flags=re.MULTILINE)

    scores: dict[str, float] = {}

    def add(token: str, weight: float = 1.0) -> None:
        tok = token.strip()
        if len(tok) < 2:
            return
        if tok.lower() in _STOPWORDS or tok in _STOPWORDS:
            return
        scores[tok] = scores.get(tok, 0.0) + weight

    # 標題整段加權
    for heading in re.findall(r"^#{1,6}\s+(.+)$", text, flags=re.MULTILINE):
        h = heading.strip()
        if 2 <= len(h) <= 20:
            add(h, 5.0)
        for part in re.findall(r"[\u4e00-\u9fff]{2,8}|[A-Za-z][A-Za-z0-9_-]{1,}", h):
            add(part if re.search(r"[\u4e00-\u9fff]", part) else part.lower(), 4.0)

    # 以標點切出較自然的中文短語
    for phrase in re.split(r"[，。！？、；：,.!?;:\s]+", cleaned):
        phrase = phrase.strip()
        if not phrase:
            continue
        zh_parts = re.findall(r"[\u4e00-\u9fff]{2,}", phrase)
        for zh in zh_parts:
            if len(zh) <= 8:
                add(zh, 2.5)
            else:
                # 長句：依常見虛詞粗切
                pieces = re.split(r"[的是了在與及和把被對從]", zh)
                for piece in pieces:
                    if 2 <= len(piece) <= 8:
                        add(piece, 2.0)
                add(zh[:4], 0.5)

    for en in re.findall(r"[A-Za-z][A-Za-z0-9_-]{1,}", cleaned):
        add(en.lower(), 2.0)

    for code in re.findall(r"[A-Za-z]*\d+[A-Za-z0-9_-]*", cleaned):
        if len(code) >= 2:
            add(code.lower(), 1.5)

    if not scores:
        fallback = _first_sentence(text, 20).strip("…。.!?,，、 ")
        return [fallback] if fallback else ["內容"]

    # 較長詞優先（同分時），再依字典序保證 deterministic
    ranked = sorted(
        scores.items(),
        key=lambda kv: (-kv[1], -len(kv[0]), kv[0]),
    )
    keywords: list[str] = []
    for word, _ in ranked:
        # 避免被更長詞完全覆蓋的短碎片重複佔位
        if any(word != k and word in k for k in keywords):
            continue
        keywords.append(word)
        if len(keywords) >= max_keywords:
            break
    return keywords[:max_keywords] or ["內容"]


def summarize_paragraph(text: str) -> tuple[str, list[str]]:
    summary = _first_sentence(text, 60)
    keywords = extract_keywords(text, 5)
    # 確保 1–5 個
    keywords = keywords[:5] or ["內容"]
    return summary, keywords


def _hash_to_index(token: str, dim: int) -> int:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % dim


def embed_texts(texts: list[str], dim: int = EMBEDDING_DIM) -> np.ndarray:
    """Deterministic hashing embedding（可替換為真實 embedding 模型）。"""
    matrix = np.zeros((len(texts), dim), dtype=np.float64)
    for i, text in enumerate(texts):
        tokens = re.findall(r"[\u4e00-\u9fff]+|[A-Za-z0-9_-]+", text.lower())
        if not tokens:
            tokens = ["empty"]
        for tok in tokens:
            idx = _hash_to_index(tok, dim)
            matrix[i, idx] += 1.0
            # 字元 bigram 補強中文語意
            for j in range(len(tok) - 1):
                bigram = tok[j : j + 2]
                bidx = _hash_to_index(f"bi:{bigram}", dim)
                matrix[i, bidx] += 0.5
        norm = np.linalg.norm(matrix[i])
        if norm > 0:
            matrix[i] /= norm
    return matrix


def cosine_similarity_matrix(vectors: np.ndarray) -> np.ndarray:
    return vectors @ vectors.T


def cluster_by_threshold(
    vectors: np.ndarray,
    threshold: float,
    max_topics: int,
) -> list[list[int]]:
    """
    閾值分群：依段落順序掃描，相似度 >= threshold 併入既有群，否則開新群。
    尊重 max_topics；超過時併入最相似群。至少 1 群。
    """
    n = vectors.shape[0]
    if n == 0:
        return []

    clusters: list[list[int]] = []
    centroids: list[np.ndarray] = []

    for i in range(n):
        vec = vectors[i]
        best_idx = -1
        best_sim = -1.0
        for c_idx, centroid in enumerate(centroids):
            sim = float(np.dot(vec, centroid))
            if sim > best_sim:
                best_sim = sim
                best_idx = c_idx

        if best_idx >= 0 and best_sim >= threshold:
            clusters[best_idx].append(i)
            members = clusters[best_idx]
            centroids[best_idx] = vectors[members].mean(axis=0)
            norm = np.linalg.norm(centroids[best_idx])
            if norm > 0:
                centroids[best_idx] /= norm
        elif len(clusters) < max_topics:
            clusters.append([i])
            centroids.append(vec.copy())
        else:
            # 已達上限，併入最相似群
            if best_idx < 0:
                best_idx = 0
            clusters[best_idx].append(i)
            members = clusters[best_idx]
            centroids[best_idx] = vectors[members].mean(axis=0)
            norm = np.linalg.norm(centroids[best_idx])
            if norm > 0:
                centroids[best_idx] /= norm

    # 依各群最小 sourceIndex 排序（deterministic）
    clusters.sort(key=lambda members: (min(members), members))
    return clusters


def topic_title_from_members(paragraphs: list[Paragraph], member_indices: list[int]) -> str:
    """從成員關鍵詞/摘要選最具代表性的標題。"""
    keyword_scores: dict[str, float] = {}
    for rank, idx in enumerate(member_indices):
        # 較早出現的段落權重略高
        position_boost = 1.0 + max(0, 3 - rank) * 0.1
        for kw_i, kw in enumerate(paragraphs[idx].keywords):
            keyword_scores[kw] = keyword_scores.get(kw, 0.0) + (
                (5 - kw_i) * position_boost
            )
        # 若原文是 markdown 標題，直接作為強候選
        raw = paragraphs[idx].text.strip()
        if re.match(r"^#{1,6}\s+\S", raw):
            title = re.sub(r"^#{1,6}\s+", "", raw.split("\n", 1)[0]).strip()
            if 2 <= len(title) <= 30:
                keyword_scores[title] = keyword_scores.get(title, 0.0) + 8.0

    if keyword_scores:
        ranked = sorted(
            keyword_scores.items(),
            key=lambda kv: (-kv[1], -len(kv[0]), kv[0]),
        )
        return ranked[0][0]

    return paragraphs[member_indices[0]].summary[:20] or "未命名主題"


def build_cards_for_topic(
    topic: Topic,
    paragraphs: list[Paragraph],
    max_bullets: int,
    card_id_start: int,
) -> list[Card]:
    """每主題 1 張卡；成員 > 8 拆成 2 張（上/下）。"""
    para_by_id = {p.id: p for p in paragraphs}
    members = [para_by_id[mid] for mid in topic.memberIds if mid in para_by_id]
    if not members:
        return [
            Card(
                id=f"c{card_id_start}",
                topicId=topic.id,
                title=topic.title,
                bullets=["（此主題目前沒有內容）"][:max_bullets],
            )
        ]

    def make_bullets(paras: list[Paragraph]) -> list[str]:
        bullets: list[str] = []
        for p in paras:
            if p.summary and p.summary not in bullets:
                bullets.append(p.summary)
            if len(bullets) >= max_bullets:
                break
        if len(bullets) < min(3, max_bullets):
            # 補關鍵詞資訊，朝目標 3–5 條
            for p in paras:
                kw_line = "關鍵詞：" + "、".join(p.keywords)
                if kw_line not in bullets:
                    bullets.append(kw_line)
                if len(bullets) >= min(3, max_bullets):
                    break
        if not bullets:
            bullets = [paras[0].text[:60] or "（無內容）"]
        return bullets[:max_bullets]

    cards: list[Card] = []
    if len(members) > 8:
        mid = (len(members) + 1) // 2
        parts = [members[:mid], members[mid:]]
        suffixes = ["（上）", "（下）"]
        for offset, (part, suffix) in enumerate(zip(parts, suffixes)):
            cards.append(
                Card(
                    id=f"c{card_id_start + offset}",
                    topicId=topic.id,
                    title=f"{topic.title}{suffix}",
                    bullets=make_bullets(part),
                )
            )
    else:
        cards.append(
            Card(
                id=f"c{card_id_start}",
                topicId=topic.id,
                title=topic.title,
                bullets=make_bullets(members),
            )
        )
    return cards


def build_deck(
    text: str,
    topic_threshold: float = 0.75,
    max_topics: int = 5,
    max_bullets: int = 5,
) -> tuple[Deck, dict[str, Any]]:
    """執行完整管線，回傳 Deck 與除錯資訊。"""
    if text is None or not str(text).strip():
        raise ValueError("輸入為空：請提供非空的純文字字串。")

    raw = str(text)
    if len(raw) > MAX_INPUT_CHARS:
        raise ValueError(
            f"輸入過長：目前上限為 {MAX_INPUT_CHARS} 字元，實際為 {len(raw)}。"
        )

    chunks = split_paragraphs(raw)
    if not chunks:
        raise ValueError("無法切分出任何段落：請確認輸入文字內容。")

    paragraphs: list[Paragraph] = []
    for i, chunk in enumerate(chunks):
        summary, keywords = summarize_paragraph(chunk)
        paragraphs.append(
            Paragraph(
                id=f"p{i + 1}",
                text=chunk,
                summary=summary,
                keywords=keywords,
                sourceIndex=i,
            )
        )

    embed_inputs = [f"{p.summary} {' '.join(p.keywords)} {p.text}" for p in paragraphs]
    vectors = embed_texts(embed_inputs)
    sim_matrix = cosine_similarity_matrix(vectors)
    clusters = cluster_by_threshold(vectors, topic_threshold, max_topics)
    if not clusters:
        clusters = [list(range(len(paragraphs)))]

    topics: list[Topic] = []
    for t_idx, member_indices in enumerate(clusters):
        member_ids = [paragraphs[i].id for i in sorted(member_indices)]
        title = topic_title_from_members(paragraphs, sorted(member_indices))
        topics.append(
            Topic(
                id=f"t{t_idx + 1}",
                title=title,
                memberIds=member_ids,
            )
        )

    # Topics 已依最小 sourceIndex 排序（cluster 階段）
    cards: list[Card] = []
    next_card_id = 1
    for topic in topics:
        new_cards = build_cards_for_topic(topic, paragraphs, max_bullets, next_card_id)
        cards.extend(new_cards)
        next_card_id += len(new_cards)

    stats = Stats(
        paragraphCount=len(paragraphs),
        topicCount=len(topics),
        cardCount=len(cards),
    )
    deck = Deck(paragraphs=paragraphs, topics=topics, cards=cards, stats=stats)

    debug_info: dict[str, Any] = {
        "topic_threshold": topic_threshold,
        "max_topics": max_topics,
        "max_bullets": max_bullets,
        "cluster_sizes": [len(c) for c in clusters],
        "similarity_sample": [
            [round(float(sim_matrix[i, j]), 4) for j in range(min(5, len(paragraphs)))]
            for i in range(min(5, len(paragraphs)))
        ],
    }
    return deck, debug_info


def deck_to_json_dict(deck: Deck) -> dict[str, Any]:
    """轉成可寫入 JSON 的 dict（保留前端 camelCase 欄位）。"""
    return deck.model_dump(mode="python")


def write_deck_json(deck: Deck, path: Path | None = None) -> Path:
    """寫入 frontend/public/deck.json（UTF-8 無 BOM，縮排 2，sort_keys）。"""
    output = path or deck_output_path()
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = deck_to_json_dict(deck)
    with output.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    return output.resolve()


def process_text(
    text: str,
    topic_threshold: float = 0.75,
    max_topics: int = 5,
    max_bullets: int = 5,
) -> tuple[Deck, Path, dict[str, Any]]:
    """建 deck 並寫入固定路徑。"""
    deck, debug_info = build_deck(
        text=text,
        topic_threshold=topic_threshold,
        max_topics=max_topics,
        max_bullets=max_bullets,
    )
    path = write_deck_json(deck)
    debug_info["output_path"] = str(path)
    return deck, path, debug_info
