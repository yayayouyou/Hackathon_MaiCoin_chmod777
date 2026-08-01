"""
agent/tool_concepts.py — 工具「概念 / 範例問句」對照表（Document Expansion 用）
=====================================================
研究依據：工具檢索命中率低多半是「工具描述太少 (tools are under-documented)」——
只用一句描述做 embedding，和使用者口語 query 的語意落差大。主流解法（Re-Invoke /
Tool2Vec / Document Expansion）是把「概念標籤 + 同義詞 + 範例問句」一起編碼，
讓工具向量更貼近「使用者會怎麼問」。

用法：expand_tool_text(name, description) 會把描述 + 概念 + 範例串成一段「擴充文件」
給 tool_embeddings 做索引。沒登錄的工具就用原描述（優雅退化），可漸進補齊。

維護：新增工具時在此加一列 {concepts, examples} 就能提升命中，不必再手動養路由關鍵字。
"""
import os
import json
from typing import Dict, List, Optional

# tool_name -> {"concepts": [...同義概念...], "examples": [...使用者會怎麼問...]}
TOOL_CONCEPTS: Dict[str, Dict[str, List[str]]] = {
    # ── 行情 / 市場 ──
    "get_max_tickers": {
        "concepts": ["現價", "報價", "多少錢", "幣價", "行情", "現在價格", "成交價"],
        "examples": ["現在比特幣多少", "BTC 台幣多少錢", "ETH 現在報價", "MAX 幣現在多少錢", "現在的價格"],
    },
    "get_max_index_prices": {
        "concepts": ["指數價", "標記價", "mark price", "清算基準價", "跨所加權價"],
        "examples": ["BTC 標記價多少", "現在的指數價格", "ETH/USDT 指數價"],
    },
    "get_max_currencies": {
        "concepts": ["幣種資訊", "提幣手續費", "可否質押", "走哪條鏈", "區塊鏈網路", "最低提幣量", "是否需要memo"],
        "examples": ["USDT 提幣手續費多少", "哪些幣可以質押", "MAX 走哪條鏈提幣", "提幣最低多少", "BTC 提幣要多少手續費"],
    },
    "get_max_depth": {
        "concepts": ["盤口", "買賣盤", "掛單量", "訂單簿深度"],
        "examples": ["BTC 買一賣一", "現在盤口多深", "訂單簿"],
    },
    # ── 帳戶：餘額 / 手續費 / 融資 ──
    "get_max_accounts": {
        "concepts": ["餘額", "資產", "持倉", "我有多少幣", "錢包餘額", "身家", "帳戶總覽"],
        "examples": ["我的餘額", "我帳戶有多少資產", "查我的持倉", "show my balance", "我現在有多少錢", "我錢包裡有什麼幣"],
    },
    "get_max_member_info": {
        "concepts": ["手續費等級", "VIP等級", "會員等級", "費率", "折扣", "maker taker 費率"],
        "examples": ["我的手續費多少", "我是 VIP 幾", "我可以打幾折", "我的費率等級", "我這帳號等級可以打幾折", "交易手續費率"],
    },
    "get_max_ad_ratio": {
        "concepts": ["融資維持率", "清算風險", "負債比", "margin 健康度", "會不會被清算"],
        "examples": ["我的融資維持率", "我會不會被清算", "融資帳戶健康嗎", "我的負債比"],
    },
    "get_max_interest_rates": {
        "concepts": ["融資利率", "借幣利率", "資金成本", "年化利率", "借錢利息"],
        "examples": ["借 USDT 利率多少", "融資年化利率多少", "借幣成本", "借 BTC 一天多少利息"],
    },
    # ── 帳戶：訂單 / 成交 ──
    "get_max_orders": {
        "concepts": ["我的委託", "掛單", "未成交訂單", "掛單中"],
        "examples": ["我的掛單", "我有哪些委託", "還沒成交的訂單", "查我的委託單"],
    },
    "get_max_order_history": {
        "concepts": ["歷史訂單", "過去的委託", "已完成訂單"],
        "examples": ["我的歷史訂單", "以前的委託紀錄", "已撤銷的單"],
    },
    "get_max_my_trades": {
        "concepts": ["成交紀錄", "成交歷史", "我買賣過什麼", "實際成交"],
        "examples": ["我的成交紀錄", "我最近成交了什麼", "我買賣過哪些", "我的交易歷史"],
    },
    # ── 帳戶：資金動態 ──
    "get_max_fund_transactions": {
        "concepts": ["入金", "出金", "提幣", "充值", "提現", "現貨與融資錢包互轉", "資金流水", "資金異動"],
        "examples": ["我上次入金多少", "我提幣到哪個地址", "現貨轉融資的紀錄", "我的出金紀錄", "我最近充值提現"],
    },
    "get_max_converts": {
        "concepts": ["閃兌", "幣幣兌換", "換幣", "swap", "把一種幣換成另一種", "即時兌換", "閃電兌換"],
        "examples": ["我的閃兌記錄", "我把台幣換成 MAX 的紀錄", "換幣歷史", "我閃兌過哪些", "把 BTC 換成 USDT 的紀錄"],
    },
    "get_max_withdraw_addresses": {
        "concepts": ["提幣白名單", "提幣地址", "地址簿", "可提幣的地址"],
        "examples": ["我的提幣白名單", "USDT 可以提到哪些地址", "我設定過哪些提幣地址"],
    },
    "get_max_internal_transfers": {
        "concepts": ["站內轉帳", "MAX 用戶互轉", "轉給朋友"],
        "examples": ["站內轉帳紀錄", "我轉給別人的紀錄", "別人轉給我的"],
    },
    # ── 回測 / 量化 ──
    "run_signal_backtest": {
        "concepts": ["策略勝率", "訊號回測", "以前每次都", "歷史統計行為", "訊號出現後會漲嗎"],
        "examples": ["這個訊號以前勝率多少", "RSI 超賣買進以前賺嗎", "以前每次golden cross後會漲嗎", "這樣做過去賺還是賠"],
    },
    "backtest_strategy": {
        "concepts": ["回測策略", "策略績效", "一站式回測"],
        "examples": ["回測一個 MACD 策略", "均線交叉策略績效如何", "幫我回測 BTC 策略"],
    },
    # ── 衍生品 ──
    "get_aggregated_funding_rate": {
        "concepts": ["資金費率", "funding rate", "永續合約費率"],
        "examples": ["BTC 資金費率多少", "現在資金費率", "永續費率"],
    },
    "get_coinglass_liquidation_chart": {
        "concepts": ["爆倉", "清算", "清算熱力圖", "多空爆倉"],
        "examples": ["昨天爆倉多少", "清算熱力圖", "有很多人被爆倉嗎"],
    },
    # ── 情緒 / 情報 ──
    "get_latest_crypto_news": {
        "concepts": ["新聞", "消息", "利多利空", "最新動態"],
        "examples": ["最新加密新聞", "有什麼消息", "今天幣圈發生什麼"],
    },
    "get_crypto_fear_and_greed_index": {
        "concepts": ["恐慌貪婪指數", "市場情緒", "fear greed"],
        "examples": ["恐慌貪婪指數", "現在市場情緒", "大家在恐慌還是貪婪"],
    },
    "analyze_sentiment_divergence": {
        "concepts": ["菁英vs群眾", "聰明錢與散戶背離", "名人與大眾情緒差", "背離訊號"],
        "examples": ["菁英跟散戶對BTC看法一致嗎", "現在有沒有情緒背離", "聰明錢跟散戶方向一樣嗎", "大戶跟散戶誰比較樂觀"],
    },
    "analyze_influence_decay": {
        "concepts": ["名人喊單影響力", "影響力半衰期", "喊單效力衰退", "川普喊加密還有用嗎"],
        "examples": ["川普喊加密的影響力變弱了嗎", "名人喊單還有用嗎", "川普發文對BTC還有影響嗎", "喊單效力是不是下降了"],
    },
    "get_smart_money_flow": {
        "concepts": ["聰明錢", "鏈上資金流", "買賣壓", "偷偷累積", "誰在買", "smart money", "on-chain flow"],
        "examples": ["聰明錢在買WIF嗎", "鏈上有沒有人在累積PEPE", "BONK買盤強不強", "有人在偷偷買嗎", "這幣鏈上資金流向"],
    },
    "validate_smart_money_signal": {
        "concepts": ["訊號驗證", "真訊號還是噪音", "資金流入歷史有效性", "這訊號可靠嗎", "signal validation"],
        "examples": ["聰明錢在買PEPE這訊號可靠嗎", "PEPE有量進場後歷史上真的漲嗎", "這是真訊號還是噪音", "WIF的買盤訊號準嗎"],
    },
    "run_token_due_diligence": {
        "concepts": ["盡職調查", "代幣綜合分析", "能不能碰", "進場前檢查", "due diligence", "一鍵分析"],
        "examples": ["幫我盡職調查PEPE", "WIF能不能碰", "進場前幫我看一遍這幣", "PEPE綜合分析一下", "這幣值不值得進"],
    },
    "trace_deposit_source": {
        "concepts": ["入金來源", "資金溯源", "來路不明資金", "錢從哪來", "入金鏈上來源", "AML"],
        "examples": ["我這些入金是從哪來的", "有沒有來路不明的錢", "我的入金來源可靠嗎", "這筆入金是從哪個錢包來的", "幫我查入金來源"],
    },
    # ── 交易 DNA 面板（六軸雷達 / 淨值曲線 / 反事實）──
    "get_trading_dna_score": {
        "concepts": ["交易性格", "交易風格", "投資風格", "交易個性", "archetype", "人格標籤",
                     "六軸分數", "雷達圖", "交易畫像", "我是哪種交易者", "哪一項最弱"],
        "examples": ["我是什麼類型的交易者", "分析我的交易個性", "幫我畫交易性格雷達圖",
                     "我的投資風格是什麼", "我哪一軸最弱", "我的交易DNA是什麼", "我這一年交易得怎麼樣"],
    },
    "get_equity_curve": {
        "concepts": ["淨值曲線", "資產曲線", "資產走勢", "淨值變化", "最大回撤", "drawdown",
                     "資產這一年怎麼變", "期初期末", "峰值淨值"],
        "examples": ["我的資產這一年怎麼變化", "幫我畫淨值曲線", "我最大回撤是多少",
                     "我的資產走勢圖", "這一年我的淨值變化如何", "我的資產從年初到現在變多少"],
    },
    "compare_sell_vs_hold": {
        "concepts": ["反事實", "如果不賣", "買了就抱", "續抱", "頻繁進出值不值得",
                     "手續費侵蝕", "主動交易成本", "機會成本"],
        "examples": ["如果當初不賣會怎樣", "我如果都不賣會怎樣", "買了就抱是不是比較好",
                     "頻繁進出到底有沒有賺到", "我的手續費花了多少", "主動交易划算嗎"],
    },
    "load_demo_account_ledger": {
        "concepts": ["示範帳戶", "範例帳戶", "訪客模式", "還沒綁帳號", "先看範例", "帳本健檢"],
        "examples": ["我還沒綁帳號可以先看個範例嗎", "給我看示範帳戶", "先用範例資料試試",
                     "沒有帳號可以體驗嗎", "這份帳本資料乾淨嗎"],
    },
}


