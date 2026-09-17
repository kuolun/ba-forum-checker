"""HTML 解析模組：從論壇頁面提取留言資料。"""

import re  # 正則表達式，用於提取 goto ID
from dataclasses import dataclass  # 資料類別，結構化留言資料
from datetime import datetime, timezone  # 日期時間處理
from bs4 import BeautifulSoup  # HTML 解析器

from config import TZ  # 台灣時區設定


@dataclass
class ForumPost:
    """論壇貼文資料結構。"""
    username: str  # 發文者帳號名稱
    timestamp: datetime  # 發文時間（台灣時區）
    goto_id: int  # 貼文唯一 ID（用於 ?goto= 連結）
    content_html: str  # 貼文內容（保留 HTML 格式，含圖片標籤）
    permalink: str  # 貼文永久連結
    thread_title: str = ""  # 所屬討論串標題（搜尋頁結果會填入）


def parse_thread_title(html: str) -> str:
    """從論壇頁面提取討論串標題。

    Args:
        html: 論壇頁面的完整 HTML 字串

    Returns:
        討論串標題文字，找不到時回傳空字串
    """
    # 使用 html.parser 解析 HTML（不需額外安裝 lxml）
    soup = BeautifulSoup(html, "html.parser")
    # 標題位於 span#ctl00_ContentPlaceHolder1_lblTitle
    title_tag = soup.find("span", id="ctl00_ContentPlaceHolder1_lblTitle")
    # 找到就回傳文字，找不到回傳空字串
    return title_tag.get_text(strip=True) if title_tag else ""


def parse_comments(html: str, base_url: str) -> list[ForumPost]:
    """從論壇頁面提取所有回覆留言。

    Args:
        html: 論壇頁面的完整 HTML 字串
        base_url: 論壇網站根網址（用於組裝永久連結）

    Returns:
        ForumPost 物件列表，依頁面出現順序排列
    """
    soup = BeautifulSoup(html, "html.parser")
    posts = []  # 儲存解析出的貼文

    # 找出所有回覆區塊：每個回覆的外層 div 有 id='reply{N}' 格式
    reply_divs = soup.find_all("div", id=re.compile(r"^reply\d+$"))

    for reply_div in reply_divs:
        # --- 提取使用者名稱 ---
        # 使用者名稱在 a[id$='_lnkName'] 標籤中
        name_tag = reply_div.find("a", id=re.compile(r"lnkName$"))
        if not name_tag:
            continue  # 找不到使用者名稱，跳過此留言
        username = name_tag.get_text(strip=True)

        # --- 提取時間戳記 ---
        # 優先使用隱藏的 local-time-src span（有穩定的 data-utc 屬性）
        date_tag = reply_div.find("span", class_="local-time-src", attrs={"data-utc": True})
        if not date_tag:
            # 備用：使用顯示用的 local-time span
            date_tag = reply_div.find("span", class_="local-time", attrs={"data-utc": True})
        if not date_tag:
            continue  # 找不到時間，跳過此留言

        # 解析 ISO 8601 UTC 時間並轉換為台灣時區
        utc_str = date_tag["data-utc"]
        timestamp = _parse_utc_time(utc_str)

        # --- 提取 goto ID ---
        # 從 btnCopyCommentLink 的 onclick 屬性中用正則提取 goto=(\d+)
        goto_id = _extract_goto_id(reply_div)
        if goto_id is None:
            # 備用：從 reply div 的 id 屬性提取數字
            reply_id_match = re.search(r"\d+", reply_div.get("id", ""))
            goto_id = int(reply_id_match.group()) if reply_id_match else 0

        # --- 提取貼文內容（保留 HTML） ---
        body_tag = reply_div.find("div", class_="post-body")
        if not body_tag:
            continue  # 找不到內容，跳過此留言
        # decode_contents() 保留內部 HTML（圖片、連結、表格等）
        content_html = body_tag.decode_contents().strip()

        # --- 組裝永久連結 ---
        # 從 btnCopyCommentLink 的 onclick 提取路徑
        permalink = _extract_permalink(reply_div, base_url)

        # 建立 ForumPost 物件並加入列表
        posts.append(ForumPost(
            username=username,
            timestamp=timestamp,
            goto_id=goto_id,
            content_html=content_html,
            permalink=permalink,
        ))

    return posts


