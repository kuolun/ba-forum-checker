# 論壇貼文監控器

監控指定論壇上指定作者的新貼文，偵測到新貼文時自動寄 Gmail 通知（含完整內容與圖片）。

論壇網址與監控帳號都不寫死在程式碼裡，全部由環境變數提供，因此這份程式碼可以公開，而不會洩漏監控對象。

## 運作方式

1. 依 `WATCH_AUTHORS` 逐一抓取該作者的搜尋結果頁（最新貼文在第一頁）
2. 解析出每則貼文的作者、時間、內容 HTML 與永久連結
3. 比對 `state.json` 中的已發送記錄，只有沒送過的貼文才寄信
4. 寄信成功後把貼文 ID 寫回 `state.json`

`state.json` 以帳號名稱的 SHA-1 前 12 碼當 key（不可逆代號），所以狀態檔本身也不會透露被監控的帳號。舊格式（直接用帳號名稱當 key）的狀態檔在載入時會自動遷移，不會把舊貼文誤判成新貼文。

## 安裝

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 設定

複製 `.env.example` 為 `.env` 並填入自己的值：

```bash
cp .env.example .env
```

| 變數 | 說明 |
|------|------|
| `FORUM_BASE_URL` | 論壇根網址，例如 `https://forum.example.com`（結尾不要加斜線） |
| `WATCH_AUTHORS` | 要監控的作者帳號，逗號分隔，例如 `author_a,author_b` |
| `GMAIL_FROM` | 寄件 Gmail 位址 |
| `GMAIL_TO` | 收件位址 |
| `GMAIL_APP_PASSWORD` | Gmail 應用程式專用密碼 |
| `EMAIL_SUBJECT_PREFIX` | 選填，Email 主旨前綴，預設 `[論壇]` |
| `CHECK_INTERVAL` | 選填，`--loop` 模式的檢查間隔秒數，預設 600 |
| `STATE_FILE` | 選填，狀態檔路徑，預設 `state.json` |

App Password 需到 [Google 帳號設定](https://myaccount.google.com/apppasswords) 產生。

## 使用方式

```bash
# 演練模式（抓取＋比對，不寄信也不寫狀態檔）
python main.py --dry-run

# 測試模式（只印出不寄信，但會更新狀態檔）
python main.py --test

# 單次檢查並寄信
python main.py

# 持續監控（依 CHECK_INTERVAL 定期檢查）
python main.py --loop

# 強制重發（忽略已發送記錄）
python main.py --resend
```

## 測試

```bash
pytest tests/
```

## GitHub Actions

專案包含 GitHub Actions workflow，台灣時間 7:00–23:00 每 10 分鐘自動檢查，並把更新後的 `state.json` commit 回 repo。

需在 GitHub repo 設定以下 Secrets：

- `FORUM_BASE_URL`
- `WATCH_AUTHORS`
- `GMAIL_FROM`
- `GMAIL_TO`
- `GMAIL_APP_PASSWORD`
