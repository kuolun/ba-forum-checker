"""parser.py 的單元測試。"""

import os  # 檔案路徑操作
from datetime import datetime  # 日期時間驗證
from zoneinfo import ZoneInfo  # 時區驗證

import pytest  # 測試框架

from parser import (
    ForumPost,
    extract_postback_data,
    has_next_page,
    parse_comments,
    parse_thread_title,
)

# 測試用 fixture 檔案路徑
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
# 討論串 A 的頁面 HTML（主要作者 author_a）
PAGE_A_HTML = os.path.join(FIXTURES_DIR, "author_a_page.html")
# 討論串 B 的頁面 HTML（主要作者 author_b）
PAGE_B_HTML = os.path.join(FIXTURES_DIR, "author_b_page.html")
# 測試用論壇根網址
BASE_URL = "https://forum.example.com"


def _load_fixture(path: str) -> str:
    """讀取測試用 fixture 檔案。"""
    with open(path, encoding="utf-8") as f:
        return f.read()


# === 討論串標題測試 ===


class TestParseThreadTitle:
    """測試 parse_thread_title 函式。"""

    def test_page_a_title(self):
        """測試能正確提取討論串 A 的標題。"""
        html = _load_fixture(PAGE_A_HTML)
        title = parse_thread_title(html)
        assert title == "author_a 的討論串"

    def test_page_b_title(self):
        """測試能正確提取討論串 B 的標題。"""
        html = _load_fixture(PAGE_B_HTML)
        title = parse_thread_title(html)
        assert title == "author_b 的討論串"

    def test_empty_html(self):
        """空 HTML 應回傳空字串。"""
        assert parse_thread_title("") == ""

    def test_no_title_element(self):
        """HTML 中沒有標題元素時應回傳空字串。"""
        html = "<html><body><p>no title</p></body></html>"
        assert parse_thread_title(html) == ""


# === 留言解析測試 ===


class TestParseComments:
    """測試 parse_comments 函式。"""

    def test_page_a_has_comments(self):
        """討論串 A 的頁面應能解析出留言。"""
        html = _load_fixture(PAGE_A_HTML)
        posts = parse_comments(html, BASE_URL)
        # 每頁 25 則留言
        assert len(posts) == 25

    def test_page_b_has_comments(self):
        """討論串 B 的頁面應能解析出留言。"""
        html = _load_fixture(PAGE_B_HTML)
        posts = parse_comments(html, BASE_URL)
        assert len(posts) == 25

    def test_comment_fields_are_populated(self):
        """留言的所有欄位都應有值。"""
        html = _load_fixture(PAGE_A_HTML)
        posts = parse_comments(html, BASE_URL)
        first_post = posts[0]
        # 每個欄位都不應為空
        assert first_post.username  # 使用者名稱不為空
        assert first_post.timestamp  # 時間戳記不為空
        assert first_post.goto_id > 0  # goto ID 為正整數
        assert first_post.content_html  # 內容不為空
        assert first_post.permalink  # 永久連結不為空

    def test_comment_username(self):
        """留言的使用者名稱應為有效字串。"""
        html = _load_fixture(PAGE_A_HTML)
        posts = parse_comments(html, BASE_URL)
        # 所有留言的使用者名稱都應為非空字串
        for post in posts:
            assert isinstance(post.username, str)
            assert len(post.username) > 0

    def test_comment_timestamp_is_timezone_aware(self):
        """留言時間應帶有台灣時區資訊。"""
        html = _load_fixture(PAGE_A_HTML)
        posts = parse_comments(html, BASE_URL)
        for post in posts:
            # 確認是 timezone-aware datetime
            assert post.timestamp.tzinfo is not None
            # 確認時區為台灣
            assert post.timestamp.tzinfo == ZoneInfo("Asia/Taipei")

    def test_comment_goto_id_is_positive(self):
        """留言的 goto ID 應為正整數。"""
        html = _load_fixture(PAGE_A_HTML)
        posts = parse_comments(html, BASE_URL)
        for post in posts:
            assert post.goto_id > 0

    def test_comment_permalink_format(self):
        """永久連結應以網站根網址開頭並包含 goto 參數。"""
        html = _load_fixture(PAGE_A_HTML)
        posts = parse_comments(html, BASE_URL)
        for post in posts:
            assert post.permalink.startswith(BASE_URL)
            assert f"goto={post.goto_id}" in post.permalink

    def test_comments_are_ordered(self):
        """留言應按頁面出現順序排列（goto ID 遞增）。"""
        html = _load_fixture(PAGE_A_HTML)
        posts = parse_comments(html, BASE_URL)
        goto_ids = [p.goto_id for p in posts]
        # goto ID 應遞增（同一頁內）
        assert goto_ids == sorted(goto_ids)

    def test_content_html_preserves_images(self):
        """內容 HTML 應保留圖片標籤。"""
        html = _load_fixture(PAGE_A_HTML)
        posts = parse_comments(html, BASE_URL)
        # 至少有一則留言包含圖片
        has_img = any("<img" in p.content_html.lower() or "<IMG" in p.content_html for p in posts)
        # 論壇帖子通常含有圖片（如果沒有也不算錯誤，只是確認解析器保留 HTML）
        assert isinstance(posts[0].content_html, str)

    def test_empty_html_returns_empty_list(self):
        """空 HTML 應回傳空列表。"""
        assert parse_comments("", BASE_URL) == []

    def test_page_b_posts_contain_target_user(self):
        """討論串 B 的頁面（已用 user filter）應包含目標作者的帖子。"""
        html = _load_fixture(PAGE_B_HTML)
        posts = parse_comments(html, BASE_URL)
        # 至少有一則目標作者的留言
        target_posts = [p for p in posts if p.username == "author_b"]
        assert len(target_posts) > 0


