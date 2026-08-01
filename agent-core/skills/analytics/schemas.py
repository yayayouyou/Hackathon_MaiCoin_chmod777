"""
skills/analytics/schemas.py

模塊五：技術分析與回測 Tool JSON Schema 定義
=============================================
定義本模塊所有函數的 OpenAI-compatible JSON Schema。
"""

# ──────────────────────────────────────────────
#  Schema 1：calculate_indicators
# ──────────────────────────────────────────────
CALCULATE_INDICATORS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "calculate_indicators",
        "description": (
            "傳入歷史 K 線列表數據，計算移動平均線 (MA, EMA)、相對強弱指標 (RSI)、"
            "平滑異同移動平均線 (MACD)、布林通道 (Bollinger Bands) 與真實波幅均值 (ATR)。"
            "提供趨勢、超買/超賣與交叉的多空診斷信號。"
            "例如：'幫我分析一下這個 K 線數據的技術指標' 或 '這對代幣是黃金交叉還是死亡交叉？'"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "klines": {
                    "type": "array",
                    "description": "K 線數據列表，格式為：[[timestamp, open, high, low, close, volume], ...]。至少需要 30 根 K 線。",
                    "items": {
                        "type": "array"
                    }
                }
            },
            "required": ["klines"]
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 2：run_backtest
# ──────────────────────────────────────────────
RUN_BACKTEST_SCHEMA = {
    "type": "function",
    "function": {
        "name": "run_backtest",
        "description": (
            "傳入歷史 K 線列表數據，執行特定策略的歷史回測模擬。"
            "返回績效指標（如總收益率、基準收益率、勝率與最大回撤百分比）以及近期成交明細。"
            "支援均線交叉 (ma_crossover) 與 RSI 逆勢 (rsi_reversal) 策略。"
            "例如：'用 10,30 均線交叉策略回測這組 BTC 數據' 或 '測試一下 RSI 逆勢策略在這組 K 線上的表現'"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "klines": {
                    "type": "array",
                    "description": "歷史 K 線列表 [[timestamp, open, high, low, close, volume], ...]。至少需要 30 根 K 線。",
                    "items": {
                        "type": "array"
                    }
                },
                "strategy_name": {
                    "type": "string",
                    "description": "回測使用的策略名稱",
                    "enum": ["ma_crossover", "rsi_reversal"],
                    "default": "ma_crossover"
                },
                "strategy_params": {
                    "type": "object",
                    "description": (
                        "策略參數。若為 'ma_crossover' 可傳入：{'fast_period': 10, 'slow_period': 30}；"
                        "若為 'rsi_reversal' 可傳入：{'rsi_period': 14, 'oversold': 30, 'overbought': 70}"
                    )
                },
                "initial_capital": {
                    "type": "number",
                    "description": "初始本金價值，預設為 10000.0 USD",
                    "default": 10000.0
                },
                "fee_rate": {
                    "type": "number",
                    "description": "單邊成交手續費比例，例如 0.001 代表 0.1% 費率",
                    "default": 0.001
                }
            },
            "required": ["klines"]
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 2b：backtest_strategy（一站式：內部自動抓 K 線）
# ──────────────────────────────────────────────
BACKTEST_STRATEGY_SCHEMA = {
    "type": "function",
    "function": {
        "name": "backtest_strategy",
        "description": (
            "一站式策略回測：只要提供交易對與策略名稱，系統會【自動抓取 K 線】並執行回測，"
            "你【不需要】先呼叫 get_ohlcv 再把大量 K 線陣列傳進來（那樣容易逾時或出錯）。"
            "支援均線交叉 (ma_crossover) 與 RSI 逆勢 (rsi_reversal)。回傳績效（總報酬/超額/勝率/最大回撤）、"
            "近期成交，以及統計穩健性驗證（bootstrap 信賴區間 + walk-forward + 穩健判定）。"
            "使用者說「回測 BTC 過去三個月的均線策略」「測 RSI 逆勢在 ETH 好不好」這類請求時，一律優先用本工具。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "交易對，例如 BTC/USDT、ETH/USDT", "default": "BTC/USDT"},
                "strategy_name": {"type": "string", "enum": ["ma_crossover", "rsi_reversal"],
                                  "description": "策略名稱", "default": "ma_crossover"},
                "strategy_params": {"type": "object",
                                    "description": "策略參數；ma_crossover:{fast_period,slow_period}；rsi_reversal:{rsi_period,oversold,overbought}"},
                "timeframe": {"type": "string", "description": "K 線週期 1h/4h/1d 等；回測『過去數月』建議 1d", "default": "1d"},
                "limit": {"type": "integer", "description": "抓取 K 線根數（至少 30，建議 90~200）", "default": 120},
                "exchange_id": {"type": "string", "description": "交易所，預設 binance", "default": "binance"},
            },
            "required": ["symbol"]
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 3：save_strategy
# ──────────────────────────────────────────────
SAVE_STRATEGY_SCHEMA = {
    "type": "function",
    "function": {
        "name": "save_strategy",
        "description": "保存或更新自定義的交易策略配置（如均線交叉、RSI），包含策略參數、預設交易對與時間週期。",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "策略名稱，唯一標識符（例如 'btc_ma_fast'）"
                },
                "strategy_type": {
                    "type": "string",
                    "description": "策略類型",
                    "enum": ["ma_crossover", "rsi_reversal"]
                },
                "params": {
                    "type": "object",
                    "description": "策略配置參數，例如雙均線的 {'fast_period': 5, 'slow_period': 20}"
                },
                "description": {
                    "type": "string",
                    "description": "關於策略的描述"
                },
                "symbol": {
                    "type": "string",
                    "description": "預設交易對符號（如 'BTC/USDT'）",
                    "default": "BTC/USDT"
                },
                "timeframe": {
                    "type": "string",
                    "description": "預設時間週期（如 '1h'）",
                    "default": "1h"
                }
            },
            "required": ["name", "strategy_type", "params"]
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 4：list_strategies
# ──────────────────────────────────────────────
LIST_STRATEGIES_SCHEMA = {
    "type": "function",
    "function": {
        "name": "list_strategies",
        "description": "查詢並列出所有已保存的自定義交易策略配置清單。",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 5：run_backtest_on_saved_strategy
# ──────────────────────────────────────────────
RUN_BACKTEST_ON_SAVED_STRATEGY_SCHEMA = {
    "type": "function",
    "function": {
        "name": "run_backtest_on_saved_strategy",
        "description": "根據指定的策略名稱，自動加載存儲參數、抓取行情數據並運行歷史回測。",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "要加載的已保存策略名稱（如 'btc_ma_fast'）"
                },
                "exchange_id": {
                    "type": "string",
                    "description": "使用的行情交易所（如 'binance', 'bybit', 'okx'）",
                    "default": "binance"
                },
                "limit": {
                    "type": "integer",
                    "description": "獲取的 K 線歷史長度，預設 150",
                    "default": 150
                }
            },
            "required": ["name"]
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 6：run_twitter_mention_backtest
# ──────────────────────────────────────────────
RUN_TWITTER_MENTION_BACKTEST_SCHEMA = {
    "type": "function",
    "function": {
        "name": "run_twitter_mention_backtest",
        "description": (
            "【免 Key 名人事件研究回測】分析特定 X 名人（如 elonmusk）近期推文，提及某加密貨幣即"
            "『於推文後下一根 K 線開盤買入』（杜絕前視偏誤），持有指定小時後平倉。"
            "回傳：相對 BTC 大盤的『異常報酬 (abnormal_vs_btc)』、多個持有期 (1h/4h/Nh) 的勝率與平均、"
            "以及『排列檢定 p 值 (permutation_test)』判斷是否只是運氣，並附樣本數/價格涵蓋範圍等誠實揭露。"
            "重要：名人事件樣本通常很小、方差大，p>0.1 代表與隨機無異，結論僅供參考、不可當交易依據。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "交易對符號（如 'DOGE/USDT', 'BTC/USDT'）"
                },
                "screen_name": {
                    "type": "string",
                    "description": "追蹤的推特帳號，預設為 'elonmusk'",
                    "default": "elonmusk"
                },
                "keywords": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "description": "自定義提及關鍵字列表，不填時自動根據 symbol base 對應代入（例如 DOGE 代入 'doge', 'dogecoin'）"
                },
                "hold_hours": {
                    "type": "integer",
                    "description": "買入後的持倉小時數，預設為 24 小時",
                    "default": 24
                },
                "exchange_id": {
                    "type": "string",
                    "description": "獲取行情的交易所，預設為 'binance'",
                    "default": "binance"
                }
            },
            "required": ["symbol"]
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 7：detect_market_regime
# ──────────────────────────────────────────────
DETECT_MARKET_REGIME_SCHEMA = {
    "type": "function",
    "function": {
        "name": "detect_market_regime",
        "description": "分析資產當前的市場體制 (Market Regime)，包含移動平均線趨勢、波動率 (ATR) 與 RSI 指標，分類為牛市、熊市、震盪或極端波動，並給出策略建議。",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "交易對符號（如 'BTC/USDT'）"
                },
                "timeframe": {
                    "type": "string",
                    "description": "K 線週期（如 '1d', '4h'），預設 '1d'",
                    "default": "1d"
                },
                "exchange_id": {
                    "type": "string",
                    "description": "交易所名稱（如 'binance'），預設 'binance'",
                    "default": "binance"
                }
            },
            "required": ["symbol"]
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 8：analyze_portfolio
# ──────────────────────────────────────────────
ANALYZE_PORTFOLIO_SCHEMA = {
    "type": "function",
    "function": {
        "name": "analyze_portfolio",
        "description": "追蹤與分析加密貨幣投資組合，計算多個資產間的皮爾森相關係數矩陣，檢測是否過度集中並給出風險評估與調倉建議。",
        "parameters": {
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "投資組合中的資產列表（如 ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']）"
                },
                "timeframe": {
                    "type": "string",
                    "description": "K 線週期，預設 '1d'",
                    "default": "1d"
                }
            },
            "required": ["symbols"]
        }
    }
}

# ──────────────────────────────────────────────
# ──────────────────────────────────────────────
#  Schema：run_analyst_desk（系統化分析師桌 — 旗艦多空決策）
# ──────────────────────────────────────────────
RUN_ANALYST_DESK_SCHEMA = {
    "type": "function",
    "function": {
        "name": "run_analyst_desk",
        "description": (
            "【旗艦多空決策】對單一標的跑完整專業投研流程：由上而下 5 層（宏觀/資金流/部位/情緒/技術）"
            "各自系統化評分 → 共振與『背離』偵測 → 論點 + 失效價位 + 風險控管建議。"
            "使用者問『該不該進場 / 完整分析 / 多空決策 / 值得買嗎』時，優先呼叫此工具取得結構化結論，再用你的人格口吻綜合敘述。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "標的，如 'BTC','ETH'"},
                "timeframe": {"type": "string", "description": "K 線週期（預設 4h）",
                              "enum": ["1h", "4h", "1d"], "default": "4h"},
            },
            "required": ["symbol"]
        }
    }
}

# ──────────────────────────────────────────────
#  Schema：run_signal_backtest（組合式訊號回測 — 通用接口）
# ──────────────────────────────────────────────
RUN_SIGNAL_BACKTEST_SCHEMA = {
    "type": "function",
    "function": {
        "name": "run_signal_backtest",
        "description": (
            "【組合式回測接口】把『任一訊號事件』回測其後的價格影響——量測事件後 N 天報酬並與隨機進場基準比較（異常報酬）。"
            "不同 skill 的訊號都能插入回測。使用者問『某訊號發生後價格會不會漲/跌、某條件下買入的歷史績效、"
            "企業增持/ETF流入/極度恐懼/資金費飆高之後行情如何』時使用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "signal": {
                    "type": "string",
                    "description": "訊號名稱",
                    "enum": ["treasury_accumulation", "extreme_fear", "extreme_greed",
                             "etf_inflow", "etf_outflow", "high_funding", "negative_funding",
                             "liquidation_long_flush", "liquidation_short_squeeze", "oi_surge",
                             "mayer_deep", "ahr999_bottom",
                             "momentum_breakout", "oversold_rsi", "vol_spike"],
                },
                "asset": {"type": "string", "description": "回測標的（BTC-only 訊號限 BTC；ETF/資金費/爆倉/價量因子可 BTC/ETH）", "default": "BTC"},
                "hold_days": {"type": "integer", "description": "事件後持有天數（預設 7）", "default": 7},
                "direction": {"type": "string", "description": "覆寫方向（貪婪/擁擠後可測 short）", "enum": ["long", "short"]},
                "ticker": {"type": "string", "description": "（僅 treasury_accumulation）公司代號如 'MSTR'"},
                "threshold": {"type": "number", "description": "覆寫訊號門檻（單位依訊號）"},
            },
            "required": ["signal"]
        }
    }
}

# ──────────────────────────────────────────────
#  Schema：run_composite_backtest（多訊號共振/聯集回測）
# ──────────────────────────────────────────────
RUN_COMPOSITE_BACKTEST_SCHEMA = {
    "type": "function",
    "function": {
        "name": "run_composite_backtest",
        "description": (
            "【組合式回測·多訊號】把多個數據源的訊號『組合』回測——例如「極度恐懼 且 ETF 淨流入」同時成立時買入的歷史績效。"
            "mode='and' 共振(所有訊號在數日內同時觸發)、'or' 聯集(任一觸發)。每個訊號沿用自己的觸發條件。"
            "使用者問『同時滿足多個條件、A 且 B、多重訊號、共振時買入』的回測時使用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "signals": {
                    "type": "array", "minItems": 2,
                    "items": {"type": "string",
                              "enum": ["treasury_accumulation", "extreme_fear", "extreme_greed",
                                       "etf_inflow", "etf_outflow", "high_funding", "negative_funding",
                                       "liquidation_long_flush", "liquidation_short_squeeze", "oi_surge",
                                       "mayer_deep", "ahr999_bottom",
                                       "momentum_breakout", "oversold_rsi", "vol_spike"]},
                    "description": "要組合的訊號名稱（≥2）",
                },
                "mode": {"type": "string", "enum": ["and", "or"], "description": "and=共振同時觸發 / or=任一觸發", "default": "and"},
                "window_days": {"type": "integer", "description": "AND 模式『同時』的日容忍（預設 1）", "default": 1},
                "asset": {"type": "string", "description": "回測標的（預設 BTC）", "default": "BTC"},
                "hold_days": {"type": "integer", "description": "事件後持有天數（預設 7）", "default": 7},
                "direction": {"type": "string", "enum": ["long", "short"], "description": "方向（預設 long）"},
            },
            "required": ["signals"]
        }
    }
}

