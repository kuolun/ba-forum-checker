"""notifier.py 的單元測試。"""

from datetime import datetime  # 日期時間建立
from unittest.mock import MagicMock, patch  # Mock 模擬 SMTP
from zoneinfo import ZoneInfo  # 時區

import pytest  # 測試框架

from notifier import build_email_body, build_email_subject, send_notification
from parser import ForumPost  # 貼文資料結構

# 台灣時區
TW_TZ = ZoneInfo("Asia/Taipei")


@pytest.fixture
def sample_post():
    """建立測試用的 ForumPost 物件。"""
    return ForumPost(
        username="author_a",
        timestamp=datetime(2026, 2, 25, 10, 17, tzinfo=TW_TZ),
        goto_id=15162,
        content_html="<p>測試留言內容</p>",
        permalink="https://forum.example.com/Forum/128/author_a_thread.aspx?goto=15162",
    )


# === Email 主旨測試 ===


class TestBuildEmailSubject:
    """測試 build_email_subject 函式。"""

    def test_format(self, sample_post):
        """主旨格式應為 {前綴} {帳號} {時間} 更新：{標題}。"""
        subject = build_email_subject(sample_post, "author_a 的討論串")
        assert subject == "[論壇] author_a 2026/02/25 10:17 更新：author_a 的討論串"

    def test_chinese_username(self):
        """非 ASCII 之外的帳號名稱也應正確顯示。"""
        post = ForumPost(
            username="author_b",
            timestamp=datetime(2026, 3, 1, 14, 30, tzinfo=TW_TZ),
            goto_id=100,
            content_html="<p>test</p>",
            permalink="https://example.com",
        )
        subject = build_email_subject(post, "author_b 的討論串")
        assert "author_b" in subject
        assert "2026/03/01 14:30" in subject


# === Email 內文測試 ===


class TestBuildEmailBody:
    """測試 build_email_body 函式。"""

    def test_contains_username(self, sample_post):
        """內文應包含帳號名稱。"""
        body = build_email_body(sample_post, "author_a 的討論串")
        assert "author_a" in body

    def test_contains_timestamp(self, sample_post):
        """內文應包含時間。"""
        body = build_email_body(sample_post, "author_a 的討論串")
        assert "2026/02/25 10:17" in body

    def test_contains_permalink(self, sample_post):
        """內文應包含永久連結。"""
        body = build_email_body(sample_post, "author_a 的討論串")
        assert sample_post.permalink in body

    def test_contains_content_html(self, sample_post):
        """內文應包含貼文原始 HTML 內容。"""
        body = build_email_body(sample_post, "author_a 的討論串")
        assert "測試留言內容" in body

    def test_is_html_format(self, sample_post):
        """內文應為 HTML 格式。"""
        body = build_email_body(sample_post, "author_a 的討論串")
        assert "<div" in body
        assert "<a href" in body

    def test_preserves_image_tags(self):
        """應保留圖片標籤（外部連結）。"""
        post = ForumPost(
            username="test",
            timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=TW_TZ),
            goto_id=1,
            content_html='<p><img src="https://i.imgur.com/test.png"></p>',
            permalink="https://example.com",
        )
        body = build_email_body(post, "test")
        assert "https://i.imgur.com/test.png" in body


# === Email 發送測試 ===


class TestSendNotification:
    """測試 send_notification 函式。"""

    @patch("notifier.GMAIL_APP_PASSWORD", "")
    def test_skips_when_no_password(self):
        """未設定密碼時應跳過寄信並回傳 False。"""
        result = send_notification("test", "<p>test</p>")
        assert result is False

    @patch("notifier.smtplib.SMTP_SSL")
    @patch("notifier.GMAIL_APP_PASSWORD", "test-password")
    @patch("notifier.GMAIL_FROM", "from@test.com")
    @patch("notifier.GMAIL_TO", "to@test.com")
    def test_sends_email_successfully(self, mock_smtp_class):
        """密碼已設定時應成功寄出 Email。"""
        # 模擬 SMTP 連線
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

        result = send_notification("test subject", "<p>test body</p>")
        assert result is True
        # 確認有呼叫 login 和 sendmail
        mock_server.login.assert_called_once_with("from@test.com", "test-password")
        mock_server.sendmail.assert_called_once()

    @patch("notifier.smtplib.SMTP_SSL")
    @patch("notifier.GMAIL_APP_PASSWORD", "test-password")
    def test_handles_smtp_error(self, mock_smtp_class):
        """SMTP 錯誤時應回傳 False。"""
        import smtplib
        mock_smtp_class.side_effect = smtplib.SMTPException("auth failed")

        result = send_notification("test", "<p>test</p>")
        assert result is False