# LLM 自動生成的範例問句（agent/gen_tool_examples.py 產出），與手寫概念表併用
_AUTO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tool_examples_auto.json")
_auto_cache: Optional[Dict[str, List[str]]] = None


def _looks_ok(e: str) -> bool:
    """過濾 LLM（gemma4）生成的壞範例：真實 query 很短，壞的多是過長囉嗦、含程式碼/JSON 殘渣、
    或重複迴圈（如「對比對比對比…」）。壞範例進索引會污染工具向量、反而降低命中，寧可丟掉。"""
    if not (3 <= len(e) <= 28):                              # 真人 query 短；過長多是囉嗦/幻覺
        return False
    if any(x in e for x in ("*", "\n", "`", "{", "}", "json", "http", "「「", "。。")):
        return False
    for w in (2, 3, 4):                                      # 連續重複子字串 ≥3 次
        for i in range(len(e) - w):
            if e[i:i + w] * 3 in e:
                return False
    return True


def _auto_examples() -> Dict[str, List[str]]:
    global _auto_cache
    if _auto_cache is None:
        try:
            with open(_AUTO_PATH, encoding="utf-8") as f:
                raw = json.load(f)
            _auto_cache = {
                k: [e for e in (v.get("examples") or []) if _looks_ok(e)]
                for k, v in raw.items()
            }
        except Exception:  # noqa: BLE001
            _auto_cache = {}
    return _auto_cache


def expand_tool_text(name: str, description: str) -> str:
    """Document Expansion：描述 + 手寫概念 + 範例問句（手寫優先，併入 LLM 自動生成的範例）。
    無任何登錄則回原描述（優雅退化）。"""
    base = f"{name}：{description or ''}"
    meta = TOOL_CONCEPTS.get(name) or {}
    concepts = meta.get("concepts") or []
    examples = list(meta.get("examples") or [])
    for e in _auto_examples().get(name, []):        # 併入自動範例（去重）
        if e not in examples:
            examples.append(e)
    if not concepts and not examples:
        return base
    parts = [base]
    if concepts:
        parts.append("概念：" + "、".join(concepts))
    if examples:
        parts.append("使用者會這樣問：" + " / ".join(examples[:14]))   # 上限避免索引文件過長
    return "\n".join(parts)