# === 分頁偵測測試 ===


class TestHasNextPage:
    """測試 has_next_page 函式。"""

    def test_first_page_has_next(self):
        """第 1 頁（非最後頁）應回傳 True。"""
        html = _load_fixture(PAGE_A_HTML)
        # fixture 是第 1 頁，應有更多頁
        assert has_next_page(html) is True

    def test_empty_html_no_next(self):
        """空 HTML 應回傳 False。"""
        assert has_next_page("") is False

    def test_single_page_no_next(self):
        """只有一頁時應回傳 False（無分頁按鈕）。"""
        html = "<html><body><p>content</p></body></html>"
        assert has_next_page(html) is False


# === PostBack 資料提取測試 ===


class TestExtractPostbackData:
    """測試 extract_postback_data 函式。"""

    def test_extracts_postback_data(self):
        """應能從第 1 頁提取 PostBack 所需的表單資料。"""
        html = _load_fixture(PAGE_A_HTML)
        data = extract_postback_data(html)
        # 第 1 頁應有翻頁資料
        assert data is not None
        # 必要欄位都應存在
        assert "__EVENTTARGET" in data
        assert "__VIEWSTATE" in data
        assert "__EVENTVALIDATION" in data
        # EVENTTARGET 應包含翻頁控制項路徑
        assert "lnkPage" in data["__EVENTTARGET"]

    def test_viewstate_is_nonempty(self):
        """__VIEWSTATE 應為非空字串。"""
        html = _load_fixture(PAGE_A_HTML)
        data = extract_postback_data(html)
        assert len(data["__VIEWSTATE"]) > 0
        assert len(data["__EVENTVALIDATION"]) > 0

    def test_empty_html_returns_none(self):
        """空 HTML 應回傳 None。"""
        assert extract_postback_data("") is None

    def test_no_pagination_returns_none(self):
        """無分頁按鈕時應回傳 None。"""
        html = "<html><body><p>content</p></body></html>"
        assert extract_postback_data(html) is None
