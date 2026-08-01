# MAIA 實作分派 SPEC v1

> 給隊友的工作說明書。看完就能開工,不必先讀完 1,300 行的框架規格。
> 分支只有一個:`main`。每個工作包標了**檔案落點**與**驗收標準**。

---

## 0. 三十秒理解現況

**整合已完成。** repo 只剩四個目錄:

```
frontend-pixel/   像素風可走動 2D 世界 —— 唯一前端 · 156 項 e2e 全綠
agent-core/       agent 大腦 + 110 個工具 · 753 pytest 通過
data_set/         主辦 CSV(降級為「訪客示範帳戶」種子)
docs/             決策文件
```

**前端現在打開長這樣**:大廳中央一座 BTC 金幣雕像,左邊拱門通討論區、右邊通 MAX 交易所,右下角有「角色訊息窗 I」按鈕。走近拱門按 `E` 傳送,走近終端機按 `E` 開面板。

**跟兩週前唯一的差別是看不見的**:擴充架構已就位。

| | 接縫前 | 現在 |
|---|---|---|
| 新增一個面板 | 3 檔 4 處 | **新檔 + barrel 兩行** |
| 新增一個房間 | 5 檔 8 處,漏加分支會靜默把玩家送進 BTC 討論室 | **新資料夾 + barrel 兩行**,catch-all 已消失 |
| 打錯 id | 執行期空面板 | **紅色編譯錯誤 + Did you mean** |

**還沒接後端。** `frontend-pixel/src/api/` 是 100% mock,`#hud-root` 存在但 0 個子節點,`FEATURES` 有 6 筆但 Deck 還沒做。

---

## 1. 我們在做什麼

> **MAIA — 走進去問,而不是盯著看。**

命題原文:「鼓勵參賽者**跳脫傳統靜態網頁的框架**」「不限於傳統 Dashboard」。

所以評分策略是:**創意 25% 靠像素世界,商業 20% 靠「這能變成 MAX 的產品功能」,AI 設計 15% 靠讓 agent 的思考過程在世界裡看得見。**

### Demo 敘事(每一段都要有畫面)

| 段 | 畫面 | 打哪一項 |
|---|---|---|
| 1 | 走進**交易 DNA 檔案室** → 六軸雷達 + 淨值曲線 + 「我讀進 10,000 筆紀錄,第一步是對帳,發現 797 筆不一致並主動揭露」 | 商業 20% |
| 2 | 走到終端機問 agent 一句話 → **HUD 亮起工具晶片**,每顆掛真來源 | AI 設計 15% + 創意 25% |
| 3 | 說「幫我買 0.01 BTC」→ agent **只能提議**,核准卡浮在世界上方,背後工具晶片還亮著 | 主題 10% |
| 4 | 走進**風控室**,拉下實體的紅色停止拉桿 → 曝險歸零、決策台帳留紀錄 | 技術可行性 20% |

---

## 2. 四軌分工

| 軌 | 負責 | 主要檔案 | 共用 append 點 |
|---|---|---|---|
| **I · Integrator** | 接線、測試基建、demo 腳本、彩排、Bedrock 首驗 | 六個凍結檔 · `tests/` · `.kiro/` | — |
| **A · 資料層 + DNA** | `api/` 三層、adapters、DNA 面板、反事實面板、圖表 | `src/api/**` · `ui/panels/{Dna,Backtest,DataSource}.tsx` · `ui/charts/**` | `panels/index.ts` · `features/registry.ts` |
| **B · Agent + HITL** | SSE、工具晶片、AgentChat、核准疊層、後端串流與心跳 | `src/api/{chat,agent}.ts` · `ui/panels/AgentChat.tsx` · `agent-core/**` | `panels/index.ts` · `hud/channels.ts` |
| **C · HUD + Deck** | `#hud-root`、live channels、四個 block、FEATURES、Deck | `src/hud/**` · `src/features/**` | `hud/channels.ts` · `features/registry.ts` |
| **D · 美術 + 世界** | 參數化道具 kit、`?gallery=1`、三個新 zone、投影模式 | `src/art/**` · `game/props.ts` · `world/zones/**` | `zones/index.ts` |

### ⚠️ 美術是不可平行化的技能瓶頸

實測:`frontend-pixel` 的**每一行**像素美術都出自單一作者。`props.ts` 有約 120 次 `fillRect/ellipse/gradient`,單支道具 10–64 行**純手排整數偏移**,零圖檔、零預覽工具。迭代迴圈是「改數字 → HMR → 操控角色走過去 → 瞇眼看」。

**把三個新房間的美術切給三個人,換到的不是產出是返工**(受光方向畫反、用了不在 36 色調色盤裡的顏色、忘了寫 `propLights` 導致道具在暗房間裡是個黑洞)。

