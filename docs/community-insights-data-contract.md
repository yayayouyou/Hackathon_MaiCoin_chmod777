# 社群每日洞察：資料庫交接契約

摘要、API 與前端不應依賴 DynamoDB 的實體表設計。資料庫整併只需替換
`agent_ui/community_insights.py` 的 repository boundary。

## 討論資料讀取

- `list_active_spaces()`：回傳 `id`、`title`、`archived`。
- `list_posts_for_day(room_id, start_utc, end_utc)`：以 `room_id + created_at` 查詢，
  回傳 `id`、`author_username`、`author`、`source`、`text`、`created_at`、`kind`。
- `kind=bridge` 的系統同步通知不能納入摘要。
- 查詢必須使用 key/index，不應 Scan 全表。

## 建議摘要表

表名可用 `maia_community_insights`：

- PK `scope_key`：`ROOM#<room_id>` 或 `LOBBY`
- SK `date_key`：`DATE#YYYY-MM-DD`
- 其他欄位：`headline`、`summary`、`directions`、`disagreements`、`sentiment`、
  `post_count`、`room_count`、`generated_at`、`model`、`prompt_version`

同一 scope、同一天使用同一組 PK/SK，讓排程重試保持冪等。

## 帳號關聯

討論貼文仍應保存不可變的 `author_username`，`author` 只作發文當下的暱稱快照。
摘要只輸出統計與主題，不輸出登入帳號、session 或密碼相關欄位。

## 排程

目前單 worker demo 可用 `COMMUNITY_INSIGHTS_AUTO_GENERATE=true`。多 instance
部署時應關閉它，改由 EventBridge Scheduler 每日觸發一次，並以摘要表的
PK/SK 或 conditional write 保證只生成一次。
