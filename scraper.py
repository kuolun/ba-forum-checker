"""論壇爬蟲模組：抓取論壇頁面 HTML，支援 goto 直達與 PostBack 翻頁。"""

import time  # 重試間隔計時
import logging  # 日誌記錄
from urllib.parse import urlencode, urljoin  # URL 參數處理

import requests  # HTTP 請求庫

from config import BASE_URL  # 論壇根網址
from parser import extract_postback_data, has_next_page  # 解析翻頁資料

# 設定日誌
logger = logging.getLogger(__name__)

# === 預設值 ===
MAX_RETRIES = 3  # 最大重試次數
TIMEOUT = 30  # 請求超時秒數
RETRY_DELAY = 5  # 重試間隔秒數
MAX_PAGINATION_LOOPS = 10  # 最大翻頁循環次數（防止無限迴圈）


def create_session() -> requests.Session:
    """建立 HTTP Session，設定共用的 headers 與 cookie 保持。

    使用 Session 可以自動管理 cookie（ASP.NET 需要 session cookie），
    並重複使用 TCP 連線提升效率。

    Returns:
        設定好 headers 的 requests.Session 物件
    """
    session = requests.Session()
    # 設定瀏覽器 User-Agent，避免被伺服器阻擋
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    })
    return session


def fetch_page(session: requests.Session, url: str) -> str:
    """用 GET 請求抓取指定 URL 的頁面 HTML，含重試機制。

    Args:
        session: HTTP Session 物件
        url: 要抓取的完整 URL

    Returns:
        頁面 HTML 字串

    Raises:
        requests.RequestException: 重試耗盡後仍然失敗
    """
    last_error = None  # 記錄最後一次的錯誤

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info("GET %s（第 %d 次嘗試）", url, attempt)
            response = session.get(url, timeout=TIMEOUT)
            response.raise_for_status()  # 非 2xx 狀態碼拋出例外
            response.encoding = "utf-8"  # 確保中文正確解碼
            return response.text
        except requests.RequestException as e:
            last_error = e
            logger.warning("第 %d 次請求失敗：%s", attempt, e)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)  # 等待後重試

    # 所有重試都失敗，拋出最後的錯誤
    raise last_error


def fetch_search_page(session: requests.Session, path: str) -> str:
    """抓取作者搜尋頁的第一頁（最新貼文）。

    搜尋頁依時間倒序排列，第一頁就是最新的貼文，
    不需要翻到最後一頁。

    Args:
        session: HTTP Session 物件
        path: 搜尋頁路徑（如 /forumsearch.aspx?author=author_a）

    Returns:
        頁面 HTML 字串
    """
    # 組裝完整 URL 並 GET 第一頁
    url = f"{BASE_URL}{path}"
    return fetch_page(session, url)


def fetch_page_by_goto(session: requests.Session, path: str, goto_id: int) -> str:
    """用 ?goto={id} 參數直達包含指定貼文的頁面。

    適用於已知貼文 ID 的情況，直接跳到該貼文所在頁面。

    Args:
        session: HTTP Session 物件
        path: 討論串路徑（如 /Forum/128/某討論串.aspx）
        goto_id: 目標貼文 ID

    Returns:
        頁面 HTML 字串
    """
    # 組裝完整 URL 並加上 goto 參數
    url = f"{BASE_URL}{path}?goto={goto_id}"
    return fetch_page(session, url)


def fetch_last_page(session: requests.Session, path: str,
                    user_filter: str | None = None) -> str:
    """用 ASP.NET PostBack 機制翻到討論串的最後一頁。

    流程：GET 第 1 頁 → 提取表單資料 → POST 翻到最後頁
    → 重複直到無更多頁面。

    Args:
        session: HTTP Session 物件
        path: 討論串路徑
        user_filter: 選填的使用者過濾參數（帳號名稱）

    Returns:
        最後一頁的 HTML 字串
    """
    # 組裝第一頁 URL
    url = f"{BASE_URL}{path}"
    if user_filter:
        url += f"?user={user_filter}"

    # GET 第一頁
    html = fetch_page(session, url)

    # 反覆翻頁直到最後一頁
    for _ in range(MAX_PAGINATION_LOOPS):
        # 檢查是否還有下一頁
        if not has_next_page(html):
            break  # 已到最後一頁

        # 提取 PostBack 翻頁資料
        postback_data = extract_postback_data(html)
        if not postback_data:
            break  # 無法提取翻頁資料，當作最後一頁

        # POST 翻到最後一頁
        logger.info("PostBack 翻頁：%s", postback_data["__EVENTTARGET"])
        html = _post_page(session, url, postback_data)

    return html


def _post_page(session: requests.Session, url: str, data: dict) -> str:
    """用 POST 請求提交 ASP.NET 表單資料，含重試機制。

    Args:
        session: HTTP Session 物件
        url: 表單提交的目標 URL
        data: POST 表單資料（含 __VIEWSTATE 等隱藏欄位）

    Returns:
        回應頁面的 HTML 字串

    Raises:
        requests.RequestException: 重試耗盡後仍然失敗
    """
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info("POST %s（第 %d 次嘗試）", url, attempt)
            response = session.post(url, data=data, timeout=TIMEOUT)
            response.raise_for_status()
            response.encoding = "utf-8"
            return response.text
        except requests.RequestException as e:
            last_error = e
            logger.warning("POST 第 %d 次請求失敗：%s", attempt, e)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

    raise last_error