# ──────────────────────────────────────────────
#  Schema：run_analysis（唯讀分析沙盒 — Code-as-Action）
# ──────────────────────────────────────────────
RUN_ANALYSIS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "run_analysis",
        "description": (
            "【唯讀分析沙盒】當『沒有現成工具』能回答使用者的自訂分析/校驗想法時，你可以臨場撰寫 Python 程式在安全沙盒中執行。"
            "沙盒內可用：call_skill(name, **kwargs) 取任何唯讀資料 skill 的結果、np(numpy)/pd(pandas)/math/statistics 運算。"
            "務必把最終結論賦值給變數 result。沙盒【無網路、無金鑰、無下單能力】，僅供分析。"
            "範例 code：\n"
            "fng = call_skill('get_crypto_fear_and_greed_index', limit=100)\n"
            "vals = [h['value'] for h in fng['history']]\n"
            "result = {'avg': sum(vals)/len(vals), 'min': min(vals)}\n"
            "可 call_skill 的常用資料：get_ticker/get_ohlcv/get_max_tickers(價格)、get_aggregated_funding_rate/"
            "get_coinalyze_long_short_ratio/get_coinglass_liquidation_chart(衍生品)、get_crypto_fear_and_greed_index/"
            "get_btc_treasuries/get_crypto_sector_indices(情緒/資金)、run_signal_backtest/run_composite_backtest/"
            "calculate_indicators(回測/指標)等（下單/私有帳戶不可用）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "要執行的 Python 分析程式；把結論賦值給 result。"},
                "goal": {"type": "string", "description": "這段分析的目的（選填，供記錄）。"},
            },
            "required": ["code"]
        }
    }
}

