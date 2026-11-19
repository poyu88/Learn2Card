
import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# 1. 指定原本的 .env 檔案
ENV_PATH = Path(
    r"C:\Users\billh\python_test\Learn2Card\.env"
)

# 2. 自動讀取 LINE 設定
def load_env(path):
    if not path.is_file():
        raise FileNotFoundError(f"找不到設定檔：{path}")

    settings = {}

    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        settings[key.strip()] = value.strip().strip('"').strip("'")

    return settings


env = load_env(ENV_PATH)

LINE_CHANNEL_ACCESS_TOKEN = env.get(
    "LINE_CHANNEL_ACCESS_TOKEN", ""
)
LINE_USER_ID = env.get("LINE_USER_ID", "")

# 3. 檢查設定
if not LINE_CHANNEL_ACCESS_TOKEN:
    raise SystemExit("錯誤：找不到 LINE_CHANNEL_ACCESS_TOKEN")

if not LINE_USER_ID:
    raise SystemExit("錯誤：找不到 LINE_USER_ID")

if not (
    len(LINE_USER_ID) == 33
    and LINE_USER_ID.startswith("U")
):
    raise SystemExit("錯誤：LINE_USER_ID 格式不正確")

# 4. 準備 LINE 測試訊息
payload = {
    "to": LINE_USER_ID,
    "messages": [
        {
            "type": "text",
            "text": (
                "✅ LINE 通知測試成功！\n"
                "這則訊息由 Python 自動發送。\n"
                "Cursor AI 通知系統測試中。"
            )
        }
    ]
}

# 5. 發送到 LINE Messaging API
request = Request(
    url="https://api.line.me/v2/bot/message/push",
    data=json.dumps(payload).encode("utf-8"),
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    },
    method="POST"
)

print("正在發送 LINE 測試訊息...")

try:
    with urlopen(request, timeout=15) as response:
        print(f"HTTP 狀態碼：{response.status}")
        print("✅ LINE API 已接受訊息，請查看手機！")

except HTTPError as error:
    print(f"❌ LINE API 錯誤：HTTP {error.code}")
    print(error.read().decode("utf-8"))

except URLError as error:
    print(f"❌ 網路連線錯誤：{error.reason}")
