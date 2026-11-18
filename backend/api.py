"""FastAPI HTTP API for Learn2Cards backend pipeline."""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from models import ErrorResponse, ProcessRequest, ProcessResponse
from pipeline import process_text

logger = logging.getLogger("learn2cards.api")

app = FastAPI(
    title="Learn2Cards Backend",
    description="文件歸納切卡機 · NLP/LLM 管線 API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _format_validation_message(exc: RequestValidationError) -> tuple[str, list[str]]:
    messages: list[str] = []
    for err in exc.errors():
        loc_parts = [str(x) for x in err.get("loc", ()) if x != "body"]
        loc = ".".join(loc_parts)
        msg = err.get("msg", "參數錯誤")
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, ") :]
        if "text" in loc_parts and (
            "empty" in msg.lower()
            or "輸入為空" in msg
            or "blank" in msg.lower()
            or "至少" in msg
            or "field required" in msg.lower()
        ):
            msg = "輸入為空：請提供非空的純文字字串。"
            messages.append(msg)
            continue
        messages.append(f"{loc}: {msg}" if loc else msg)

    message = messages[0] if messages else "請求參數錯誤。"
    if any("輸入為空" in m for m in messages):
        message = "輸入為空：請提供非空的純文字字串。"
    return message, messages


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/api/process",
    response_model=ProcessResponse,
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def process(request: ProcessRequest) -> ProcessResponse:
    """接收純文字，執行切段→摘要→分群→出卡，並寫入 frontend/public/deck.json。"""
    try:
        deck, output_path, debug_info = process_text(
            text=request.text,
            topic_threshold=request.topic_threshold,
            max_topics=request.max_topics,
            max_bullets=request.max_bullets,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"success": False, "message": str(exc)},
        ) from exc
    except Exception as exc:  # noqa: BLE001 — 轉成明確 500
        logger.exception("處理管線發生未預期錯誤")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "message": "內部錯誤：處理失敗，請稍後再試。",
                "detail": str(exc),
            },
        ) from exc

    message = (
        f"已成功輸出到：{output_path}\n"
        f"  - 段落數：{deck.stats.paragraphCount}\n"
        f"  - 主題數：{deck.stats.topicCount}\n"
        f"  - 卡片數：{deck.stats.cardCount}"
    )
    return ProcessResponse(
        success=True,
        message=message,
        output_path=str(output_path),
        stats=deck.stats,
        deck=deck,
        debug_info=debug_info if request.debug else None,
    )


@app.exception_handler(RequestValidationError)
async def fastapi_validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    message, messages = _format_validation_message(exc)
    return JSONResponse(
        status_code=400,
        content={"success": False, "message": message, "detail": messages},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    """統一錯誤回應格式。"""
    if isinstance(exc.detail, dict):
        body = exc.detail
        if "success" not in body:
            body = {"success": False, **body}
        return JSONResponse(status_code=exc.status_code, content=body)
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "message": str(exc.detail)},
    )
