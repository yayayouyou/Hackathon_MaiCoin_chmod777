"""
工具路由器與 Prompt 瘦身／安全守則的回歸測試
=====================================================
鎖住 Agent 強化成果（確定性、免 LLM）：
  - 工具路由：簡單問題給小子集、分析問題給完整堆疊、永遠含 MAX 報價、永不為空。
  - Prompt 瘦身：system prompt 不再內嵌 69 個工具 schema。
  - 安全守則：G9（禁捏造下單）、G10（抗提示注入）存在於 system prompt。
"""
import pytest

from agent.tool_router import select_tools, select_tool_names, route_intents
from agent.prompts import ALL_TOOLS, get_system_prompt

ALL_NAMES = {t["function"]["name"] for t in ALL_TOOLS}


def names_for(q):
    return {t["function"]["name"] for t in select_tools(q)}


# ── 路由整合性 ─────────────────────────
class TestRouterIntegrity:
    def test_all_selected_names_are_real_tools(self):
        """路由回傳的每個工具都必須真實存在於 ALL_TOOLS。"""
        for q in ["BTC 多少錢", "該不該進場", "什麼是合約", "我的帳戶", "隨便打的字"]:
            assert names_for(q) <= ALL_NAMES

    def test_never_empty_and_core_always_present(self):
        """任何輸入都回傳非空集合，且永遠含 MAX 報價（G6 保證）。"""
        for q in ["", "   ", "asdfghjkl", "早安", "BTC"]:
            sel = names_for(q)
            assert sel, f"空集合: {q!r}"
            assert "get_max_tickers" in sel, f"缺 MAX 報價: {q!r}"

    def test_output_is_subset_not_full(self):
        """簡單問題必須真的收斂（不是回傳全部 69 個）。"""
        assert len(names_for("BTC 現在多少錢？")) < len(ALL_TOOLS)


# ── 各意圖路由正確性 ─────────────────────────
class TestRouterIntents:
    def test_price_query_small_and_focused(self):
        sel = names_for("BTC 現在台幣多少錢？")
        assert len(sel) <= 15
        assert "get_max_tickers" in sel
        assert "create_order" not in sel  # 報價不該掛下單工具
        assert "run_backtest" not in sel

    def test_technical_query(self):
        sel = names_for("給我 ETH 的 4 小時 K 線並算 RSI")
        assert "get_ohlcv" in sel
        assert "calculate_indicators" in sel
        assert len(sel) <= 15

    def test_calculator_query_not_pulled_into_full_analysis(self):
        """『該買多少…停損』是試算，不該展開成完整分析堆疊。"""
        sel = names_for("我有 10 萬，BTC 在 200 萬進場、180 萬停損，這筆該買多少？")
        assert "calculate_position_size" in sel
        assert "create_order" not in sel
        assert len(sel) <= 20

    def test_analysis_gets_full_stack(self):
        """真正的多空決策才展開完整旗艦堆疊（跨情緒/衍生品/技術/量化）。"""
        sel = names_for("幫我完整分析現在 BTC 該不該進場，給我多空評級")
        assert "analysis_full" in route_intents("該不該進場 多空評級")
        assert len(sel) >= 35
        for needed in ["get_ohlcv", "get_aggregated_funding_rate",
                       "get_latest_crypto_news", "detect_market_regime"]:
            assert needed in sel, f"分析堆疊缺 {needed}"

    def test_education_query(self):
        sel = names_for("什麼是資金費率？用白話解釋")
        assert "explain_crypto_term" in sel

    def test_execution_query_has_order_tool(self):
        sel = names_for("幫我市價買入 0.01 顆 BTC")
        assert "create_order" in sel

    def test_account_query(self):
        sel = names_for("看一下我的 MAX 帳戶資產餘額")
        assert "get_max_accounts" in sel


