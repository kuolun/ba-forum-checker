"""主程式入口：論壇監控的單次檢查、持續監控與測試模式。"""

import argparse  # 命令列參數解析
import logging  # 日誌記錄
import time  # 計時與等待
from datetime import datetime  # 時間戳記

from config import BASE_URL, CHECK_INTERVAL, TARGETS, TZ  # 設定
from notifier import build_email_body, build_email_subject, send_notification  # 通知
from parser import parse_comments, parse_search_results, parse_thread_title  # 解析
from scraper import create_session, fetch_last_page, fetch_search_page  # 爬蟲
from state import is_already_sent, load_state, mark_as_sent, save_state  # 狀態

# 設定日誌格式
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _check_config() -> bool:
    """確認必要的環境變數都已設定。

    Returns:
        True 表示設定完整，False 表示缺少必要設定
    """
    ok = True
    if not BASE_URL:
        logger.error("未設定 FORUM_BASE_URL（論壇根網址），無法執行檢查")
        ok = False
    if not TARGETS:
        logger.error("未設定 WATCH_AUTHORS（監控帳號，逗號分隔），無法執行檢查")
        ok = False
    return ok


def check_once(test_mode: bool = False, resend: bool = False,
               save: bool = True) -> int:
    """執行一次完整的論壇檢查流程。

    流程：載入狀態 → 遍歷每個目標 → 爬取最後頁 → 解析留言
    → 過濾新留言 → 發送通知 → 更新狀態

    Args:
        test_mode: True 時只印出 Email 內容，不實際寄送
        resend: True 時忽略已發送記錄，強制重發所有留言
        save: False 時不寫回狀態檔（dry-run 用，避免污染既有狀態）

    Returns:
        本次發送的通知數量
    """
    # 缺少必要設定時直接中止，避免發出沒有網址的請求
    if not _check_config():
        return 0

    # 載入已發送狀態（載入時會自動把舊格式的帳號名 key 遷移為代號）
    state = load_state()
    # 建立 HTTP Session（共用 cookie）
    session = create_session()
    # 計數本次發送的通知數
    total_sent = 0
    # 計數被判定為「已發送過」而略過的貼文數
    total_skipped = 0

    now = datetime.now(TZ)
    logger.info("===== 開始檢查 %s =====", now.strftime("%Y/%m/%d %H:%M"))

    for target in TARGETS:
        target_name = target["name"]
        logger.info("--- 檢查目標：%s ---", target_name)

        try:
            strategy = target.get("strategy", "postback")

            if strategy == "author_search":
                # 作者搜尋頁策略：GET 第一頁（最新貼文）
                html = fetch_search_page(session, target["path"])
                # 搜尋頁直接解析，每則貼文自帶 thread_title
                target_posts = parse_search_results(html, BASE_URL)
                logger.info("找到 %d 則留言", len(target_posts))
            else:
                # 原有策略：PostBack 翻到最後頁
                html = fetch_last_page(
                    session,
                    target["path"],
                    user_filter=target.get("user_filter"),
                )
                # 解析討論串標題
                thread_title = parse_thread_title(html)
                if not thread_title:
                    thread_title = target_name  # 找不到標題時用帳號名稱
                # 解析頁面上的所有留言
                posts = parse_comments(html, BASE_URL)
                logger.info("找到 %d 則留言", len(posts))
                # 過濾：只處理目標帳號的留言
                target_posts = [p for p in posts if p.username == target_name]
                # 為每則貼文填入討論串標題
                for p in target_posts:
                    p.thread_title = thread_title

            logger.info("目標帳號留言：%d 則", len(target_posts))

            # 遍歷每則留言，檢查是否為新留言
            for post in target_posts:
                # 檢查是否已發送過（除非 resend 模式）
                if not resend and is_already_sent(state, target_name, post.goto_id):
                    total_skipped += 1
                    continue  # 已發送過，跳過

                # 組裝 Email（使用貼文自帶的 thread_title，或外層的 thread_title）
                title = post.thread_title or target_name
                subject = build_email_subject(post, title)
                body = build_email_body(post, title)

                if test_mode:
                    # 測試模式：只印出不寄送
                    print(f"\n{'='*60}")
                    print(f"主旨：{subject}")
                    print(f"{'='*60}")
                    print(f"帳號：{post.username}")
                    print(f"時間：{post.timestamp.strftime('%Y/%m/%d %H:%M')}")
                    print(f"連結：{post.permalink}")
                    print(f"goto ID：{post.goto_id}")
                    print(f"-"*40)
                    # 印出純文字版本的內容（去除 HTML 標籤）
                    from bs4 import BeautifulSoup
                    text_content = BeautifulSoup(post.content_html, "html.parser").get_text()
                    # 只印前 200 字
                    preview = text_content[:200] + ("..." if len(text_content) > 200 else "")
                    print(f"內容預覽：{preview}")
                    print(f"{'='*60}")
                    total_sent += 1
                else:
                    # 正式模式：發送 Email
                    success = send_notification(subject, body)
                    if success:
                        total_sent += 1
                        logger.info("已發送通知：%s (goto=%d)", post.username, post.goto_id)
                    else:
                        logger.error("通知發送失敗：%s (goto=%d)", post.username, post.goto_id)
                        continue  # 發送失敗不標記為已發送

                # 標記為已發送
                mark_as_sent(state, target_name, post.goto_id)

        except Exception as e:
            logger.error("檢查 %s 時發生錯誤：%s", target_name, e)
            continue  # 單一目標失敗不影響其他目標

    # 儲存狀態（dry-run 不寫回）
    if save:
        save_state(state)
    else:
        logger.info("dry-run 模式：不寫回狀態檔")

    logger.info("本次共發送 %d 則通知，略過已發送 %d 則", total_sent, total_skipped)
    return total_sent


def main():
    """程式主入口：解析命令列參數並執行對應模式。"""
    # 定義命令列參數
    arg_parser = argparse.ArgumentParser(
        description="論壇貼文監控器 — 自動偵測指定作者的新貼文並發送 Email 通知",
    )
    arg_parser.add_argument(
        "--test", action="store_true",
        help="測試模式：只印出 Email 內容，不實際寄送（仍會更新狀態檔）",
    )
    arg_parser.add_argument(
        "--dry-run", action="store_true",
        help="演練模式：抓取並比對新舊貼文，但不寄信也不寫回狀態檔",
    )
    arg_parser.add_argument(
        "--loop", action="store_true",
        help="持續監控模式：每隔固定時間自動檢查",
    )
    arg_parser.add_argument(
        "--resend", action="store_true",
        help="強制重發：忽略已發送記錄，重新發送所有留言",
    )
    args = arg_parser.parse_args()

    # dry-run 等同「不寄信 + 不寫狀態」
    test_mode = args.test or args.dry_run
    save = not args.dry_run

    if args.loop:
        # 持續監控模式
        logger.info("啟動持續監控模式（間隔 %d 秒）", CHECK_INTERVAL)
        while True:
            try:
                check_once(test_mode=test_mode, resend=args.resend, save=save)
            except KeyboardInterrupt:
                logger.info("收到中斷訊號，停止監控")
                break
            except Exception as e:
                logger.error("檢查過程發生未預期錯誤：%s", e)

            logger.info("等待 %d 秒後再次檢查...", CHECK_INTERVAL)
            time.sleep(CHECK_INTERVAL)
    else:
        # 單次檢查模式
        check_once(test_mode=test_mode, resend=args.resend, save=save)


if __name__ == "__main__":
    main()
