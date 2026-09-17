"""scraper.py 的單元測試（使用 mock 避免真實網路請求）。"""

from unittest.mock import MagicMock, patch  # Mock 物件模擬 HTTP 回應

import pytest  # 測試框架
import requests  # 用於模擬 RequestException

from scraper import create_session, fetch_page, fetch_page_by_goto, fetch_last_page


class TestCreateSession:
    """測試 create_session 函式。"""

    def test_returns_session(self):
        """應回傳 requests.Session 物件。"""
        session = create_session()
        assert isinstance(session, requests.Session)

    def test_has_user_agent(self):
        """Session 應設定 User-Agent header。"""
        session = create_session()
        assert "User-Agent" in session.headers
        assert "Mozilla" in session.headers["User-Agent"]


class TestFetchPage:
    """測試 fetch_page 函式。"""

    @patch("scraper.time.sleep")  # 跳過重試等待時間
    def test_success(self, mock_sleep):
        """成功時應回傳 HTML 字串。"""
        # 模擬 HTTP 回應
        session = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "<html>test</html>"
        mock_response.raise_for_status = MagicMock()
        session.get.return_value = mock_response

        result = fetch_page(session, "https://example.com")
        assert result == "<html>test</html>"

    @patch("scraper.time.sleep")
    def test_retry_on_failure(self, mock_sleep):
        """失敗時應重試，第二次成功。"""
        session = MagicMock()
        # 第一次失敗，第二次成功
        mock_response = MagicMock()
        mock_response.text = "<html>ok</html>"
        mock_response.raise_for_status = MagicMock()
        session.get.side_effect = [
            requests.RequestException("timeout"),
            mock_response,
        ]

        result = fetch_page(session, "https://example.com")
        assert result == "<html>ok</html>"
        # 確認呼叫了 2 次
        assert session.get.call_count == 2

    @patch("scraper.time.sleep")
    def test_raises_after_max_retries(self, mock_sleep):
        """重試耗盡後應拋出例外。"""
        session = MagicMock()
        session.get.side_effect = requests.RequestException("server error")

        with pytest.raises(requests.RequestException):
            fetch_page(session, "https://example.com")
        # 確認重試了 3 次
        assert session.get.call_count == 3


class TestFetchPageByGoto:
    """測試 fetch_page_by_goto 函式。"""

    @patch("scraper.fetch_page")
    def test_constructs_correct_url(self, mock_fetch):
        """應用 goto 參數組裝正確的 URL。"""
        mock_fetch.return_value = "<html>page</html>"
        session = MagicMock()

        result = fetch_page_by_goto(
            session, "/Forum/128/test.aspx", 12345
        )
        # 確認 URL 包含 goto 參數
        call_url = mock_fetch.call_args[0][1]
        assert "goto=12345" in call_url
        assert result == "<html>page</html>"


class TestFetchLastPage:
    """測試 fetch_last_page 函式。"""

    @patch("scraper.extract_postback_data")
    @patch("scraper.has_next_page")
    @patch("scraper.fetch_page")
    def test_single_page_no_pagination(self, mock_fetch, mock_has_next, mock_postback):
        """只有一頁時應直接回傳第一頁。"""
        mock_fetch.return_value = "<html>single page</html>"
        mock_has_next.return_value = False  # 沒有下一頁

        session = MagicMock()
        result = fetch_last_page(session, "/Forum/1/test.aspx")
        assert result == "<html>single page</html>"
        # 只呼叫一次 GET，不需 POST
        mock_fetch.assert_called_once()

    @patch("scraper._post_page")
    @patch("scraper.extract_postback_data")
    @patch("scraper.has_next_page")
    @patch("scraper.fetch_page")
    def test_navigates_to_last_page(self, mock_fetch, mock_has_next,
                                     mock_postback, mock_post):
        """有多頁時應用 PostBack 翻到最後一頁。"""
        mock_fetch.return_value = "<html>page 1</html>"
        # 第一次檢查有下一頁，第二次（翻頁後）沒有
        mock_has_next.side_effect = [True, False]
        mock_postback.return_value = {"__EVENTTARGET": "btn", "__VIEWSTATE": "vs",
                                       "__EVENTVALIDATION": "ev", "__VIEWSTATEGENERATOR": "vg",
                                       "__EVENTARGUMENT": ""}
        mock_post.return_value = "<html>last page</html>"

        session = MagicMock()
        result = fetch_last_page(session, "/Forum/1/test.aspx")
        assert result == "<html>last page</html>"
        # 確認有 POST 翻頁
        mock_post.assert_called_once()

    @patch("scraper.fetch_page")
    def test_user_filter_in_url(self, mock_fetch):
        """user_filter 參數應加到 URL 中。"""
        mock_fetch.return_value = "<html>filtered</html>"
        # 模擬 has_next_page 回傳 False（單頁）
        with patch("scraper.has_next_page", return_value=False):
            session = MagicMock()
            fetch_last_page(session, "/Forum/12/test.aspx", user_filter="author_b")

        # 確認 URL 包含 user 參數
        call_url = mock_fetch.call_args[0][1]
        assert "user=author_b" in call_url
