# 社群每日洞察：資料庫交接契約

摘要目前已由 `agent_ui/community_insights.py` 直接支援 DynamoDB；API 與前端
不依賴實體表設計。本機仍可明確指定 `COMMUNITY_INSIGHTS_STORAGE=json`。

## 討論資料讀取

- `list_active_spaces()`：回傳 `id`、`title`、`archived`。
- `list_posts_for_day(room_id, start_utc, end_utc)`：以 `room_id + created_at` 查詢，
  回傳 `id`、`author_username`、`author`、`source`、`text`、`created_at`、`kind`。
- `kind=bridge` 的系統同步通知不能納入摘要。
- 查詢必須使用 key/index，不應 Scan 全表。

## 建議摘要表

表名可用 `maia_community_insights`：

- PK `scope_key`：`ROOM#<room_id>` 或 `LOBBY`
- SK `insight_date`：`YYYY-MM-DD`
- 其他欄位：`headline`、`summary`、`directions`、`disagreements`、`sentiment`、
  `post_count`、`room_count`、`generated_at`、`model`、`prompt_version`

同一 scope、同一天使用同一組 PK/SK，讓排程重試保持冪等。

## 帳號關聯

討論貼文仍應保存不可變的 `author_username`，`author` 只作發文當下的暱稱快照。
摘要只輸出統計與主題，不輸出登入帳號、session 或密碼相關欄位。

## 排程

正式環境設定：

- `COMMUNITY_INSIGHTS_STORAGE=dynamodb`
- `DYNAMODB_COMMUNITY_INSIGHTS_TABLE=maia_community_insights`
- `COMMUNITY_INSIGHTS_LOCK_TTL_SECONDS=3600`

同一張表使用 `LOCK#DAILY + 日期` 保存有期限的分散式鎖，避免多個 worker
同時產生相同日期的摘要。正式排程仍建議由 EventBridge Scheduler 觸發；
`COMMUNITY_INSIGHTS_AUTO_GENERATE=true` 適合單一常駐 Web worker。
