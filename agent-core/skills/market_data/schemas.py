"""
skills/market_data/schemas.py

模塊一：LLM Function Calling JSON Schema 定義
=============================================
此文件定義所有 market_data 模塊函數對應的 OpenAI-compatible JSON Schema，
可直接用於：
  - OpenAI / Azure OpenAI Function Calling
  - Anthropic Claude Tool Use
  - Gemini Function Calling
  - 任何支援 JSON Schema 工具描述的 LLM 框架

使用方式：
    from skills.market_data.schemas import MARKET_DATA_TOOLS
    # 直接傳入 LLM API 的 tools 參數
    response = openai.chat.completions.create(
        model="gpt-4o",
        tools=MARKET_DATA_TOOLS,
        messages=[...]
    )

作者：AI Crypto Trading Agent Project
"""

# ──────────────────────────────────────────────
#  Schema 1：get_ohlcv
# ──────────────────────────────────────────────
GET_OHLCV_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_ohlcv",
        "description": (
            "獲取加密貨幣 K 線（OHLCV：開盤/最高/最低/收盤/成交量）數據。"
            "適用於：查看歷史價格走勢、分析特定時間週期的行情、計算技術指標前的數據準備。"
            "例如：'幫我看一下 BTC 過去 24 小時的 1 小時 K 線' 或 "
            "'ETH 最近 7 天的日線走勢如何？'"
            "注意：台幣（TWD）市場請改用 get_max_klines（MAX 原生資料較準確）；"
            "本工具適合 Binance 等國際交易所的 USDT 市場。同一組參數失敗時勿原樣重試。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "exchange_id": {
                    "type": "string",
                    "description": "交易所 ID（小寫），例如 'binance', 'okx', 'bybit'",
                    "enum": ["binance", "okx", "bybit", "kraken", "coinbase", "max"],
                },
                "symbol": {
                    "type": "string",
                    "description": (
                        "交易對符號，格式為 'BASE/QUOTE'，"
                        "例如 'BTC/USDT', 'ETH/USDT', 'SOL/USDT'。"
                        "合約市場通常使用 'BTC/USDT:USDT' 格式。"
                    ),
                },
                "timeframe": {
                    "type": "string",
                    "description": "K 線時間週期。常用：'1m'=1分鐘, '1h'=1小時, '4h'=4小時, '1d'=日線",
                    "enum": ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w"],
                    "default": "1h",
                },
                "limit": {
                    "type": "integer",
                    "description": "返回的 K 線數量。例如 limit=24 配合 timeframe='1h' 即返回最近 24 小時數據",
                    "default": 100,
                    "minimum": 1,
                    "maximum": 500,
                },
                "market_type": {
                    "type": "string",
                    "description": "市場類型：'spot'=現貨市場, 'swap'=永續合約",
                    "enum": ["spot", "swap", "future"],
                    "default": "spot",
                },
            },
            "required": ["exchange_id", "symbol"],
        },
    },
}

# ──────────────────────────────────────────────
#  Schema 2：get_ticker
# ──────────────────────────────────────────────
GET_TICKER_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_ticker",
        "description": (
            "獲取交易對的最新即時行情數據，包含最新成交價、買一/賣一價、"
            "24小時成交量、24小時漲跌幅等。"
            "適用於：快速查看當前價格、確認市場流動性、比較不同交易所的報價差異。"
            "例如：'現在 BTC 的價格是多少？' 或 '幫我看一下 ETH 今天的漲跌幅'"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "exchange_id": {
                    "type": "string",
                    "description": "交易所 ID（小寫），例如 'binance', 'okx'",
                    "enum": ["binance", "okx", "bybit", "kraken", "coinbase", "max"],
                },
                "symbol": {
                    "type": "string",
                    "description": "交易對符號，例如 'BTC/USDT', 'ETH/USDT'",
                },
            },
            "required": ["exchange_id", "symbol"],
        },
    },
}

# ──────────────────────────────────────────────
#  Schema 3：get_orderbook
# ──────────────────────────────────────────────
GET_ORDERBOOK_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_orderbook",
        "description": (
            "獲取交易對的 Orderbook（掛單深度）數據，顯示目前市場上的買單和賣單分佈。"
            "適用於：分析市場流動性、評估買賣壓力、判斷大型掛單牆的位置。"
            "例如：'幫我看看 BTC 目前的買賣掛單分佈' 或 '現在有沒有大的賣單牆？'"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "exchange_id": {
                    "type": "string",
                    "description": "交易所 ID（小寫）",
                    "enum": ["binance", "okx", "bybit", "kraken", "coinbase", "max"],
                },
                "symbol": {
                    "type": "string",
                    "description": "交易對符號，例如 'BTC/USDT'",
                },
                "depth": {
                    "type": "integer",
                    "description": "單邊顯示的掛單層數（預設 10 層，最多 50 層）",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 50,
                },
            },
            "required": ["exchange_id", "symbol"],
        },
    },
}

