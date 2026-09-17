"""狀態管理模組：記錄已發送通知的貼文 ID，避免重複通知。

狀態檔以「帳號代號」為 key，而不是帳號名稱本身，
避免公開的 state.json 洩漏被監控的帳號。代號是帳號名的
SHA-1 前 12 碼（單向、不可逆，但同一帳號永遠對應同一代號）。
"""

import hashlib  # 產生帳號代號用的雜湊
import json  # JSON 讀寫
import logging  # 日誌記錄
import os  # 檔案存在檢查
import re  # 判斷 key 是否已是代號格式

from config import STATE_FILE  # 狀態檔案路徑

# 設定日誌
logger = logging.getLogger(__name__)

# 每個目標保留的已發送 ID 數量上限（避免狀態檔無限膨脹）
MAX_SENT_IDS = 100

# 帳號代號格式：12 碼小寫十六進位
KEY_PATTERN = re.compile(r"^[0-9a-f]{12}$")


def author_key(author_name: str) -> str:
    """把帳號名稱轉成不可逆的代號（SHA-1 前 12 碼）。

    Args:
        author_name: 帳號名稱

    Returns:
        12 碼小寫十六進位字串
    """
    return hashlib.sha1(author_name.encode("utf-8")).hexdigest()[:12]


def migrate_state(state: dict) -> tuple[dict, int]:
    """把舊格式（以帳號名稱為 key）的狀態遷移成代號格式。

    舊狀態檔的 key 是帳號名稱；新格式是 author_key() 的代號。
    未遷移就上線會讓所有舊貼文被當成新貼文重寄，因此每次載入
    都先做一次遷移。已是代號格式的 key 原封不動。

    Args:
        state: 原始狀態字典

    Returns:
        (遷移後的狀態字典, 被遷移的 key 數量)
    """
    migrated = {}  # 遷移後的新狀態
    changed = 0  # 被遷移的 key 數量

    for key, value in state.items():
        # 已經是代號格式就直接沿用
        target_key = key if KEY_PATTERN.match(key) else author_key(key)
        if target_key != key:
            changed += 1

        if target_key not in migrated:
            migrated[target_key] = value
            continue

        # 極少數情況：新舊 key 同時存在，合併 sent_ids（保序去重）
        existing_ids = migrated[target_key].get("sent_ids", [])
        merged = list(existing_ids)
        for goto_id in value.get("sent_ids", []):
            if goto_id not in merged:
                merged.append(goto_id)
        migrated[target_key]["sent_ids"] = merged[-MAX_SENT_IDS:]

    return migrated, changed


def load_state() -> dict:
    """從 state.json 載入狀態資料，並自動遷移舊格式。

    狀態格式（key 為 author_key() 產生的代號）：
    {
        "f7e1c9c578a0": {
            "sent_ids": [1668, 1663, 1662, ...],
            "last_check": "2026-03-04T10:00:00+08:00"
        },
        ...
    }

    Returns:
        狀態字典，檔案不存在或格式錯誤時回傳空字典
    """
    if not os.path.exists(STATE_FILE):
        logger.info("狀態檔不存在，使用空白狀態")
        return {}

    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            state = json.load(f)
        logger.info("已載入狀態檔：%s", STATE_FILE)
    except (json.JSONDecodeError, OSError) as e:
        # JSON 格式錯誤或讀取失敗時，回傳空狀態避免程式中斷
        logger.warning("狀態檔讀取失敗（%s），使用空白狀態", e)
        return {}

    # 舊格式（帳號名稱當 key）自動轉成代號格式
    state, changed = migrate_state(state)
    if changed:
        logger.info("已將 %d 個舊格式的狀態 key 遷移為帳號代號", changed)
    return state


def save_state(state: dict) -> None:
    """將狀態資料寫入 state.json。

    Args:
        state: 要儲存的狀態字典
    """
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            # ensure_ascii=False 保留非 ASCII 字元，indent=2 易於閱讀
            json.dump(state, f, ensure_ascii=False, indent=2)
        logger.info("狀態已儲存至 %s", STATE_FILE)
    except OSError as e:
        logger.error("狀態檔寫入失敗：%s", e)


def is_already_sent(state: dict, target_name: str, goto_id: int) -> bool:
    """檢查指定貼文是否已發送過通知。

    Args:
        state: 狀態字典
        target_name: 監控目標的帳號名稱
        goto_id: 貼文 ID

    Returns:
        True 表示已發送過，False 表示未發送
    """
    # 以代號取得該目標的已發送 ID 列表；相容尚未遷移的舊 key
    target_state = state.get(author_key(target_name)) or state.get(target_name, {})
    sent_ids = target_state.get("sent_ids", [])
    return goto_id in sent_ids


def mark_as_sent(state: dict, target_name: str, goto_id: int) -> None:
    """將指定貼文標記為已發送，並維護 ID 列表在上限以內。

    Args:
        state: 狀態字典（會被直接修改）
        target_name: 監控目標的帳號名稱
        goto_id: 已發送通知的貼文 ID
    """
    key = author_key(target_name)

    # 確保目標在狀態中有初始結構
    if key not in state:
        state[key] = {"sent_ids": []}

    target_state = state[key]
    sent_ids = target_state.get("sent_ids", [])

    # 避免重複加入
    if goto_id not in sent_ids:
        sent_ids.append(goto_id)

    # 只保留最近 MAX_SENT_IDS 筆（移除最舊的）
    if len(sent_ids) > MAX_SENT_IDS:
        sent_ids = sent_ids[-MAX_SENT_IDS:]

    target_state["sent_ids"] = sent_ids
