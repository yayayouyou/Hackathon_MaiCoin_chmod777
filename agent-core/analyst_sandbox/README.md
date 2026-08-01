# Analyst Sandbox — 唯讀分析沙盒（Code-as-Action，安全版）

> 讓 agent 能「臨場撰寫 Python 分析程式」組合現有 skills 校驗任意想法（處理沒有現成工具的 edge case），
> 但**生成的程式永遠碰不到金鑰與下單**——分析與執行之間一道硬牆。

## 為什麼要這個

目前 agent 是 **tool-calling**：只能在預先定義好的固定工具選單裡挑。但使用者的想法是長尾的
（「回測恐懼且資金費負、但只在 BTC.D 下降的月份」——沒有這個工具）。Claude Code 之所以強，
是因為它能**臨場寫程式**把積木自由組合。這個沙盒把那份彈性帶進來，**但只給「分析」、不給「執行」**。

## 架構：三層 + 一道硬牆

```
  父行程（agent，持有金鑰）
  ┌──────────────────────────────────────────────┐
  │ sandbox.run_analysis(code)                     │
  │   1. 產生一對 socket（socketpair）              │
  │   2. 以【乾淨環境 env】啟動子行程（無任何金鑰）    │
  │   3. 把 code 從 stdin 送進子行程                 │
  │   4. 迴圈服務子行程的 skill 請求（broker）        │
  │      · broker 驗證 skill ∈ 唯讀白名單            │
  │      · 在【父行程】用金鑰執行 skill              │
  │      · 只把「資料結果」(JSON) 回給子行程         │
  │   5. 逾時 / 資源上限 → 殺掉子行程                │
  └──────────────────────────────────────────────┘
            ║ socketpair（唯一通道，只傳「資料」）
  ┌──────────────────────────────────────────────┐
  │ runner.py（沙盒子行程 · 無金鑰 · 無網路*）        │
  │   · 受限 exec：無 __import__ / open / eval /     │
  │     compile / input（無法 import socket/os/…）   │
  │   · 命名空間：np / pd / math / statistics +      │
  │     call_skill(name, **kwargs) + 安全 builtins   │
  │   · 使用者 code 把結果賦值給變數 `result`         │
  └──────────────────────────────────────────────┘
```

**硬牆**：下單 / 撤單 / 金鑰 / 私有帳戶讀取 **不在白名單**，且金鑰**物理上不存在於子行程**
（乾淨 env）。生成的程式最多只能取得**公開市場資料**並做運算——錯了、被注入了，也不會虧錢、不會外洩金鑰。

## 安全模型（Threat Model）

| 威脅 | 防護 |
|---|---|
| 生成程式外洩 API 金鑰 | 子行程以**乾淨 env 啟動**（無任何金鑰）；skill 在**父行程**執行，只回資料。金鑰不進沙盒。 |
| 生成程式下單/動用資金 | 下單/撤單/寫入/私有帳戶 skill **不在白名單**；沙盒無 order 能力。執行層完全隔離。 |
| `import os/socket/urllib/requests` 竊取/外連 | **受控 `__import__`**：只放行『純運算』白名單庫；I/O/系統/網路庫一律 `ImportError`。 |
| `open()` 讀本機檔 | 受限 builtins **移除 `open`**。 |
| `eval/exec/compile` 繞過 | 受限 builtins **移除**。 |
| 無窮迴圈 / 記憶體炸彈 | 父行程**逾時**殺行程 + 子行程 **RLIMIT_CPU / RLIMIT_AS** 上限。 |
| 巨大輸出灌爆 | 結果與 stdout **截斷上限**（JSON 大小上限）。 |
| 沙盒被完全攻破（未知逃逸） | 子行程**無金鑰、cwd=臨時目錄、資源受限**；能取得的只有公開市場資料，輸出只回到使用者自己的 agent。爆炸半徑極小。 |

### 已知限制（誠實）
- **numpy/pandas 殘留面**：`pd.read_csv(url/path)` 理論上可讀檔或外連。影響評估為**低**——沙盒無金鑰、
  可取得的只有公開資料、輸出只回使用者自己。生產環境（Linux）應再加 **network namespace 隔離**
  （本模組已在 Linux 以 `unshare(CLONE_NEWNET)` best-effort 阻斷外連；macOS 開發機無此保證）。
- **CPython `exec` 沙盒**對「刻意對抗式」程式非萬能（dunder 逃逸）。本設計不單靠語言層，而是靠
  **無金鑰 + 行程隔離 + 資源上限 + 公開資料面**把爆炸半徑壓到最小。
- 本地 12B 模型寫的程式**品質有限**：因此沙盒只暴露**已驗證的高階函式**（我們的 skills / 回測引擎 /
  指標），讓模型「組裝」而非「從零寫統計」，降低出錯空間。

## 可用的庫（能力範圍）

- **預先注入**（不 import 也能直接用）：`np`(numpy)、`pd`(pandas)、`math`、`statistics`、
  `datetime`、`collections`、`itertools`、`functools`、`re`、`json`、`random`。
- **可 import 的純運算白名單**：上述 + `operator`、`decimal`、`fractions`、`heapq`、`bisect`、
  `cmath`、`scipy`／`statsmodels`／`sklearn`（若已安裝）。
- **一律禁止 import**：`os`、`sys`、`socket`、`subprocess`、`requests`、`urllib`、`pathlib`、
  `io`、`shutil`、`importlib`、`ctypes`… 等 I/O/系統/網路庫（回清楚的 `ImportError`）。
- **執行環境**：與父行程**同一個 venv**（共用已裝套件），但以獨立行程 + 乾淨 env（無金鑰）+
  受控 import + 資源上限隔離。因 import 受控，同 venv 已足夠；若要更嚴（如允許任意 import），
  才需另建 minimal venv + OS 級隔離（生產硬化）。

能力範圍：numpy/pandas 已涵蓋絕大多數量化分析（相關/回歸/滾動/分位/線代），加上 `call_skill`
可取任一唯讀資料，足以組合出「沒有現成工具」的長尾分析。

## 使用（LLM 工具 `run_analysis`）

agent 撰寫 Python，用 `call_skill(name, **kwargs)` 取資料、`np/pd/math` 運算，把結論賦值給 `result`：

```python
# 例：近 100 天恐懼貪婪的平均與極值
fng = call_skill("get_crypto_fear_and_greed_index", limit=100)
vals = [h["value"] for h in fng["history"]]
result = {"avg": sum(vals) / len(vals), "min": min(vals), "max": max(vals)}
```

## 檔案
- `broker.py` — 唯讀 skill 白名單 + 執行 + JSON 淨化（**父行程**，金鑰留在這）。
- `runner.py` — 沙盒子行程進入點（受限 exec + `call_skill` RPC）。
- `sandbox.py` — `run_analysis()` 主 API（啟動子行程、服務 broker、逾時/資源上限）。
