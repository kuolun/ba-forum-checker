"""state.py 的單元測試。"""

import json  # JSON 操作
import os  # 檔案操作
import tempfile  # 暫存檔案

import pytest  # 測試框架

from state import (
    MAX_SENT_IDS,
    author_key,
    is_already_sent,
    load_state,
    mark_as_sent,
    migrate_state,
    save_state,
)

# 測試用的假帳號名稱
AUTHOR_A = "author_a"
AUTHOR_B = "作者乙"  # 含非 ASCII 字元，驗證編碼處理
# 對應的代號
KEY_A = author_key(AUTHOR_A)
KEY_B = author_key(AUTHOR_B)


@pytest.fixture
def temp_state_file(monkeypatch):
    """建立暫存狀態檔案供測試使用。

    使用 monkeypatch 暫時覆蓋 state.py 中的 STATE_FILE 路徑。
    """
    # 建立暫存檔案
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    # 覆蓋 STATE_FILE 常數
    monkeypatch.setattr("state.STATE_FILE", path)
    yield path
    # 測試結束後清理
    if os.path.exists(path):
        os.unlink(path)


class TestAuthorKey:
    """測試 author_key 函式。"""

    def test_is_12_hex_chars(self):
        """代號應為 12 碼小寫十六進位字串。"""
        key = author_key(AUTHOR_A)
        assert len(key) == 12
        assert all(c in "0123456789abcdef" for c in key)

    def test_is_stable(self):
        """同一帳號名應永遠對應同一代號。"""
        assert author_key(AUTHOR_A) == author_key(AUTHOR_A)

    def test_different_names_differ(self):
        """不同帳號名應對應不同代號。"""
        assert author_key(AUTHOR_A) != author_key(AUTHOR_B)

    def test_does_not_leak_name(self):
        """代號不應包含原始帳號名稱。"""
        assert AUTHOR_A not in author_key(AUTHOR_A)
        assert AUTHOR_B not in author_key(AUTHOR_B)

    def test_handles_non_ascii(self):
        """非 ASCII 帳號名也應能產生代號。"""
        assert len(author_key(AUTHOR_B)) == 12


class TestMigrateState:
    """測試 migrate_state 函式（舊格式 → 代號格式）。"""

    def test_migrates_plain_name_keys(self):
        """以帳號名為 key 的舊狀態應轉成代號。"""
        old = {AUTHOR_A: {"sent_ids": [1, 2, 3]}}
        new, changed = migrate_state(old)
        assert changed == 1
        assert new == {KEY_A: {"sent_ids": [1, 2, 3]}}

    def test_migrates_non_ascii_keys(self):
        """非 ASCII 帳號名的 key 也應被遷移。"""
        old = {AUTHOR_B: {"sent_ids": [10]}}
        new, changed = migrate_state(old)
        assert changed == 1
        assert new == {KEY_B: {"sent_ids": [10]}}

    def test_leaves_hashed_keys_untouched(self):
        """已是代號格式的 key 應原封不動。"""
        already = {KEY_A: {"sent_ids": [5, 6]}}
        new, changed = migrate_state(already)
        assert changed == 0
        assert new == already

    def test_is_idempotent(self):
        """重複遷移結果應相同（不會反覆改動）。"""
        old = {AUTHOR_A: {"sent_ids": [1, 2]}}
        once, _ = migrate_state(old)
        twice, changed = migrate_state(once)
        assert changed == 0
        assert twice == once

    def test_merges_when_both_keys_exist(self):
        """新舊 key 同時存在時應合併 sent_ids 且不重複。"""
        mixed = {KEY_A: {"sent_ids": [1, 2]}, AUTHOR_A: {"sent_ids": [2, 3]}}
        new, changed = migrate_state(mixed)
        assert changed == 1
        assert new[KEY_A]["sent_ids"] == [1, 2, 3]

    def test_preserves_other_fields(self):
        """遷移應保留 sent_ids 以外的欄位。"""
        old = {AUTHOR_A: {"sent_ids": [1], "last_check": "2026-03-04T10:00:00+08:00"}}
        new, _ = migrate_state(old)
        assert new[KEY_A]["last_check"] == "2026-03-04T10:00:00+08:00"

    def test_empty_state(self):
        """空狀態遷移後仍為空。"""
        assert migrate_state({}) == ({}, 0)