#  統一工具清單與映射
# ──────────────────────────────────────────────
RECONCILE_HOLDINGS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "reconcile_holdings",
        "description": "資金對帳：把成交、閃兌、獎勵、出入金、站內轉帳等所有流水正規化成事件帳本並重播，"
                       "比對每個幣種『帳本應有數量』vs『交易所實際餘額』，列出差異與成因診斷。"
                       "用於回答：我的持倉紀錄對得上嗎？損益數字可信嗎？錢的流向有沒有缺口？",
        "parameters": {
            "type": "object",
            "properties": {
                "sync": {"type": "boolean",
                         "description": "是否先從 MAX 抓最新流水更新帳本（預設 true）", "default": True},
            },
            "required": [],
        },
    },
}

GET_COST_BASIS_POSITIONS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_cost_basis_positions",
        "description": "取得目前持倉的成本可追溯度：每個幣種的數量（以交易所餘額為準）、其中多少數量能追溯到"
                       "歷史買入成本、多少屬於無法追溯來源（期初或平台未公開流水）。"
                       "用於回答：我這些幣的成本是多少？算出來的損益涵蓋了多少比例？",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

GET_OPEN_POSITIONS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_open_positions",
        "description": "目前未平艙位與未實現損益：每個幣種的持有量、平均成本、現價、浮動損益與報酬率。"
                       "成本由歷史買入批次推算（以成交當時的日收盤價換算 TWD），數量對齊交易所實際餘額。"
                       "用於回答：我現在持倉如何？成本多少？浮動賺賠多少？最近買的艙位現在怎樣？",
        "parameters": {
            "type": "object",
            "properties": {
                "method": {"type": "string", "enum": ["fifo", "average"],
                           "description": "成本配對法：fifo 先進先出（預設）或 average 移動平均",
                           "default": "fifo"},
                "reward_basis": {"type": "string", "enum": ["market", "zero"],
                                 "description": "質押獎勵的成本認定：market 以收到當下市價（預設）或 zero 視為零成本",
                                 "default": "market"},
            },
            "required": [],
        },
    },
}