**做法:D 軌獨佔 `art/` 與 `props.ts`,先產出參數化槽位道具 kit,其他人只組合不繪製。**

---

## 3. 協作規則(六條)

**規則 1 · 六個檔案凍結。** `main.tsx` / `index.html` / `App.tsx` / `uiStore.ts` / `game/index.ts` / `world/types.ts`。要動 → 開 issue 給 integrator 批次處理。

**規則 2 · 全隊只有四個 append 點,都是兩行。**

```
src/world/zones/index.ts      新 zone     import 一行 + key 一行
src/ui/panels/index.ts        新 panel    import 一行 + key 一行
src/hud/channels.ts           新 HUD 通道
src/features/registry.ts      新功能入口
```

git 會如實報告衝突,5 秒可解 —— 這遠比「零衝突但白畫面」好。

**規則 3 · CSS 用 `@layer`。** `styles.css` 頂端已宣告 `@layer core, zone, hud, pro;`。zone 的 CSS 一律 `.z-<id>-` 前綴。

**規則 4 · 不准新增 runtime 相依。** `package.json` 的 dependencies 只有 `react` + `react-dom`。**Chart.js 不論 CDN 還是 npm 都不准** —— 離線 live demo 的前提。圖表手刻 SVG/CSS(參考 `agent-core/agent_ui/templates/index.html` 的 21 個 viz 卡,其中 **15 個本來就是純 CSS 橫條**)。

**規則 5 · 每幀變動的東西不進 React。** 有測試守著:走動 2 秒期間 `#ui-root` 的 DOM 變動必須是 **0**。跳動數值走 `LiveText`(只寫 `textContent`)。

**規則 6 · merge gate。** 動 `main` 前跑:

```bash
cd frontend-pixel && npx tsc --noEmit && node tests/run.mjs
cd agent-core && python -m pytest -q
```

---

## 4. 工作包

### P0 — 不做就沒有 demo

| # | 工作包 | 軌 | 檔案落點 | 驗收 |
|---|---|---|---|---|
| **W1** | **Bedrock 端到端首驗** | I | `agent-core/agent/llm/bedrock.py` | `LLM_PROVIDER=bedrock` 實跑一輪含工具呼叫;**ARM64 容器內也要驗一次**。用 `aws bedrock list-inference-profiles` 查帳號實際可用的最新 Claude,不要沿用寫死的 2024 model id |
| **W2** | **CORS / proxy** | I | `frontend-pixel/vite.config.ts` | 加 3 行 proxy 指向 `localhost:8000`。**沒有它一行 API 都呼叫不到** |
| **W3** | **後端 status 心跳** | B | `agent-core/agent_ui/app.py` | `run_agent_turn` 每次 LLM 呼叫前 yield `status`;event_stream 外層 15 秒無事件就 `yield ": ping\n\n"` |
| **W4** | **前端 paced reveal** | B | `frontend-pixel/src/api/agent.ts`(新) | Bedrock 無 `converse_stream`,收到 `final_answer` 後以 20 字/秒吐出;等待期間顯示「MAIA 正在讀《工具中文名》…」+ 已過秒數 |
| **W5** | **api 三層** | A | `src/api/{transport,adapters,index}.ts` | mock 換成 fetch。**既有 10 個函式簽名一字不動**(156 項測試靠它);新能力走 `maia.*` 命名空間 |
| **W6** | **SSE 12 事件接進 UI** | B | `src/api/agent.ts` · `ui/chatStore.ts` | 見 §5 的事件表。解析器約 20 行可從 `agent_ui/templates/index.html:2913-2930` 原封不動搬 |
| **W7** | **`#hud-root` 四個 block** | C | `src/hud/**` | 行情條 / 持倉市值 / **agent 狀態+工具晶片** / 資料來源徽章。新增 `tests/hud.mjs` 斷言走動 2 秒期間 `#hud-root` 變動 = 0 |
| **W8** | **DNA 面板** | A | `ui/panels/Dna.tsx` | 六軸雷達 + 淨值曲線 + FIFO 艙位 + 對帳信心。手刻 SVG |
| **W9** | **`maxBot` → `agentChat`** | B | `ui/panels/AgentChat.tsx` | rename + 接真 SSE。要同步改兩處**非凍結檔**:`features/registry.ts` 一行、`maxinfo` zone 的 interactable 一行 |
| **W10** | **demo 腳本 + 三次彩排** | I | — | 含離線完整演練 + 90 秒預錄影片 |

### P1 — 主要得分

