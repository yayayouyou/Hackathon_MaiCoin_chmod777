# 討論室 DB 整合 SPEC

**目標**：讓平台上的每一則討論，在任何情況下都先進 DynamoDB，並且知道是哪個帳號發的。

前置狀態（已完成，不在本 SPEC 範圍）：`agent-core/.env` 已接上 `THREADS_ACCESS_TOKEN` 與
`maia-discussion-{spaces,posts}-218322564712` 兩張表，本機讀得到 AWS 上的既有資料。

---

## 1. 現況的三個問題

### P1 · Threads 是留言落庫的前置條件

[`create_platform_post`](../agent-core/agent_ui/threads_bridge.py#L346) 的 `publish` 寫死 `True`，
流程是「先打 Threads，成功才 `_upsert`」。Threads 端任何錯誤（token 過期、rate limit、
超過 500 字、網路不通）都會 raise，[app.py:978](../agent-core/agent_ui/app.py#L978) 轉成 502，
**DB 不會留下任何紀錄**。

換句話說：Threads 掛掉的那段時間，討論室不只是不能同步，是完全不能發言，而且事後
無從得知誰想說過什麼。

### P2 · 貼文不知道是誰發的

存進去的作者欄位是 `author` = `nickname or username` 的字串快照。沒有 `username`，
也沒有 `author_role`。後果：

- 暱稱不唯一 —— AWS 上現有資料就有兩個不同的人叫「遊客8234」與「慢癈龍」，
  但畫面上無法區分同名者
- 做不到「我發過哪些文」、按讚去重、事後追責
- 官方發言與一般發言在資料上沒有差別

### P3 · API 把 DynamoDB 原始 item 整包回給瀏覽器

[app.py:919-927](../agent-core/agent_ui/app.py#L919-L927) 是 `return {"posts": posts}`，
而且這個端點不需登入。目前已經吐出 `raw_text` / `published_text` / `sync_state` /
`threads_parent_id` 等內部欄位。

這在 P2 修好之前只是雜訊；**一旦補上 `username` 就變成公開洩漏登入帳號**。

---

## 2. 規格

### S1 · 落庫先於發佈

`create_platform_post` 改成：

1. 組出 post（`sync_state='local'`）
2. `_upsert` 落庫 ← **走到這一步，這則留言就已經在 DB 裡了**
3. `publish=True` 時才嘗試 `publish_platform_post`
   - 成功 → 補上 `threads_id` / `permalink` / `published_text`，`sync_state='published'`
   - 失敗（`RuntimeError`）→ **不 raise**，記 `sync_error`（截 200 字），`sync_state` 維持 `'local'`
4. 回傳 post

`POST /api/discussions/{room_id}` 不再因為 Threads 失敗回 502。

**需要新增 `update_post(room_id, post_id, patch)`**：`_load()` 每次回傳的是從 DynamoDB
反序列化出來的新 dict，直接改 `create_platform_post` 裡的區域變數不會進 DB。

### S2 · post_key 一旦決定就不能再變（**這是 S1 的前提，漏掉會產生重複留言**）

[`_save`](../agent-core/agent_ui/threads_bridge.py#L86) 現在的排序鍵是每次即時算出來的：

```python
item["post_key"] = "T#" + str(post["threads_id"]) if post.get("threads_id") else "P#" + str(post["id"])
```

而 [`_load`](../agent-core/agent_ui/threads_bridge.py#L75) 每次讀取又把 `post_key` pop 掉。

S1 會讓一則貼文從「沒有 `threads_id`」變成「有 `threads_id`」，於是它的 `post_key` 從
`P#platform-xxx` 變成 `T#<threads_id>`。而 `_save` 用 `batch_writer` **只 put 不 delete**
→ 舊的 `P#` 那一列留在表裡 → 下次 `_load` 讀到兩筆 → **討論串出現兩則一模一樣的留言**。

規格：

- `_load()` 不再 pop `post_key`，讓它跟著 post 往返
- `_save()` 有 `post_key` 就沿用，沒有才計算（**維持現有算式**）
- `_upsert()` 插入新貼文時就把 `post_key` 決定好

> ⚠️ **不可以順手把鍵改成時間戳前綴**（即使那樣才排得了序）。`_save` 每次重寫整個
> store，換算式等於把 AWS 上既有的每一列都用新鍵複製一份，5 筆立刻變 10 筆。
> 排序問題見 §5。

### S3 · 補 `username` 與 `author_role`

| 欄位 | 平台貼文 | Threads 匯入貼文 |
|---|---|---|
| `author` | 暱稱快照（現況不變） | 現況不變 |
| `username` | 登入帳號 | 不寫 |
| `author_role` | 發文當下的 role 快照 | 不寫 |

- `create_platform_post` 與 `create_space` 各增加 `username`、`author_role` 兩個參數
- [app.py:973](../agent-core/agent_ui/app.py#L973) 與 [app.py:942](../agent-core/agent_ui/app.py#L942)
  已經查到 `player` 物件了，把 `username` 和 `auth.role_of(player)` 一起傳下去即可
- **role 是寫入當下的快照，不是讀取時再查。** 理由沿用 `discussion.py` 原本的註解：
  撤銷某人的官方身分後，他過去以官方名義發的貼文不該追溯性地變成一般發言 ——
  那會跟已經同步出去的 Threads 貼文對不上
- 匯入貼文沒有平台帳號，兩欄都不寫。前端用既有的 `source === 'threads'` 判斷就夠，
  **不要為此新增第三種 role 值**

### S4 · 回應白名單

新增 `_public_discussion_post()`，只回這些欄位：

```
id · author · author_role · text · source · source_author
created_at · permalink · parent_post_id · sync_state
```

套用於 `GET /api/discussions/{room_id}` 與 `POST /api/discussions/{room_id}`。

明確**不回**：`username`、`raw_text`、`published_text`、`threads_id`、`threads_parent_id`、
`thread_root_id`、`is_thread_root`、`kind`、`room_id`、`space_id`、`post_key`、`sync_error`。

理由與 [`auth.public_player`](../agent-core/agent_ui/auth.py) 同一條：**白名單而非黑名單，
之後新增欄位時預設不外流。**

### S5 · 待同步貼文的補發

沒有這條，S1 的 `'local'` 標記就只是一個永遠不會消失的標籤。

`sync_threads()` 在匯入 Threads 回覆**之前**，先把該室 `sync_state == 'local'` 的平台貼文
各嘗試發佈一次：

- 成功 → `update_post` 補欄位，`sync_state='published'`
- 失敗 → 不中斷整個同步，計數後維持 `'local'`

回傳值增加 `published` / `publish_errors` 兩個計數，前端的同步結果訊息一併帶上。

觸發點沿用現成的兩個，**不另外做重試引擎**：官方面板的「同步 Threads」按鈕、
`THREADS_AUTO_SYNC` 背景輪詢。

### S6 · 前端呈現

- [`types.ts`](../frontend-pixel/src/api/types.ts#L37) 的 `Post` 增加
  `syncState?: 'local' | 'published' | 'imported'` 與 `authorRole?: 'user' | 'official'`
- `asBridgePost` 帶上這兩個欄位
- [`Thread.tsx`](../frontend-pixel/src/ui/panels/Thread.tsx)：
  - `syncState === 'local'` 的貼文顯示「⏳ 尚未同步到 Threads」
  - `send()` 成功訊息依 `syncState` 分兩種說法，不要一律說「並同步到 Threads」
  - `authorRole === 'official'` 顯示官方標記

### S7 · 建立討論區維持 fail-fast（範圍邊界）

`create_space` **不套用 S1**。

討論區的 Threads 根文是後續所有回覆的掛載點（[create_platform_post:352](../agent-core/agent_ui/threads_bridge.py#L352)
取不到 `discussion_root_threads_id` 就 raise），沒有根文的討論區收不了任何留言。
把它存進 DB 只是製造一個壞掉的房間。所以建立討論區照舊：Threads 發佈失敗就整筆失敗、回 502。

順帶修一個現有的不一致：[Rooms.tsx:131](../frontend-pixel/src/ui/panels/Rooms.tsx#L131)
開場文 `maxLength=460`，但 [`publish_platform_post`](../agent-core/agent_ui/threads_bridge.py#L325)
實際可用字數是 500 減署名前綴 `[MAIA 平台｜{author}]\n`（author 最長 60）→ 最少只剩約 430。
前端收到 **400** 即可，剩餘的邊界情況後端本來就有明確錯誤訊息。

### S8 · 移除另一套討論室後端

| 檔案 | 動作 |
|---|---|
| `agent_ui/discussion.py` | 刪除 |
| [app.py:32](../agent-core/agent_ui/app.py#L32) | import 移除 `discussion` |
| [app.py:150-157](../agent-core/agent_ui/app.py#L150-L157) | 刪 `PostRequest` |
| [app.py:355-379](../agent-core/agent_ui/app.py#L355-L379) | 刪兩個 `/api/discussion/{space_id}/posts` 端點 |
| [app.py:382-391](../agent-core/agent_ui/app.py#L382-L391) | 刪 `_public_post`（由 S4 的新函式取代） |
| [scripts/create_tables.py:31](../agent-core/scripts/create_tables.py#L31) | 移除 `discussion.create_tables()` |
| [tests/test_auth.py:274-356](../agent-core/tests/test_auth.py#L274-L356) | 刪 `dclient` fixture 與該組測試 |
| [docs/資料模型.md:154-155](資料模型.md#L154) | `maia_posts` / `maia_post_likes` 兩列改成實際存在的兩張表 |

AWS 上不存在 `maia_discussion_*` 這組表，**沒有資料遷移問題**。

---

## 3. 驗收條件

### 自動測試

沿用 [`tests/test_threads_bridge.py`](../agent-core/tests/test_threads_bridge.py) 既有的
`monkeypatch` + `tmp_path` JSON store 模式。

| # | 測試 | 為什麼這條不能少 |
|---|---|---|
| 1 | `publish_platform_post` 拋錯時，貼文仍在 `list_posts` 裡且 `sync_state == 'local'` | S1 的全部意義 |
| 2 | 同上情境，`POST /api/discussions/{id}` 回 200 而非 502 | 使用者看到「已送出，待同步」而不是失敗 |
| 3 | 一則貼文從 local 變 published 後，`list_posts` 的長度不變 | S2 的重複列陷阱 |
| 4 | 平台貼文寫入後 store 裡有 `username`，但 API 回應沒有 | S3 + S4 |
| 5 | 撤銷官方身分後，他先前的貼文 `author_role` 仍是 `official` | role 快照語意 |
| 6 | `sync_threads` 會把 local 貼文發佈掉並更新 `sync_state` | S5 |
| 7 | `create_space` 在 Threads 失敗時不建立討論區 | S7 的邊界 |

### 手動驗收（本機 `.env` 已接真表）

1. 登入 → 建討論區 → 發一則留言 → `aws dynamodb scan` 看得到該筆、且含 `username`
2. 把 `THREADS_ACCESS_TOKEN` 改壞 → 發一則 → 前端顯示「待同步」、DB 仍有紀錄
3. token 改回來 → 按官方面板的「同步 Threads」→ 該則變成已同步，
   **且討論串沒有出現重複**（這步是 S2 的實地驗證）

---

## 4. 明確不做

| 項目 | 為什麼 |
|---|---|
| 儲存層改單筆 `put_item` / 可 `Query` | 現有寫法在 demo 資料量下沒有體感差異，而它是目前唯一能跑且有真實資料的路徑。整合的同時動它，是拿唯一能動的功能去換一個現在看不到的好處 |
| 多實例安全 | `_upsert` 的「讀全表 → 改 → 寫全表」只靠 process 內的 `_LOCK`。單容器部署沒問題；改走 App Runner 自動擴的話，兩人同時發文會靜默吃掉一則。**要在 `_upsert` 上留一行註解標明這個前提** |
| 按讚 | 前端 ♥ 寫死 0。要做需要 `maia_post_likes` 去重表，否則同一個人可以無限點 |
| 玩家綁自己的 Threads 帳號 | 現在所有留言都由 MAIA 官方帳號代發、加 `[MAIA 平台｜暱稱]` 署名。改成每人一個帳號是另一個量級的工作 |
| 暱稱唯一性 | 兩個玩家可以取一樣的暱稱，畫面上分不出來。S3 存了 `username` 之後才有解決的基礎 |

---

## 5. 已知限制（做完之後依然存在）

- `post_key` 的值是 `T#<threads_id>` 或 `P#<id>`，**不是時間戳**，所以 DynamoDB 的排序鍵
  排不出時間序。`list_posts` 是把整室貼文載入後在 Python 裡排。單室貼文無法分頁。
- `_load()` 是 `scan()` 全表、`_save()` 是整包重寫。每發一則留言 = 掃全表 + 重寫全表。
- 這兩點都指向同一個未來工作：把 `post_key` 換成 `<created_at 毫秒>#<亂數>`
  （即被刪掉的 `discussion.py` 原本的設計）並改用 `Query`。**要做的話必須連同既有資料
  一起遷移**，理由見 S2。