# ──────────────────────────────────────────────
#  Schema 4：get_funding_rate
# ──────────────────────────────────────────────
GET_FUNDING_RATE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_funding_rate",
        "description": (
            "獲取加密貨幣永續合約的資金費率歷史數據。"
            "資金費率是判斷市場多空情緒的重要指標：正費率代表市場偏多，負費率代表偏空。"
            "適用於：分析市場整體情緒、判斷是否存在多空擁擠現象。"
            "例如：'BTC 目前的資金費率高嗎？多方是否過熱？' 或 '最近 ETH 的資金費率趨勢'"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "幣種符號（只需幣種名稱，不含 USDT），例如 'BTC', 'ETH', 'SOL'",
                },
                "exchange": {
                    "type": "string",
                    "description": "交易所名稱（首字母大寫），例如 'Binance', 'OKX', 'Bybit'",
                    "enum": ["Binance", "OKX", "Bybit", "Bitget", "Deribit"],
                    "default": "Binance",
                },
                "interval": {
                    "type": "string",
                    "description": "數據時間間隔。永續合約通常每 8 小時結算一次，'8h' 最常用",
                    "enum": ["1h", "4h", "8h", "1d"],
                    "default": "8h",
                },
                "limit": {
                    "type": "integer",
                    "description": "返回的數據點數量（預設 30，即最近 30 個費率結算週期）",
                    "default": 30,
                    "minimum": 1,
                    "maximum": 200,
                },
            },
            "required": ["symbol"],
        },
    },
}

# ──────────────────────────────────────────────
#  Schema 5：get_open_interest
# ──────────────────────────────────────────────
GET_OPEN_INTEREST_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_open_interest",
        "description": (
            "獲取加密貨幣永續/期貨合約的持倉量（Open Interest）歷史數據。"
            "持倉量代表市場中未平倉合約的總規模，是衡量市場熱度的核心指標。"
            "OI 上升 + 價格上升 → 趨勢確認；OI 下降 + 價格下降 → 去槓桿警訊。"
            "例如：'BTC 的持倉量最近有變化嗎？' 或 'ETH 的 OI 是否持續增加？'"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "幣種符號，例如 'BTC', 'ETH'",
                },
                "exchange": {
                    "type": "string",
                    "description": "交易所名稱",
                    "enum": ["Binance", "OKX", "Bybit", "Bitget", "CME", "All"],
                    "default": "Binance",
                },
                "interval": {
                    "type": "string",
                    "description": "數據時間間隔",
                    "enum": ["5m", "15m", "30m", "1h", "4h", "8h", "1d"],
                    "default": "1h",
                },
                "limit": {
                    "type": "integer",
                    "description": "返回數量（預設 48，即最近 48 小時的小時數據）",
                    "default": 48,
                    "minimum": 1,
                    "maximum": 200,
                },
            },
            "required": ["symbol"],
        },
    },
}

# ──────────────────────────────────────────────
#  Schema 6：get_liquidation_history
# ──────────────────────────────────────────────
GET_LIQUIDATION_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_liquidation_history",
        "description": (
            "獲取加密貨幣合約的爆倉（強制平倉）歷史數據，分別統計多頭和空頭爆倉金額。"
            "大量多頭爆倉往往發生在快速下跌時，可能代表短期底部；"
            "大量空頭爆倉則發生在快速上漲後，可能代表短期頂部。"
            "例如：'今天 BTC 有多少人被爆倉？' 或 '過去 24 小時的爆倉情況'"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "幣種符號，例如 'BTC', 'ETH'",
                },
                "exchange": {
                    "type": "string",
                    "description": "交易所名稱（預設 Binance）",
                    "enum": ["Binance", "OKX", "Bybit", "Bitget", "All"],
                    "default": "Binance",
                },
                "interval": {
                    "type": "string",
                    "description": "數據時間間隔（預設 '1h'）",
                    "enum": ["5m", "15m", "30m", "1h", "4h", "12h", "1d"],
                    "default": "1h",
                },
                "limit": {
                    "type": "integer",
                    "description": "返回數量（預設 24，即最近 24 小時）",
                    "default": 24,
                    "minimum": 1,
                    "maximum": 200,
                },
            },
            "required": ["symbol"],
        },
    },
}