class TestLoadState:
    """測試 load_state 函式。"""

    def test_returns_empty_when_no_file(self, monkeypatch):
        """檔案不存在時應回傳空字典。"""
        monkeypatch.setattr("state.STATE_FILE", "/nonexistent/path.json")
        assert load_state() == {}

    def test_loads_existing_state(self, temp_state_file):
        """應能載入已存在的（代號格式）狀態檔。"""
        # 先寫入測試資料
        test_data = {KEY_A: {"sent_ids": [100, 200, 300]}}
        with open(temp_state_file, "w", encoding="utf-8") as f:
            json.dump(test_data, f)

        state = load_state()
        assert state == test_data

    def test_migrates_legacy_state_on_load(self, temp_state_file):
        """載入舊格式狀態檔時應自動遷移成代號格式。"""
        legacy = {AUTHOR_A: {"sent_ids": [100, 200]}, AUTHOR_B: {"sent_ids": [300]}}
        with open(temp_state_file, "w", encoding="utf-8") as f:
            json.dump(legacy, f, ensure_ascii=False)

        state = load_state()
        assert set(state.keys()) == {KEY_A, KEY_B}
        # 遷移後舊貼文仍被視為已發送，不會重寄
        assert is_already_sent(state, AUTHOR_A, 100) is True
        assert is_already_sent(state, AUTHOR_B, 300) is True

    def test_handles_corrupted_file(self, temp_state_file):
        """檔案內容損壞時應回傳空字典。"""
        with open(temp_state_file, "w") as f:
            f.write("this is not json{{{")

        state = load_state()
        assert state == {}


class TestSaveState:
    """測試 save_state 函式。"""

    def test_saves_state(self, temp_state_file):
        """應能正確寫入狀態檔。"""
        test_data = {KEY_A: {"sent_ids": [1, 2, 3]}}
        save_state(test_data)

        # 驗證檔案內容
        with open(temp_state_file, encoding="utf-8") as f:
            saved = json.load(f)
        assert saved == test_data

    def test_saved_file_has_no_author_names(self, temp_state_file):
        """存檔內容不應出現帳號名稱明文。"""
        state = {}
        mark_as_sent(state, AUTHOR_A, 1)
        mark_as_sent(state, AUTHOR_B, 2)
        save_state(state)

        with open(temp_state_file, encoding="utf-8") as f:
            content = f.read()
        assert AUTHOR_A not in content
        assert AUTHOR_B not in content
        assert KEY_A in content
        assert KEY_B in content


class TestIsAlreadySent:
    """測試 is_already_sent 函式。"""

    def test_returns_true_for_sent_id(self):
        """已發送的 ID 應回傳 True。"""
        state = {KEY_A: {"sent_ids": [100, 200, 300]}}
        assert is_already_sent(state, AUTHOR_A, 200) is True

    def test_returns_false_for_new_id(self):
        """未發送的 ID 應回傳 False。"""
        state = {KEY_A: {"sent_ids": [100, 200, 300]}}
        assert is_already_sent(state, AUTHOR_A, 999) is False

    def test_returns_false_for_unknown_target(self):
        """未知目標應回傳 False。"""
        state = {KEY_A: {"sent_ids": [100]}}
        assert is_already_sent(state, AUTHOR_B, 100) is False

    def test_returns_false_for_empty_state(self):
        """空狀態應回傳 False。"""
        assert is_already_sent({}, AUTHOR_A, 100) is False

    def test_falls_back_to_legacy_key(self):
        """尚未遷移的舊 key 也應被認得（相容邏輯）。"""
        legacy = {AUTHOR_A: {"sent_ids": [100]}}
        assert is_already_sent(legacy, AUTHOR_A, 100) is True


class TestMarkAsSent:
    """測試 mark_as_sent 函式。"""

    def test_adds_new_id(self):
        """應能新增 ID 到已發送列表。"""
        state = {}
        mark_as_sent(state, AUTHOR_A, 100)
        assert 100 in state[KEY_A]["sent_ids"]

    def test_uses_hashed_key(self):
        """標記時應以代號當 key，不出現帳號名。"""
        state = {}
        mark_as_sent(state, AUTHOR_A, 100)
        assert AUTHOR_A not in state
        assert KEY_A in state

    def test_adds_to_existing_target(self):
        """應能對已有的目標新增 ID。"""
        state = {KEY_A: {"sent_ids": [100]}}
        mark_as_sent(state, AUTHOR_A, 200)
        assert state[KEY_A]["sent_ids"] == [100, 200]

    def test_does_not_duplicate_id(self):
        """不應重複加入已存在的 ID。"""
        state = {KEY_A: {"sent_ids": [100]}}
        mark_as_sent(state, AUTHOR_A, 100)
        assert state[KEY_A]["sent_ids"] == [100]

    def test_trims_to_max_size(self):
        """超過上限時應移除最舊的 ID。"""
        state = {KEY_A: {"sent_ids": list(range(MAX_SENT_IDS))}}
        # 新增一個超出上限的 ID
        mark_as_sent(state, AUTHOR_A, 9999)
        sent_ids = state[KEY_A]["sent_ids"]
        # 確認長度不超過上限
        assert len(sent_ids) <= MAX_SENT_IDS
        # 最新的 ID 應在列表中
        assert 9999 in sent_ids
        # 最舊的 ID (0) 應已被移除
        assert 0 not in sent_ids
