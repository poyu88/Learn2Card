# Backend - Python 後端處理（Agent A）

## 目前狀態

已實作 FastAPI HTTP API 與核心 NLP 管線：
- 段落切分（標題 / 空行 / 清單）
- 摘要與關鍵詞抽取
- Deterministic hashing embedding + 閾值分群
- 卡片草稿生成與統計
- 固定輸出 `frontend/public/deck.json`（UTF-8）

## 啟動方式

```bash
cd backend
uv sync
uv run uvicorn api:app --reload --host 127.0.0.1 --port 8000
```

## API

- `GET /health`：健康檢查
- `POST /api/process`：處理純文字並寫入 deck.json

### Request 範例

```json
{
  "text": "# 標題\n\n這是一段內容。\n\n## 另一段\n\n更多說明。",
  "topic_threshold": 0.75,
  "max_topics": 5,
  "max_bullets": 5,
  "debug": false
}
```

### curl 範例

```bash
curl -s -X POST http://127.0.0.1:8000/api/process \
  -H "Content-Type: application/json" \
  -d '{"text":"# 目標\n\n把長文變成卡片。\n\n# 流程\n\n切段、摘要、分群、出卡。","debug":true}'
```

## 檔案結構

- `api.py`：FastAPI app（CORS、`/api/process`）
- `pipeline.py`：核心處理管線
- `models.py`：Pydantic Request/Response 與 Deck schema
- `main.py`：入口說明

詳細規格請參考 `docs/prd/agent-a.md` 與 `docs/spec/technical-spec.md`。