# ──────────────────────────────────────────────
#  Schema 7：get_long_short_ratio
# ──────────────────────────────────────────────
GET_LONG_SHORT_RATIO_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_long_short_ratio",
        "description": (
            "獲取加密貨幣合約市場的全球帳戶多空比（Long/Short Account Ratio）。"
            "多空比代表看多帳戶 vs 看空帳戶的比例，是市場情緒的直接指標。"
            "極端高多空比（>2）往往是反向警訊；極端低（<0.5）也需謹慎。"
            "例如：'目前市場多空比例如何？' 或 '大家對 BTC 是偏多還是偏空？'"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "幣種符號，例如 'BTC', 'ETH'",
                },
                "exchange": {
                    "type": "string",
                    "description": "交易所名稱",
                    "enum": ["Binance", "OKX", "Bybit", "Bitget"],
                    "default": "Binance",
                },
                "interval": {
                    "type": "string",
                    "description": "數據時間間隔",
                    "enum": ["5m", "15m", "30m", "1h", "4h", "12h", "1d"],
                    "default": "1h",
                },
                "limit": {
                    "type": "integer",
                    "description": "返回數量（預設 24）",
                    "default": 24,
                    "minimum": 1,
                    "maximum": 200,
                },
            },
            "required": ["symbol"],
        },
    },
}

# ──────────────────────────────────────────────
#  Schema 8：get_coinglass_liquidation_chart
# ──────────────────────────────────────────────
GET_COINGLASS_LIQUIDATION_CHART_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_coinglass_liquidation_chart",
        "description": "獲取特定代幣跨 ~25 所彙整的歷史爆倉數據（多/空拆分金額），常用於繪製爆倉柱狀圖（Coinalyze 免費 API，需一次性免費金鑰）。",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "代幣代號，例如 'BTC', 'ETH'"
                },
                "interval": {
                    "type": "string",
                    "description": "時間間隔，可選: '1h', '4h', '12h', '1d'",
                    "default": "1h"
                }
            },
            "required": ["symbol"]
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 9：get_coinglass_open_interest_info
# ────────────────────────────────────────ZS
GET_COINGLASS_OPEN_INTEREST_INFO_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_coinglass_open_interest_info",
        "description": "【免 Key】獲取特定代幣在全網主要合約交易所的即時持倉額 (Open Interest) 與變動率。",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "代幣代號，例如 'BTC', 'ETH'"
                }
            },
            "required": ["symbol"]
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 10：get_coinglass_home_stats
# ──────────────────────────────────────────────
GET_COINGLASS_HOME_STATS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_coinglass_home_stats",
        "description": "【免 Key】獲取全網大盤宏觀總覽（總市值/BTC主導度/24h量、全網衍生品總持倉量與成交額、市場多空比、恐懼與貪婪指數；24h總爆倉需免費 Coinalyze 金鑰）。免費來源聚合。",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 11：get_coinglass_ahr999
# ──────────────────────────────────────────────
GET_COINGLASS_AHR999_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_coinglass_ahr999",
        "description": "【免 Key】獲取比特幣 AHR999 囤幣與逃頂指標的最新值與歷史數據。主要用於指導比特幣定投、超低吸籌或高位止盈逃頂。",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 12：get_coinglass_altcoin_season
# ──────────────────────────────────────────────
GET_COINGLASS_ALTCOIN_SEASON_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_coinglass_altcoin_season",
        "description": "【免 Key】獲取山寨幣季節指數 (Altcoin Season Index) 歷史數據。指數高於 75 為山寨季節，低於 25 為 BTC 季節，用於判定市場大盤輪動格局。",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 13：get_coinglass_mayer_multiple
# ──────────────────────────────────────────────
GET_COINGLASS_MAYER_MULTIPLE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_coinglass_mayer_multiple",
        "description": "【免 Key】獲取梅耶乘數 (Mayer Multiple) 的最新值與歷史數據，公式為現價比 200 日移動平均線 (SMA)，低於 0.75 屬歷史嚴重超跌買點。",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 14：get_coinglass_etf_flow