GET_REALIZED_PNL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_realized_pnl",
        "description": "已實現損益：每一筆賣出配對到哪些歷史買入批次、各賺賠多少、持有幾天，"
                       "並依幣種彙總報酬率與勝率。用於回答：我賣掉的那些賺了嗎？這波實現多少獲利？"
                       "某個幣我總共賺賠多少？",
        "parameters": {
            "type": "object",
            "properties": {
                "currency": {"type": "string", "description": "只看某個幣（如 'BTC'），省略＝全部"},
                "method": {"type": "string", "enum": ["fifo", "average"],
                           "description": "成本配對法，預設 fifo", "default": "fifo"},
                "reward_basis": {"type": "string", "enum": ["market", "zero"],
                                 "description": "質押獎勵成本認定，預設 market", "default": "market"},
                "limit": {"type": "integer", "description": "回傳最近幾筆明細，預設 50", "default": 50},
            },
            "required": [],
        },
    },
}

ANALYZE_TRADING_BEHAVIOR_SCHEMA = {
    "type": "function",
    "function": {
        "name": "analyze_trading_behavior",
        "description": "從使用者自己的交易帳本反推交易習慣與行為偏誤：處置效應（賺的抱不住、"
                       "賠的捨不得砍）、追漲殺跌、手續費拖累、攤平傾向。每個指標都附樣本數，"
                       "樣本不足時只列數字不下結論。用於回答：我的交易習慣有什麼問題？"
                       "我是不是常常追高？我手續費花太多嗎？我是不是愛攤平？",
        "parameters": {
            "type": "object",
            "properties": {
                "method": {"type": "string", "enum": ["fifo", "average"],
                           "description": "成本配對法，預設 fifo", "default": "fifo"},
                "min_trade_twd": {"type": "number",
                                  "description": "小於此金額的平倉視為尾差排除，預設 100 TWD",
                                  "default": 100},
            },
            "required": [],
        },
    },
}