# ── R1：子字串誤匹配（純查詢不得拉進下單/旗艦分析工具）─────────────────────────
class TestRoutingCollisions:
    def test_derivatives_query_no_execution_or_full_stack(self):
        # 「未平倉量」含「平倉」、「多空比」含「多空」，以前誤觸 execution + analysis_full
        q = "昨晚爆倉多少，清算熱力圖、多空比和未平倉量都看一下"
        ints = route_intents(q)
        assert "execution" not in ints and "analysis_full" not in ints
        assert "derivatives" in ints
        assert "create_order" not in names_for(q)

    def test_view_orders_is_account_not_execution(self):
        q = "查一下我的委託單跟成交紀錄"
        assert "execution" not in route_intents(q)
        assert "create_order" not in names_for(q)

    def test_ru_he_does_not_trigger_education(self):
        assert "education" not in route_intents("BTC 大家情緒如何")
        assert "education" not in route_intents("今天台北天氣如何")

    def test_legit_close_position_still_routes_execution(self):
        assert "create_order" in names_for("幫我平倉賣掉 ETH")
        assert "create_order" in names_for("幫我平倉 BTC")

    def test_informational_position_query_not_execution(self):
        # 定義/how-to/風險資訊題不得拉進 create_order（裸『平倉』不再觸發 execution）
        for q in ["什麼是平倉", "如何平倉", "我會不會被平倉", "平倉價怎麼計算"]:
            assert "create_order" not in names_for(q), q

    def test_long_short_ratio_metric_is_derivatives_not_flagship(self):
        # 「多空持倉比/多空單量」是衍生品指標，不該展開旗艦五步堆疊
        for q in ["多空持倉比是多少", "查一下大戶多空持倉比", "多空單量"]:
            ints = route_intents(q)
            assert "analysis_full" not in ints, q
            assert "derivatives" in ints, q

    def test_legit_analysis_still_full_stack(self):
        assert "analysis_full" in route_intents("BTC 該不該進場")

    def test_definitional_and_metric_queries_veto_execution(self):
        # v4 資訊否決：訂單類型/訊號/手續費/賣壓等資訊題不得拉進 create_order（防碰撞 class 重生）
        for q in ["什麼是市價單", "什麼是限價單", "什麼是買入訊號",
                  "市價單手續費多少", "撤單要手續費嗎", "現在賣壓大嗎", "現在買一的掛單量多少"]:
            assert "create_order" not in names_for(q), q

    def test_colloquial_commands_route_execution(self):
        # v4 放寬動作詞：口語買賣/平倉命令都要接住
        for q in ["買 0.01 顆 BTC", "賣 0.5 ETH", "全部平倉", "撤掉那張單",
                  "市價買 0.01 BTC", "強制平倉我的多單", "買入 0.1 BTC"]:
            assert "create_order" in names_for(q), q

    def test_opinion_questions_dont_expose_order_tools(self):
        # 建議/意見題（該不該買入/值得平倉嗎）不得曝露下單工具，但要保留旗艦分析
        for q in ["該不該買入 BTC", "值得買入嗎", "該不該平倉", "值得建倉嗎"]:
            assert "create_order" not in names_for(q), q
        assert "analysis_full" in route_intents("該不該買入 BTC")

    def test_cancel_and_liquidate_phrasings_route_execution(self):
        # 常見撤單/清倉口語都要接住（先前『取消訂單』會漏接）
        for q in ["取消訂單", "取消委託", "清倉", "賣光"]:
            assert "create_order" in names_for(q), q


# ── Prompt 瘦身回歸 ─────────────────────────
class TestPromptSlimming:
    def test_no_embedded_tool_schemas(self):
        """system prompt 不應再內嵌整包工具 schema（避免與原生 tools 重複送出）。"""
        prompt = get_system_prompt("default")
        embedded = sum(1 for t in ALL_TOOLS
                       if (t["function"].get("description") or "")[:18] in prompt)
        assert embedded == 0, f"仍有 {embedded} 個工具描述殘留在 prompt"
        assert len(prompt) < 12000  # 瘦身後應遠小於原本的 ~45000

    def test_tool_calling_protocol_still_present(self):
        prompt = get_system_prompt("default")
        assert "<tool_calling_protocol>" in prompt
        assert "自然語言回答" in prompt  # 不相關就別硬湊工具


