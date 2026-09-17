"""設定模組：環境變數讀取、監控目標定義、常數設定。"""

import os  # 作業系統介面，用於讀取環境變數
from urllib.parse import quote  # URL 參數編碼（作者名可能含非 ASCII 字元）
from dotenv import load_dotenv  # 從 .env 檔載入環境變數
from zoneinfo import ZoneInfo  # Python 3.9+ 內建時區支援

# 載入 .env 檔案中的環境變數
load_dotenv()

# === Gmail 寄信設定 ===
# 寄件者 Email（需搭配 App Password）
GMAIL_FROM = os.getenv("GMAIL_FROM", "")
# 收件者 Email
GMAIL_TO = os.getenv("GMAIL_TO", "")
# Gmail 應用程式專用密碼（不可寫死在程式碼中）
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
# Email 主旨前綴（方便收件端設過濾規則）
EMAIL_SUBJECT_PREFIX = os.getenv("EMAIL_SUBJECT_PREFIX", "[論壇]")

# === 論壇基礎設定 ===
# 論壇網站根網址，例如 https://forum.example.com（結尾不要加斜線）
BASE_URL = os.getenv("FORUM_BASE_URL", "").rstrip("/")

# === 監控目標清單 ===
# 監控的作者帳號，以逗號分隔，例如 WATCH_AUTHORS=author_a,author_b
WATCH_AUTHORS = [
    name.strip()
    for name in os.getenv("WATCH_AUTHORS", "").split(",")
    if name.strip()
]


def build_targets(authors: list[str]) -> list[dict]:
    """依作者清單組出監控目標設定。

    每個目標包含：name（帳號名）、path（作者搜尋頁路徑）、strategy（爬蟲策略）。

    Args:
        authors: 作者帳號名稱列表

    Returns:
        監控目標字典列表
    """
    return [
        {
            "name": author,  # 帳號名稱
            # 作者搜尋頁（追蹤該作者所有討論串），非 ASCII 帳號需 URL 編碼
            "path": f"/forumsearch.aspx?author={quote(author)}",
            "strategy": "author_search",  # 使用搜尋頁抓取最新貼文
        }
        for author in authors
    ]


# 由環境變數展開的監控目標
TARGETS = build_targets(WATCH_AUTHORS)

# === 排程設定 ===
# 檢查間隔（秒），預設 10 分鐘
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "600"))

# === 狀態檔案路徑 ===
# 記錄已發送通知的貼文 ID
STATE_FILE = os.getenv("STATE_FILE", "state.json")

# === 時區設定 ===
# 台灣時區，用於顯示時間
TZ = ZoneInfo("Asia/Taipei")