# ──────────────────────────────────────────────
#  交易 DNA 面板（CSV 種子帳本 → 淨值曲線 / 六軸分數 / 反事實）
#  四支工具共用 source 參數：'demo'＝訪客示範帳戶 CSV、'ledger'＝MAX 真實帳本
# ──────────────────────────────────────────────
_DNA_SOURCE_PARAM = {
    "type": "string",
    "enum": ["demo", "ledger"],
    "description": "資料來源：demo＝訪客示範帳戶的 CSV 種子帳本（預設，離線可跑）；"
                   "ledger＝使用者的 MAX 真實帳本（需已用 reconcile_holdings 建立本地帳本）。"
                   "使用者已綁定 MAX 且問的是「我的」數字時用 ledger，其餘用 demo。",
    "default": "demo",
}
_DNA_PATH_PARAM = {
    "type": "string",
    "description": "source='demo' 時要讀的 CSV 路徑，留空即用內建示範帳戶（一般不需要指定）",
}

LOAD_DEMO_ACCOUNT_LEDGER_SCHEMA = {
    "type": "function",
    "function": {
        "name": "load_demo_account_ledger",
        "description": "載入『訪客示範帳戶』的 CSV 種子交易帳本並回傳資料健檢："
                       "總筆數、時間範圍、幣種與動作分布、餘額欄與累積變動量對不上的列數。"
                       "使用者**還沒綁定 MAX 金鑰**、或想先看看這個產品長什麼樣時，用這個當展示資料。"
                       "用於回答：先給我看個範例、我還沒綁帳號能看什麼、這份示範資料裡有什麼？"
                       "注意：它是合成的示範資料，不是使用者的真實帳本，回答時必須講清楚。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": _DNA_PATH_PARAM,
                "include_events": {"type": "boolean",
                                   "description": "是否回傳全部事件（1 萬筆會塞爆對話，預設 false）",
                                   "default": False},
                "preview": {"type": "integer", "description": "回傳前幾筆事件當樣本，預設 5",
                            "default": 5},
            },
            "required": [],
        },
    },
}