# ──────────────────────────────────────────────
GET_COINGLASS_ETF_FLOW_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_coinglass_etf_flow",
        "description": "獲取美國現貨 BTC/ETH ETF 每日資金流入流出與統計（第一方 SoSoValue 免費 API；需一次性免費金鑰）。用於評估傳統合規法幣機構買盤資金的流向變化。",
        "parameters": {
            "type": "object",
            "properties": {
                "asset": {
                    "type": "string",
                    "description": "資產：'BTC' 或 'ETH'（預設 BTC）",
                    "enum": ["BTC", "ETH"]
                }
            }
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 15：get_coinglass_grayscale_stats
# ──────────────────────────────────────────────
GET_COINGLASS_GRAYSCALE_STATS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_coinglass_grayscale_stats",
        "description": "【免 Key】獲取灰度信託基金 (Grayscale Trust) 最新持倉量、溢價率與折價變化數據。反映傳統大額合規資金的溢價購買力。",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 16：get_coinglass_liquidation_heatmap
# ──────────────────────────────────────────────
GET_COINGLASS_LIQUIDATION_HEATMAP_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_coinglass_liquidation_heatmap",
        "description": "【免 Key】本地計算的爆倉熱力圖/爆倉價位群落（由持倉量 OI × 假設槓桿投影，價格掃過即清零）。用於尋找多空流動性聚集價位與支撐/阻力牆。屬近似『預測』非觀測。",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "幣種符號，如 BTC、ETH，或具體交易對如 Binance_BTCUSDT、OKX_ETHUSDT。若僅傳入單一幣種，預設拉取 Binance 永續合約數據。"
                },
                "range": {
                    "type": "string",
                    "description": "時間範圍，可選值：'3d' (預設), '7d', '30d'。此端點僅限這三種範圍。"
                }
            },
            "required": ["symbol"]
        }
    }
}

# ──────────────────────────────────────────────
# ──────────────────────────────────────────────
#  Schema 17：search_dex_pairs
# ──────────────────────────────────────────────
SEARCH_DEX_PAIRS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_dex_pairs",
        "description": "【免 Key】去中心化交易所 (DEX) 交易池搜尋。支持代幣名稱、符號（如 'WIF', 'DEGEN'）或合約地址，可返回流動性、FDV、價格與交易量。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜尋關鍵字，例如代幣符號 'WIF' 或名稱"
                }
            },
            "required": ["query"]
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 18：get_dex_token_info
# ──────────────────────────────────────────────
GET_DEX_TOKEN_INFO_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_dex_token_info",
        "description": "【免 Key】根據代幣合約地址獲取其在去中心化交易所上的配對交易池行情數據與價格。",
        "parameters": {
            "type": "object",
            "properties": {
                "token_address": {
                    "type": "string",
                    "description": "代幣合約地址，例如 Solana 的 WIF 地址 EKpQGSJtjMFqKZ9KQGWjh69d5189ocZ2WqiTaG2Spump"
                }
            },
            "required": ["token_address"]
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 19：get_smart_money_flow（鏈上資金流/買賣壓）
# ──────────────────────────────────────────────
GET_SMART_MONEY_FLOW_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_smart_money_flow",
        "description": ("【免 Key】查某代幣的鏈上資金流/買賣壓（看行動而非嘴巴）：用 DEX 聚合買/賣筆數、"
                        "量能、trending 判斷是否有異常買盤或『偷偷累積』。適合『聰明錢在買 X 嗎、"
                        "鏈上有沒有人在累積某迷因幣、X 買盤強不強』。（錢包級聰明錢需另設 BIRDEYE_API_KEY）"),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string",
                          "description": "代幣符號/名稱/合約地址，如 'WIF'、'PEPE' 或 Solana 合約地址"}
            },
            "required": ["query"]
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 20：validate_smart_money_signal（資金流訊號歷史有效性驗證）
# ──────────────────────────────────────────────
VALIDATE_SMART_MONEY_SIGNAL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "validate_smart_money_signal",
        "description": ("【免 Key】驗證某代幣『資金流入訊號』的歷史有效性 → 分辨當下買盤是真訊號還是噪音。"
                        "以歷史量能激增日當流入代理做事件研究，看之後是否真的顯著上漲。適合『聰明錢在買 X 這訊號"
                        "可靠嗎、歷史上 X 有量進場後真的漲嗎、這是真訊號還是噪音』。需該幣在主流交易所有日線。"),
        "parameters": {
            "type": "object",
            "properties": {
                "token": {"type": "string", "description": "代幣符號/名稱/合約地址，如 'PEPE'、'WIF'"},
                "hold_days": {"type": "integer", "description": "流入後觀察天數，預設 5"}
            },
            "required": ["token"]
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 21：run_token_due_diligence（一鍵盡職調查）
# ──────────────────────────────────────────────
RUN_TOKEN_DUE_DILIGENCE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "run_token_due_diligence",
        "description": ("【免 Key】對某代幣做一鍵盡職調查：一次整合『當下鏈上買賣壓＋訊號歷史有效性＋基本面"
                        "風險旗標（流動性/FDV/是否噪音）』給出綜合判讀，進場前避免追坑。適合『幫我盡職調查 X、"
                        "X 能不能碰、進場前幫我看一遍、X 綜合分析』。個別面向另有 get_smart_money_flow / "
                        "validate_smart_money_signal。"),
        "parameters": {
            "type": "object",
            "properties": {
                "token": {"type": "string", "description": "代幣符號/名稱/合約地址，如 'PEPE'、'WIF'"},
                "hold_days": {"type": "integer", "description": "訊號驗證觀察天數，預設 5"}
            },
            "required": ["token"]
        }
    }
}

