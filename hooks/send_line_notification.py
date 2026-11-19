#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent 終止時透過 LINE Messaging API 發送通知
用於 Cursor stop hook
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict

LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"

STATUS_MESSAGES = {
    "completed": "✅ Cursor Agent 已完成任務。",
    "aborted": "⏹️ Cursor Agent 已被中止。",
    "error": "❌ Cursor Agent 因錯誤而終止。",
}


def write_output(payload: Dict[str, Any]) -> None:
    """以 UTF-8 輸出 JSON 到 stdout（stop hook 無需 follow-up 時輸出空物件）。"""
    output = json.dumps(payload, ensure_ascii=False)
    sys.stdout.buffer.write(output.encode("utf-8"))
    sys.stdout.buffer.flush()


def load_dotenv(dotenv_path: Path) -> None:
    """簡易讀取 .env（不依賴 python-dotenv）。"""
    if not dotenv_path.is_file():
        return

    raw = dotenv_path.read_bytes().decode("utf-8")
    for line in raw.splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def resolve_dotenv_path() -> Path:
    """優先使用專案根目錄（cwd）的 .env，否則退回腳本上一層目錄。"""
    cwd_env = Path.cwd() / ".env"
    if cwd_env.is_file():
        return cwd_env
    return Path(__file__).resolve().parent.parent / ".env"


def build_message(data: Dict[str, Any]) -> str:
    """依 status 組出 LINE 通知內容。"""
    status = str(data.get("status", "") or "").strip().lower()
    base = STATUS_MESSAGES.get(status, f"ℹ️ Cursor Agent 已結束（狀態：{status or 'unknown'}）。")

    details: list[str] = [base]
    model = data.get("model")
    if model:
        details.append(f"模型：{model}")
    conversation_id = data.get("conversation_id")
    if conversation_id:
        details.append(f"對話 ID：{conversation_id}")
    loop_count = data.get("loop_count")
    if loop_count is not None:
        details.append(f"loop_count：{loop_count}")
    return "\n".join(details)


def send_line_push(token: str, user_id: str, text: str) -> None:
    """使用 LINE Messaging API 推播文字訊息。"""
    body = json.dumps(
        {
            "to": user_id,
            "messages": [{"type": "text", "text": text}],
        },
        ensure_ascii=False,
    ).encode("utf-8")

    request = urllib.request.Request(
        LINE_PUSH_URL,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )

    with urllib.request.urlopen(request, timeout=15) as response:
        response.read()


def main() -> None:
    try:
        input_data = sys.stdin.buffer.read().decode("utf-8")
        try:
            data: Dict[str, Any] = json.loads(input_data) if input_data.strip() else {}
        except json.JSONDecodeError:
            write_output({})
            return

        load_dotenv(resolve_dotenv_path())
        token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
        user_id = os.environ.get("LINE_USER_ID", "").strip()

        # 設定不完整或仍為範例佔位符時略過發送，不阻斷 Agent 結束流程
        if (
            not token
            or not user_id
            or token.startswith("your_")
            or user_id.startswith("your_")
        ):
            write_output({})
            return

        message = build_message(data)
        send_line_push(token, user_id, message)
        write_output({})
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        write_output({})
    except Exception:
        write_output({})


if __name__ == "__main__":
    main()