# ── 安全守則回歸 ─────────────────────────
class TestSafetyGuardrails:
    def test_g9_no_fake_order(self):
        prompt = get_system_prompt("default")
        assert 'id="G9"' in prompt
        assert "捏造下單" in prompt
        assert "create_order" in prompt

    def test_g10_injection_resistance(self):
        prompt = get_system_prompt("default")
        assert 'id="G10"' in prompt
        assert "RISK_MODE" in prompt
        assert "提示注入" in prompt or "越權" in prompt


# ── 免費獨家新能力的路由涵蓋（大盤/跨所多空/爆倉價位/預測資金費）─────────────
class TestFreeExclusiveRouting:
    def test_market_overview_routes_home_stats(self):
        assert "get_coinglass_home_stats" in select_tool_names("幫我看一下大盤現在氣氛怎樣")
        assert "get_coinglass_home_stats" in select_tool_names("市場總覽 整體行情如何")

    def test_retail_long_short_routes_coinalyze(self):
        for q in ("散戶現在偏多還偏空", "現在全市場散戶擁擠嗎"):
            assert "get_coinalyze_long_short_ratio" in select_tool_names(q)

    def test_liquidation_levels_route_heatmap(self):
        assert "get_coinglass_liquidation_heatmap" in select_tool_names("現在有沒有要爆掉的關鍵價位")

    def test_predicted_funding_routes(self):
        assert "get_coinalyze_predicted_funding" in select_tool_names("下一期資金費會怎樣")
        assert "get_coinalyze_predicted_funding" in select_tool_names("預測資金費率")

    def test_etf_flow_routes(self):
        assert "get_coinglass_etf_flow" in select_tool_names("ETF 資金是流入還流出")


class TestColloquialBacktestRecall:
    """口語化回測/運算問句必須把 run_signal_backtest / run_analysis 送到模型面前
    （活體 E2E 發現：口語問句只命中 derivatives/intel，回測引擎叫不到 → 已補口語線索）。"""

    def test_colloquial_signal_backtest_routes(self):
        for q in [
            "以前每次大家都超怕、恐慌指數超低的時候硬著頭皮買，一週後通常是賺還是賠",
            "資金費率貴到追多的人都在倒貼錢，過往這樣之後容易回檔嗎",
            "那個未平倉突然暴衝上去之後，以前這樣之後幾天大多怎麼走",
            "爆量急殺完之後接下來幾天會不會彈回來",
            "一直創新高追進去，之後通常還會繼續漲嗎",
            "跌到超賣區接刀，事後回頭看勝率高不高",
            "現在算便宜還貴？以前每次跌到這種便宜區間之後抱一段報酬好不好",
        ]:
            assert "run_signal_backtest" in names_for(q), q

    def test_colloquial_run_analysis_routes(self):
        for q in [
            "幫我數一下過去三個月 btc 有幾天單日漲超過 5%",
            "恐懼指數跟幣價是不是反著走的，算個相關係數給我",
            "btc eth sol 最近一個月誰最強幫我排個序",
            "幫我算 btc 最近三個月的標準差跟最大回撤",
        ]:
            assert "run_analysis" in names_for(q), q

    def test_no_regression_simple_queries_stay_lean(self):
        # 口語線索不得污染簡單報價/技術/試算題
        assert "analytics" not in route_intents("給我 ETH 的 4 小時 K 線並算 RSI")
        assert "analytics" not in route_intents("btc 現在多少錢")
        assert "run_signal_backtest" not in names_for("eth 現在技術面怎樣有沒有超買超賣")