# ──────────────────────────────────────────────
#  統一工具列表（直接傳給 LLM API）
# ──────────────────────────────────────────────
MARKET_DATA_TOOLS = [
    GET_OHLCV_SCHEMA,
    GET_TICKER_SCHEMA,
    GET_ORDERBOOK_SCHEMA,
    GET_FUNDING_RATE_SCHEMA,
    GET_OPEN_INTEREST_SCHEMA,
    GET_LIQUIDATION_SCHEMA,
    GET_LONG_SHORT_RATIO_SCHEMA,
    GET_COINGLASS_LIQUIDATION_CHART_SCHEMA,
    GET_COINGLASS_OPEN_INTEREST_INFO_SCHEMA,
    GET_COINGLASS_HOME_STATS_SCHEMA,
    GET_COINGLASS_AHR999_SCHEMA,
    GET_COINGLASS_ALTCOIN_SEASON_SCHEMA,
    GET_COINGLASS_MAYER_MULTIPLE_SCHEMA,
    GET_COINGLASS_ETF_FLOW_SCHEMA,
    GET_COINGLASS_GRAYSCALE_STATS_SCHEMA,
    GET_COINGLASS_LIQUIDATION_HEATMAP_SCHEMA,
    SEARCH_DEX_PAIRS_SCHEMA,
    GET_DEX_TOKEN_INFO_SCHEMA,
    GET_SMART_MONEY_FLOW_SCHEMA,
    VALIDATE_SMART_MONEY_SIGNAL_SCHEMA,
    RUN_TOKEN_DUE_DILIGENCE_SCHEMA,
]

# 函數名稱 → 實際函數的映射（方便 Agent 分發調用）
MARKET_DATA_TOOL_MAP = {
    "get_ohlcv":                       "skills.market_data.ccxt_fetcher.get_ohlcv",
    "get_ticker":                      "skills.market_data.ccxt_fetcher.get_ticker",
    "get_orderbook":                   "skills.market_data.ccxt_fetcher.get_orderbook",
    "get_funding_rate":                "skills.market_data.coinglass_client.get_funding_rate",
    "get_open_interest":               "skills.market_data.coinglass_client.get_open_interest",
    "get_liquidation_history":         "skills.market_data.coinglass_client.get_liquidation_history",
    "get_long_short_ratio":            "skills.market_data.coinglass_client.get_long_short_ratio",
    "get_coinglass_liquidation_chart": "skills.market_data.coinglass_scraper.get_coinglass_liquidation_chart",
    "get_coinglass_open_interest_info":"skills.market_data.coinglass_scraper.get_coinglass_open_interest_info",
    "get_coinglass_home_stats":        "skills.market_data.coinglass_scraper.get_coinglass_home_stats",
    "get_coinglass_ahr999":            "skills.market_data.coinglass_scraper.get_coinglass_ahr999",
    "get_coinglass_altcoin_season":    "skills.market_data.coinglass_scraper.get_coinglass_altcoin_season",
    "get_coinglass_mayer_multiple":    "skills.market_data.coinglass_scraper.get_coinglass_mayer_multiple",
    "get_coinglass_etf_flow":          "skills.market_data.coinglass_scraper.get_coinglass_etf_flow",
    "get_coinglass_grayscale_stats":   "skills.market_data.coinglass_scraper.get_coinglass_grayscale_stats",
    "get_coinglass_liquidation_heatmap":"skills.market_data.coinglass_scraper.get_coinglass_liquidation_heatmap",
    "search_dex_pairs":                "skills.market_data.dex_screener.search_dex_pairs",
    "get_dex_token_info":              "skills.market_data.dex_screener.get_dex_token_info",
    "get_smart_money_flow":            "skills.market_data.onchain_flow.get_smart_money_flow",
    "validate_smart_money_signal":     "skills.market_data.onchain_flow.validate_smart_money_signal",
    "run_token_due_diligence":         "skills.market_data.onchain_flow.run_token_due_diligence",
}