GET_EQUITY_CURVE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_equity_curve",
        "description": "加密資產淨值的**每日時間序列**（畫資產曲線用），另附起訖值、峰值與最大回撤。"
                       "與 get_open_positions 的差別：那個只給「現在」的快照，這個給「一整段時間的變化」。"
                       "用於回答：我的資產這一年怎麼變化？畫一下淨值曲線、我最大回撤多少、"
                       "什麼時候最慘？（不含 TWD 現金，只算加密部位市值）",
        "parameters": {
            "type": "object",
            "properties": {
                "source": _DNA_SOURCE_PARAM,
                "path": _DNA_PATH_PARAM,
                "limit": {"type": "integer",
                          "description": "只回最近幾天（0＝全部，預設 0）", "default": 0},
            },
            "required": [],
        },
    },
}

GET_TRADING_DNA_SCORE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_trading_dna_score",
        "description": "交易 DNA：把交易紀錄壓成雷達圖畫得出來的**六軸 0–100 性格分數**"
                       "（活躍度／紀律／擇時／分散／持有耐心／風險控管）加一個 archetype 標籤"
                       "（如「高頻無 alpha 交易者」「分散型長期持有者」），並附每個分數背後的原始指標。"
                       "與 analyze_trading_behavior 的差別：那個給行為偏誤的診斷文字，"
                       "這個給可視覺化的分數與人格標籤。"
                       "用於回答：我是什麼類型的交易者？幫我畫交易性格雷達圖、"
                       "我的交易風格是什麼、我哪一項最弱？"
                       "注意：分數高不等於績效好（活躍度只是描述交易頻繁程度），"
                       "且係數是用合成資料校準的，回答時可引用 calibration_note。"
                       "★ 回傳 insufficient_data=true 時，archetype 與標籤會是空的，"
                       "**絕對不可以宣稱使用者的交易性格**，只能說「交易紀錄還太少，無法判定」。",
        "parameters": {
            "type": "object",
            "properties": {"source": _DNA_SOURCE_PARAM, "path": _DNA_PATH_PARAM},
            "required": [],
        },
    },
}

COMPARE_SELL_VS_HOLD_SCHEMA = {
    "type": "function",
    "function": {
        "name": "compare_sell_vs_hold",
        "description": "反事實比較：使用者**實際的買進賣出** vs **『買了就抱、一次都不賣』**，"
                       "哪一種期末淨值比較高，並估算手續費侵蝕與主動交易的總成本。"
                       "用於回答：我如果都不賣會怎樣？頻繁進出到底有沒有賺到？"
                       "買了就抱是不是比較好？我手續費吃掉多少？"
                       "**引用規則（重要）**：回傳的 capital_feasible 若為 false，代表續抱情境需要的本金"
                       "遠超過帳戶實際投入的錢（根本執行不了），此時**只能把金額當方法學示意**，"
                       "必須連同 caveat 一起說明，不可以講成「你少賺了 XX 元」。",
        "parameters": {
            "type": "object",
            "properties": {
                "source": _DNA_SOURCE_PARAM,
                "path": _DNA_PATH_PARAM,
                "fee_rate": {"type": "number",
                             "description": "手續費率，預設 0.0016（MAX taker 0.16%）",
                             "default": 0.0016},
            },
            "required": [],
        },
    },
}

