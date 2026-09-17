"""Email 通知模組：組裝 HTML Email 並透過 Gmail SMTP 發送。"""

import logging  # 日誌記錄
import re  # 正則表達式，用於處理圖片標籤
import smtplib  # SMTP 郵件發送
from email.mime.text import MIMEText  # MIME 文字格式

from config import EMAIL_SUBJECT_PREFIX, GMAIL_APP_PASSWORD, GMAIL_FROM, GMAIL_TO  # 設定
from parser import ForumPost  # 貼文資料結構

# 設定日誌
logger = logging.getLogger(__name__)


def build_email_subject(post: ForumPost, thread_title: str) -> str:
    """組裝 Email 主旨。

    格式：{前綴} {帳號} {年}/{月}/{日} {時}:{分} 更新：{討論串標題}

    前綴預設為「[論壇]」，可用環境變數 EMAIL_SUBJECT_PREFIX 覆寫。

    Args:
        post: 貼文資料
        thread_title: 討論串標題

    Returns:
        Email 主旨字串
    """
    # 格式化台灣時間為 yyyy/MM/dd HH:mm
    time_str = post.timestamp.strftime("%Y/%m/%d %H:%M")
    return f"{EMAIL_SUBJECT_PREFIX} {post.username} {time_str} 更新：{thread_title}"


def build_email_body(post: ForumPost, thread_title: str) -> str:
    """組裝 HTML 格式的 Email 內文。

    參考截圖格式：
    - 帳號 · 時間
    - 標題（粗體連結）
    - 永久連結
    - 分隔線
    - 貼文完整內容

    圖片使用外部連結，Gmail 會自動代理載入。

    Args:
        post: 貼文資料
        thread_title: 討論串標題

    Returns:
        HTML 格式的 Email 內文
    """
    # 格式化時間
    time_str = post.timestamp.strftime("%Y/%m/%d %H:%M")

    # 組裝 HTML Email
    html = f"""\
<div style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; font-size: 16px;">
    <!-- 帳號與時間 -->
    <p style="color: #555; margin-bottom: 8px; font-size: 16px;">
        {post.username} · {time_str}
    </p>

    <!-- 討論串標題（粗體連結） -->
    <p style="margin-bottom: 4px;">
        <a href="{post.permalink}"
           style="font-size: 20px; font-weight: bold; color: #1a73e8; text-decoration: none;">
            {thread_title}
        </a>
    </p>

    <!-- 永久連結 -->
    <p style="margin-bottom: 16px;">
        <a href="{post.permalink}" style="color: #1a73e8; font-size: 15px;">
            {post.permalink}
        </a>
    </p>

    <!-- 分隔線 -->
    <hr style="border: none; border-top: 1px solid #ddd; margin: 16px 0;">

    <!-- 貼文完整內容（保留原始 HTML：圖片、表格等） -->
    <div style="line-height: 1.8; font-size: 16px; overflow-x: auto;">
        {_limit_image_width(post.content_html)}
    </div>
</div>
"""
    return html


def _limit_image_width(content_html: str) -> str:
    """為內容中的 <img> 標籤加上 inline max-width 限制。

    Gmail 會移除 <style> 標籤，所以必須用 inline style。
    將圖片限制在 max-width: 100% 避免超出信件版面。

    Args:
        content_html: 原始貼文 HTML 內容

    Returns:
        加上圖片寬度限制的 HTML 內容
    """
    # 匹配所有 <img> 標籤，加上 max-width 和 height:auto
    def _add_style(match):
        tag = match.group(0)
        # 如果已有 style 屬性，在其中追加
        if "style=" in tag.lower():
            return re.sub(
                r'style="',
                'style="max-width:100%;height:auto;',
                tag,
                flags=re.IGNORECASE,
            )
        # 沒有 style 屬性，新增一個
        return tag.replace(">", ' style="max-width:100%;height:auto;">', 1)

    return re.sub(r"<img\b[^>]*>", _add_style, content_html, flags=re.IGNORECASE)


def send_notification(subject: str, body_html: str) -> bool:
    """透過 Gmail SMTP 發送 HTML Email。

    使用 SMTP_SSL（port 465）直接建立加密連線。
    需要在 .env 中設定 GMAIL_APP_PASSWORD。

    Args:
        subject: Email 主旨
        body_html: HTML 格式的 Email 內文

    Returns:
        True 表示發送成功，False 表示失敗或未設定密碼
    """
    # 檢查 App Password 是否已設定
    if not GMAIL_APP_PASSWORD:
        logger.warning("GMAIL_APP_PASSWORD 未設定，跳過寄信")
        return False

    # 建立 HTML 格式的 MIME 訊息
    msg = MIMEText(body_html, "html", "utf-8")
    msg["Subject"] = subject  # 設定主旨
    msg["From"] = GMAIL_FROM  # 設定寄件者
    msg["To"] = GMAIL_TO  # 設定收件者

    try:
        # 使用 SMTP_SSL 建立加密連線（port 465）
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_FROM, GMAIL_APP_PASSWORD)  # 用 App Password 登入
            server.sendmail(GMAIL_FROM, [GMAIL_TO], msg.as_string())  # 發送
        logger.info("Email 已寄出：%s → %s", subject, GMAIL_TO)
        return True
    except smtplib.SMTPException as e:
        logger.error("Email 寄送失敗：%s", e)
        return False