def parse_search_results(html: str, base_url: str) -> list[ForumPost]:
    """從作者搜尋頁提取所有貼文。

    搜尋頁結構為 div.forum-card#comment{ID}，每則貼文包含：
    - 討論串標題（a[id$='Lkbtn']）
    - 作者（i.bi-person 文字）
    - 時間（span.local-time[data-utc]）
    - 內容（div.post-body）
    - 永久連結（a[id$='btnCopyLink'] 的 onclick）

    Args:
        html: 搜尋頁的完整 HTML 字串
        base_url: 論壇網站根網址（用於組裝永久連結）

    Returns:
        ForumPost 物件列表，含 thread_title 欄位
    """
    soup = BeautifulSoup(html, "html.parser")
    posts = []  # 儲存解析出的貼文

    # 找出所有 forum-card 區塊：id 格式為 comment{N}
    cards = soup.find_all("div", class_="forum-card", id=re.compile(r"^comment\d+$"))

    for card in cards:
        # --- 提取 goto ID ---
        # 從 card 的 id 屬性 comment{N} 提取數字
        id_match = re.search(r"comment(\d+)", card.get("id", ""))
        if not id_match:
            continue  # 無法取得 ID，跳過
        goto_id = int(id_match.group(1))

        # --- 提取討論串標題 ---
        # 標題在 a[id$='Lkbtn'] 連結中
        title_link = card.find("a", id=re.compile(r"Lkbtn$"))
        thread_title = title_link.get_text(strip=True) if title_link else ""

        # --- 提取使用者名稱 ---
        # 使用者名稱在 i.bi-person 圖示的文字中
        person_icon = card.find("i", class_="bi-person")
        if not person_icon:
            continue  # 找不到作者，跳過
        username = person_icon.get_text(strip=True)

        # --- 提取時間戳記 ---
        # 時間在 span.local-time[data-utc] 屬性中
        time_span = card.find("span", class_="local-time", attrs={"data-utc": True})
        if not time_span:
            continue  # 找不到時間，跳過
        timestamp = _parse_utc_time(time_span["data-utc"])

        # --- 提取貼文內容（保留 HTML） ---
        body_div = card.find("div", class_="post-body")
        if not body_div:
            continue  # 找不到內容，跳過
        content_html = body_div.decode_contents().strip()

        # --- 組裝永久連結 ---
        # 從 btnCopyLink 的 onclick 提取路徑
        copy_btn = card.find("a", id=re.compile(r"btnCopyLink$"))
        permalink = ""
        if copy_btn:
            onclick = copy_btn.get("onclick", "")
            match = re.search(r'copyForumLink\(["\u0026quot;]*([^"&]+)', onclick)
            if match:
                permalink = f"{base_url}{match.group(1)}"

        # 建立 ForumPost 物件並加入列表
        posts.append(ForumPost(
            username=username,
            timestamp=timestamp,
            goto_id=goto_id,
            content_html=content_html,
            permalink=permalink,
            thread_title=thread_title,
        ))

    return posts


def has_next_page(html: str) -> bool:
    """檢查目前頁面是否還有下一頁（用於 PostBack 翻頁判斷）。

    判斷方式：找「最後一頁」按鈕（chevron-bar-right 圖示）。
    如果存在可點擊的 <a> 標籤包含此圖示，代表還有後續頁面。

    Args:
        html: 論壇頁面的完整 HTML 字串

    Returns:
        True 表示還有下一頁，False 表示已在最後一頁
    """
    soup = BeautifulSoup(html, "html.parser")
    # 在上方分頁器中找「最後一頁」按鈕的圖示
    last_icon = soup.select_one(
        "nav[aria-label*='pagination'] a.page-link i.bi-chevron-bar-right"
    )
    return last_icon is not None