| # | 工作包 | 軌 | 說明 |
|---|---|---|---|
| **W11** | **HITL 核准疊層** | B | ⚠️ **不是 Panel。** Panel 會 freeze 世界且 backdrop 蓋掉 HUD 的工具晶片,但核准當下最需要同時看到 agent 剛才查了什麼。做成 `#hud-root` 的非模態疊層 + `setInputCaptured(true)`(欄位已預留) |
| **W12** | **Deck 功能清單** | C | 一張 `FEATURES` 註冊表長出三個介面:`Tab` 快捷格 / `/` 命令面板 / 手機 FAB。**選取後是「傳送 + 走過去 + 自動觸發」**,不是直接開面板 —— 選單是捷徑,世界是容器 |
| **W13** | **`props/kit.ts` + `?gallery=1`** | D | 6–8 支參數化槽位道具(`screenPanel` / `pedestal` / `kiosk` / `archSign` / `dataPillar` / `floorRune`),全部用既有 23 種 Prop 變體組出來。`?gallery=1` 是把所有道具畫在網格上的除錯場景 —— **30 分鐘,全案投報最高,沒有它就談不上讓第二個人碰美術** |
| **W14** | **三個新 zone** | D | `dna`(交易 DNA 檔案室)· `guard`(風控室)· `whatif`(反事實推演室)。⚠️ 中庭自動配位還沒做,新 zone 先不填 `pinned`,用 Deck 進去 |
| **W15** | **風控室** | D+B | **最值得做的一個房間** —— 唯一能把「AI 有煞車」做成實體互動的地方:一支紅色停止拉桿 + 24h 曝險進度條 + 決策台帳。資料完全現成(`live_guard.ledger_summary()`) |
| **W16** | **CSV 資料來源抽屜** | A | 表頭 + 前 20 列 + **797 筆對帳結果** + 可點到 FIFO 軌跡。對一家做合規/信託/ISO 27001 的公司,**主動對帳比任何漂亮數字都更像「這能變成我們的產品」** |
| **W17** | **Boot 進場(8 秒)** | C | 只留「分析取向三選一 + 進入」。**砍掉金鑰輸入**(金鑰本來就該在後端)、**砍掉暱稱輸入**(評審看你打字 5–8 秒)。逃生口用 `Ctrl+Shift+Enter`(**不要用 F9**,macOS 是 Mission Control,按下去整個桌面連沒關的 Slack 一起投影出去) |
| **W18** | **`.kiro/`** | I | +5% 加分項。指定一人只用 Kiro 做文件與簡報,spec-driven 產出當交付物 |

### P2 — 有時間才做

Lv2 唯讀餘額(+5%,與台上真下單解耦)· Bedrock Guardrails 一條 denied topic(~2h,評審最想看的合規展示)· 主動預警(價格穿越 FIFO 均價時推 SSE 到 HUD)· `pro.html` 專業 console

---

## 5. SSE 12 事件契約(整合的核心)

⚠️ `agent-core/docs/FRONTEND_HANDOFF.md` 只列 **6 種**且把 `approval_request` 寫成 `approval`。**照它實作會拿不到串流、開不出核准卡。** 以下是從 `agent/ollama_agent.py` 實際 grep 出來的完整 12 種:

| 事件 | 行號 | payload | 前端落點 |
|---|---|---|---|
| `status` | 403, 465, 610 | `{content, step, max_steps}` | `hud.agent.set({phase:'thinking', note, elapsed})` |
| `persona` | 421 | `{key, name, icon}` | 訊息頭 + 世界裡 NPC 換色 |
| `thinking` / `thought` | 491 / 495 | `{content}` | 可摺疊的「思考過程」 |
| `tool_call` | 509 | `{name, args}` | `hud.agent.steps` push(`ok: null`)+ **NPC 走到對應道具前**(純 canvas) |
| `tool_result` | 540, 544, 548 | `{name, result}` | 對應 step 的 `ok` 落定 + 觸發圖卡 |
| `reader` | 553+ | `{name, injection_detected, flags}` | **`injection_detected` 為 true 時 HUD 閃「已攔截疑似指令注入」** —— AI 設計 15% 的免費得分點,目前完全沒有出口 |
| `approval_request` | 518–525 | `{name, token, plan, hash, summary}` | `hud.approval.set(plan)` + `setInputCaptured(true)` |
| `answer_delta` | 475 | `{content}` | 累積進 paced reveal(**Bedrock 路徑上不會出現**) |
| `answer_reset` | 501 | `{}` | **必須實作** —— 否則小模型「邊講邊呼叫工具」的前導文字會留在畫面上變成假答案 |
| `final_answer` | 628, 636 | `{content}` | 收尾 + `[圖表]` 錨點解析 + 分級免責 |
| `error` | 395, 449, 484 | `{content}` | 帶「重試」,**已串出的字不清掉** |

### 六條紀律