# ──────────────────────────────────────────────
#  Schema：package_strategy_bot（把驗證過的策略打包成自動化 paper 機器人）
# ──────────────────────────────────────────────
PACKAGE_STRATEGY_BOT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "package_strategy_bot",
        "description": (
            "把一個（最好先用 backtest_strategy 驗證過的）策略打包成一支可在『策略機器人』面板啟動的"
            "自動化 Paper 交易機器人。打包後是停止狀態，使用者到面板按啟動才會自動模擬運行"
            "（全程 paper 模擬盤、不下真單）。當使用者回測完覺得策略不錯、說想『把它變成機器人／"
            "自動跑／打包／部署／讓它自己交易』時呼叫。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "機器人名稱，給人看的（如『BTC 雙均線 5/20』）"},
                "strategy_type": {"type": "string", "description": "策略類型", "enum": ["ma_crossover", "rsi_reversal"]},
                "params": {"type": "object", "description": "策略參數。ma_crossover: {fast_period, slow_period}；rsi_reversal: {rsi_period, oversold, overbought}"},
                "market": {"type": "string", "description": "MAX 交易對，如 'btctwd'、'ethtwd'", "default": "btctwd"},
                "period_minutes": {"type": "integer", "description": "K 線週期（分鐘），如 5、15、60", "default": 5},
            },
            "required": ["name", "strategy_type", "params"],
        },
    },
}


ANALYTICS_TOOLS = [
    CALCULATE_INDICATORS_SCHEMA,
    PACKAGE_STRATEGY_BOT_SCHEMA,
    RUN_BACKTEST_SCHEMA,
    BACKTEST_STRATEGY_SCHEMA,
    SAVE_STRATEGY_SCHEMA,
    LIST_STRATEGIES_SCHEMA,
    RUN_BACKTEST_ON_SAVED_STRATEGY_SCHEMA,
    RUN_TWITTER_MENTION_BACKTEST_SCHEMA,
    DETECT_MARKET_REGIME_SCHEMA,
    ANALYZE_PORTFOLIO_SCHEMA,
    RUN_ANALYST_DESK_SCHEMA,
    RUN_SIGNAL_BACKTEST_SCHEMA,
    RUN_COMPOSITE_BACKTEST_SCHEMA,
    RUN_ANALYSIS_SCHEMA,
    RECONCILE_HOLDINGS_SCHEMA,
    GET_COST_BASIS_POSITIONS_SCHEMA,
    GET_OPEN_POSITIONS_SCHEMA,
    GET_REALIZED_PNL_SCHEMA,
    ANALYZE_TRADING_BEHAVIOR_SCHEMA,
    LOAD_DEMO_ACCOUNT_LEDGER_SCHEMA,
    GET_EQUITY_CURVE_SCHEMA,
    GET_TRADING_DNA_SCORE_SCHEMA,
    COMPARE_SELL_VS_HOLD_SCHEMA,
]

ANALYTICS_TOOL_MAP = {
    "calculate_indicators": "skills.analytics.indicators.calculate_indicators",
    "run_analyst_desk":     "skills.analytics.analyst_desk.run_analyst_desk",
    "run_signal_backtest":  "skills.analytics.event_study.run_signal_backtest",
    "run_composite_backtest": "skills.analytics.event_study.run_composite_backtest",
    "run_analysis":         "analyst_sandbox.sandbox.run_analysis",
    "run_backtest":         "skills.analytics.backtester.run_backtest",
    "save_strategy":        "skills.analytics.strategy_manager.save_strategy",
    "package_strategy_bot": "agent.strategy_bots.package_strategy_bot",
    "list_strategies":      "skills.analytics.strategy_manager.list_strategies",
    "run_backtest_on_saved_strategy": "skills.analytics.strategy_manager.run_backtest_on_saved_strategy",
    "run_twitter_mention_backtest": "skills.analytics.backtester.run_twitter_mention_backtest",
    "detect_market_regime": "skills.analytics.regime_detector.detect_market_regime",
    "analyze_portfolio":    "skills.analytics.portfolio_tracker.analyze_portfolio",
    "load_demo_account_ledger": "skills.analytics.csv_source.load_demo_account_ledger",
    "get_equity_curve":     "skills.analytics.equity_curve.get_equity_curve",
    "get_trading_dna_score": "skills.analytics.dna_score.get_trading_dna_score",
    "compare_sell_vs_hold": "skills.analytics.counterfactual.compare_sell_vs_hold",
}