def extract_postback_data(html: str) -> dict | None:
    """提取 ASP.NET PostBack 翻頁所需的表單資料。

    找到「最後一頁」按鈕，提取其 __doPostBack 的 EVENTTARGET，
    以及頁面上的 __VIEWSTATE、__EVENTVALIDATION 等隱藏欄位。

    Args:
        html: 論壇頁面的完整 HTML 字串

    Returns:
        包含 POST 資料的字典，找不到翻頁按鈕時回傳 None
    """
    soup = BeautifulSoup(html, "html.parser")

    # 找「最後一頁」按鈕（包含 chevron-bar-right 圖示的 <a> 標籤）
    last_icon = soup.select_one(
        "nav[aria-label*='pagination'] a.page-link i.bi-chevron-bar-right"
    )
    if not last_icon:
        return None  # 已在最後一頁，無需翻頁

    # 取得父元素 <a> 的 href 屬性（含 __doPostBack 呼叫）
    parent_a = last_icon.parent
    href = parent_a.get("href", "")

    # 用正則從 __doPostBack('控制項路徑','') 提取 EVENTTARGET
    match = re.search(r"__doPostBack\('([^']+)'", href)
    if not match:
        return None  # 無法解析 PostBack 目標
    event_target = match.group(1)

    # 提取 ASP.NET 隱藏表單欄位
    viewstate = _get_hidden_field(soup, "__VIEWSTATE")
    viewstate_gen = _get_hidden_field(soup, "__VIEWSTATEGENERATOR")
    event_validation = _get_hidden_field(soup, "__EVENTVALIDATION")

    # 組裝 POST 資料
    return {
        "__EVENTTARGET": event_target,  # 翻頁按鈕的控制項路徑
        "__EVENTARGUMENT": "",  # PostBack 事件參數（翻頁時為空）
        "__VIEWSTATE": viewstate,  # ASP.NET 頁面狀態
        "__VIEWSTATEGENERATOR": viewstate_gen,  # 狀態產生器 ID
        "__EVENTVALIDATION": event_validation,  # 事件驗證令牌
    }


def _parse_utc_time(utc_str: str) -> datetime:
    """將 UTC 時間字串轉換為台灣時區的 datetime。

    Args:
        utc_str: ISO 8601 格式的 UTC 時間字串，如 '2023-01-31T09:58:00Z'

    Returns:
        台灣時區的 datetime 物件
    """
    # 移除結尾的 'Z' 並解析為 UTC 時間
    utc_str = utc_str.rstrip("Z")
    dt = datetime.fromisoformat(utc_str).replace(tzinfo=timezone.utc)
    # 轉換為台灣時區
    return dt.astimezone(TZ)


def _extract_goto_id(reply_div) -> int | None:
    """從回覆區塊中提取 goto ID。

    Args:
        reply_div: BeautifulSoup 的回覆區塊元素

    Returns:
        goto ID 數字，找不到時回傳 None
    """
    # 找 btnCopyCommentLink 按鈕
    link_tag = reply_div.find("a", id=re.compile(r"btnCopyCommentLink$"))
    if not link_tag:
        return None
    # 從 onclick 屬性提取 goto=(\d+)
    onclick = link_tag.get("onclick", "")
    match = re.search(r"goto=(\d+)", onclick)
    return int(match.group(1)) if match else None


def _extract_permalink(reply_div, base_url: str) -> str:
    """從回覆區塊中組裝永久連結。

    Args:
        reply_div: BeautifulSoup 的回覆區塊元素
        base_url: 論壇網站根網址

    Returns:
        完整的永久連結 URL
    """
    # 找 btnCopyCommentLink 按鈕
    link_tag = reply_div.find("a", id=re.compile(r"btnCopyCommentLink$"))
    if not link_tag:
        # 備用：用 reply div 的 id 組裝
        return ""
    # 從 onclick 提取相對路徑
    onclick = link_tag.get("onclick", "")
    # 匹配 copyForumLink("...") 中的路徑
    match = re.search(r'copyForumLink\(["\u0026quot;]*([^"&]+)', onclick)
    if match:
        path = match.group(1)
        return f"{base_url}{path}"
    return ""


def _get_hidden_field(soup, field_name: str) -> str:
    """取得 ASP.NET 隱藏表單欄位的值。

    Args:
        soup: BeautifulSoup 物件
        field_name: 欄位名稱（如 __VIEWSTATE）

    Returns:
        欄位值，找不到時回傳空字串
    """
    tag = soup.find("input", {"name": field_name})
    return tag["value"] if tag else ""