1. **SSE 只在使用者送出時開,絕不在面板 mount 時開。** `harness.mjs` 用 `waitUntil:'networkidle'` —— 一條掛著的 SSE 會讓它永不觸發 → `page.goto` 撞 30s 逾時 → **156 項測試全部記成「套件中斷」**
2. **`?fast=1` 完全不打 SSE**,改吐一組硬編 canned 事件(順便就是錄影腳本)
3. **`AbortController` 綁面板卸載 + 場景切換**(`ZoneRuntime.signal` 已經是這個形狀)
4. **後端補心跳** —— Bedrock 路徑上一輪工具呼叫可能 20–40 秒無事件
5. **`answer_delta` 累積走命令式 `ref.textContent`**,一則訊息收完才 `setState` 一次
6. **`hud.agent` 的 `elapsed` 用 rAF 不用 `setInterval`**

---

## 6. 新增一個 zone / panel 的完整範例

已實測驗證過,照抄即可。

### Zone

`src/world/zones/<id>/index.ts`:

```ts
import { defineZone } from '../../../engine/zone';
import { finish, frontOf } from '../../../engine/kit';
import { door, doorProps, doorPortals } from '../../../engine/doors';

// ⚠️ 門一定要用 door() —— 手寫 portal 的 rect 會被 tests/zones.mjs 抓到
//    (「每道門的觸發區都對齊它的拱門道具」)。門座標只寫一次。
const doors = [door({ id: 'lobby', accent: 'cyan' }, 224, 240, { label: '返回大廳' })];

export const myzone = defineZone({
  id: 'myzone',
  title: '我的房間',
  accent: 'violet',
  build: () => finish({
    id: 'myzone', title: '我的房間',
    w: 480, h: 320,                        // ⚠️ 新 zone 上限 640×384
    accent: 'violet', ambient: '#8890b8', floor: 'tech',
    props: [{ kind: 'terminal', x: 200, y: 120, accent: 'violet' }, ...doorProps(doors)],
    portals: doorPortals(doors),
    interactables: [{ rect: frontOf(200, 120, 56, 44), label: '終端', panel: 'mypanel' }],
    npcs: [], spawn: { x: 240, y: 190 },
  }),
});
```

`src/world/zones/index.ts` 加兩行(import + key)。**完成。**

### Panel

`src/ui/panels/MyPanel.tsx` + `src/ui/panels/index.ts` 加兩行:

```ts
mypanel: definePanel({ id: 'mypanel', title: '我的面板', Component: MyPanel }),
```

`App.tsx` 永遠不用改。打錯字是編譯錯誤:

```
error TS2820: Type '"mypanelll"' is not assignable to type
  '... | "char" | "mypanel"'. Did you mean '"mypanel"'?
```

---

## 7. 現場 Live Demo 已知風險

| 風險 | 處置 |
|---|---|
| **MAX 私有 API 整組 401** —— nonce 只用本機時鐘,筆電睡眠喚醒後漂移,而錯誤訊息完全不指向時鐘 | 前一晚 NTP 同步;demo 腳本第一步放 `get_max_member_info()` 驗簽 |
| **agent 起不來** —— `ollama_agent.py:25-235` 在 module import 時載入全部 72 個 skill,任一 ImportError 整包掛 | 用乾淨機器從 `requirements.txt` 裝一次驗證 |
| **核准 token 找不到** —— 行程內狀態 | `uvicorn --workers 1`,鎖單一實例 |
| **投影機是 1280×720** | `tests/screen.mjs` 補這個尺寸;上台前一天用 HDMI 實際接投影機量 `window.innerWidth` |
| **深色美術投上去糊成一片** —— 會議室投影機黑階是灰的、對比 1000:1 以下 | 做「投影模式」:`room.ambient` 全房間提亮、bloom 拉高、vignette 關掉 |

---

## 8. 三句不能出現在簡報裡的話

1. **「我們用 Strands Agents SDK」** —— 全庫 grep `strands` **零命中**
2. **「我們的大腦是本地 Ollama + gemma4」** —— 那是 `FRONTEND_HANDOFF.md:9` 的舊文,正式路徑是 Bedrock
3. **「我們反向工程了 CoinGlass 的 AES-128-ECB 加密」** —— 已是死碼且有 ToS 風險。改講「我們主動移除了對逆向抓取的依賴,改用可持續的免費第一方來源」

---

## 9. 延伸閱讀

| 文件 | 什麼時候讀 |
|---|---|
| `docs/前端框架規格.md` | 要改前端架構、或想知道某個設計為什麼這樣做 |
| `docs/agent-repo-整合計畫.md` | 要知道 106 個工具怎麼對應到 zone / panel / HUD |
| `docs/架構與實作計畫.md` | 要畫 AWS 架構圖、要寫簡報的技術段 |
| `docs/競賽約束與資源.md` | 要寫「費用/權限/用量」那段(表格可原樣貼) |
| `agent-core/README.md` | 要動 agent 或 skills |
