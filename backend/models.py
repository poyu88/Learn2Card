"""Pydantic models for deck schema and API request/response."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class Paragraph(BaseModel):
    id: str
    text: str
    summary: str
    keywords: list[str]
    sourceIndex: int


class Topic(BaseModel):
    id: str
    title: str
    memberIds: list[str]


class Card(BaseModel):
    id: str
    topicId: str
    title: str
    bullets: list[str]


class Stats(BaseModel):
    paragraphCount: int
    topicCount: int
    cardCount: int


class Deck(BaseModel):
    paragraphs: list[Paragraph]
    topics: list[Topic]
    cards: list[Card]
    stats: Stats


class ProcessRequest(BaseModel):
    text: str = Field(..., description="輸入的純文字字串（必填）")
    topic_threshold: float = Field(
        0.75, ge=0.0, le=1.0, description="分群相似度閾值"
    )
    max_topics: int = Field(5, ge=1, le=20, description="最大主題數")
    max_bullets: int = Field(5, ge=1, le=5, description="每卡摘要數上限")
    debug: bool = Field(False, description="除錯模式")

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        if value is None or not str(value).strip():
            raise ValueError("輸入為空：請提供非空的純文字字串。")
        return value


class ProcessResponse(BaseModel):
    success: bool
    message: str
    output_path: str | None = None
    stats: Stats | None = None
    deck: Deck | None = None
    debug_info: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    success: bool = False
    message: str
    detail: str | None = None
