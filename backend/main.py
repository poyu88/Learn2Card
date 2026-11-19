"""Backend entry point（管線可由 api.py 以 HTTP 呼叫）。"""


def main() -> None:
    print("Learn2Cards backend")
    print("請以 FastAPI 啟動：uv run uvicorn api:app --reload --host 127.0.0.1 --port 8000")
    print("API：POST /api/process")


if __name__ == "__main__":
    main()
