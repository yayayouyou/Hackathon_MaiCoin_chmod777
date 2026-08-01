"""
skills/market_intel/schemas.py

模塊四：市場情報模組 Tool JSON Schema 定義
=============================================
定義本模塊所有函數的 OpenAI-compatible JSON Schema。
"""

# ──────────────────────────────────────────────
#  Schema 1：get_coingecko_coin_price
# ──────────────────────────────────────────────
GET_COINGECKO_COIN_PRICE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_coingecko_coin_price",
        "description": "獲取一個或多個加密貨幣在 CoinGecko 上的即時報價、市值與 24 小時漲跌幅。不需 API 金鑰即可使用。",
        "parameters": {
            "type": "object",
            "properties": {
                "ids": {
                    "type": "string",
                    "description": "CoinGecko 幣種 ID 清單（小寫，逗號分隔，如 'bitcoin,ethereum,solana'）"
                },
                "vs_currencies": {
                    "type": "string",
                    "description": "法幣或報價代幣，如 'usd', 'twd'，預設為 'usd'",
                    "default": "usd"
                }
            },
            "required": ["ids"]
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 2：get_coingecko_global_stats
# ──────────────────────────────────────────────
GET_COINGECKO_GLOBAL_STATS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_coingecko_global_stats",
        "description": "獲取加密貨幣全網全球宏觀大盤數據（例如總市值、日交易量、比特幣市佔比、日市值變動比率）。",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 3：get_coingecko_trending
# ──────────────────────────────────────────────
GET_COINGECKO_TRENDING_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_coingecko_trending",
        "description": "獲取 CoinGecko 過去 24 小時前 7 名最受用戶熱搜的熱門代幣清單 (Trending)。",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 4：get_cmc_latest_quotes
# ──────────────────────────────────────────────
GET_CMC_LATEST_QUOTES_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_cmc_latest_quotes",
        "description": "【需授權金鑰】獲取指定代幣符號在 CoinMarketCap 上的詳細最新報價、供應量與市值排名等核心指標。支援批量查詢。",
        "parameters": {
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "string",
                    "description": "代幣符號清單（大寫，逗號分隔，例如 'BTC,ETH,SOL'）"
                },
                "convert": {
                    "type": "string",
                    "description": "轉換的法定/加密貨幣，如 'USD', 'TWD'，預設為 'USD'",
                    "default": "USD"
                }
            },
            "required": ["symbols"]
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 5：get_cmc_global_metrics
# ──────────────────────────────────────────────
GET_CMC_GLOBAL_METRICS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_cmc_global_metrics",
        "description": "【需授權金鑰】獲取 CoinMarketCap 的全球加密市場宏觀大盤指標走勢數據（包含 BTC 與 ETH 的主導佔有率等）。",
        "parameters": {
            "type": "object",
            "properties": {
                "convert": {
                    "type": "string",
                    "description": "報價單位，如 'USD', 'TWD'，預設為 'USD'",
                    "default": "USD"
                }
            }
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 6：get_blockchain_btc_stats
# ──────────────────────────────────────────────
GET_BLOCKCHAIN_BTC_STATS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_blockchain_btc_stats",
        "description": "獲取比特幣 (BTC) 全網最新的鏈上數據與網絡統計資訊（如全網算力、挖礦難度、24小時出塊時間與數量、礦工收益）。",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 7：get_btc_unconfirmed_tx
# ──────────────────────────────────────────────
GET_BTC_UNCONFIRMED_TX_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_btc_unconfirmed_tx",
        "description": "獲取當前比特幣網絡記憶體池 (Mempool) 中未確認的交易總數，用於評估鏈上網絡擁堵程度與預估交易手續費。",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 8：get_crypto_fear_and_greed_index
# ──────────────────────────────────────────────
GET_CRYPTO_FEAR_AND_GREED_INDEX_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_crypto_fear_and_greed_index",
        "description": "獲取加密貨幣市場最新的「恐懼與貪婪指數」(Fear & Greed Index)，以及歷史數據走勢。不需 API 金鑰即可使用。",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "獲取的天數，預設 1 (最新一天)，最多支持 100 天。",
                    "default": 1
                }
            }
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 9：get_latest_crypto_news
# ──────────────────────────────────────────────
GET_LATEST_CRYPTO_NEWS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_latest_crypto_news",
        "description": "【免 Key】獲取最新的加密貨幣即時市場新聞、頭條報導與簡要摘要（基於 CoinTelegraph RSS 訂閱源）。可用於分析宏觀情緒。",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "要獲取的新聞頭條數量，預設為 5，上限為 15。",
                    "default": 5
                }
            }
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 10：fetch_reddit_sentiment
# ──────────────────────────────────────────────
FETCH_REDDIT_SENTIMENT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "fetch_reddit_sentiment",
        "description": "【免 Key】抓取 Reddit 論壇 /r/cryptocurrency 版面中有關指定代幣（如 SOL, BTC）的最新貼文標題、內容、讚數與討論量，用於社交輿情與零售情緒分析。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "代幣符號或名稱（例如 'SOL' 或 'Solana'）"
                },
                "limit": {
                    "type": "integer",
                    "description": "獲取的貼文條數，預設為 5，上限為 10",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 11：search_web_duckduckgo
# ──────────────────────────────────────────────
SEARCH_WEB_DUCKDUCKGO_SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_web_duckduckgo",
        "description": "【免 Key】網頁實時搜尋。支持輸入搜尋詞獲取最新網頁標題、簡要摘要與連結，用於解答時效性強或外部資訊查詢的問題。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜尋關鍵字（例如 'MAX 交易所 2026 最新公告'）"
                },
                "max_results": {
                    "type": "integer",
                    "description": "返回的搜尋結果數量限制，預設 5，上限 10",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 12：fetch_trump_truth_posts
# ──────────────────────────────────────────────
FETCH_TRUMP_TRUTH_POSTS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "fetch_trump_truth_posts",
        "description": "【免 Key】抓取唐納·川普 (Donald Trump) 在 Truth Social 發表的最新貼文、發文時間與原文連結，用於分析其對加密貨幣市場的情緒影響。",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "獲取的貼文條數，預設為 5，上限為 15",
                    "default": 5
                }
            }
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 13：fetch_twitter_user_tweets
# ──────────────────────────────────────────────
FETCH_TWITTER_USER_TWEETS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "fetch_twitter_user_tweets",
        "description": "【免 Key】抓取特定 X (Twitter) 名人（如 elonmusk 或 realDonaldTrump）最新推文內容與點讚、轉發、回覆等互動數據，以進行名人輿情分析。",
        "parameters": {
            "type": "object",
            "properties": {
                "screen_name": {
                    "type": "string",
                    "description": "X 使用者帳號，如 'elonmusk' 或 'realDonaldTrump'，預設為 'elonmusk'",
                    "default": "elonmusk"
                },
                "limit": {
                    "type": "integer",
                    "description": "獲取的推文條數，預設為 5，上限為 15",
                    "default": 5
                }
            }
        }
    }
}

# ──────────────────────────────────────────────
#  Schema：get_btc_treasuries（企業比特幣財庫持幣動向）
# ──────────────────────────────────────────────
GET_BTC_TREASURIES_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_btc_treasuries",
        "description": (
            "獲取企業比特幣財庫（BTC Treasuries，如 MicroStrategy/Strategy、Metaplanet、MARA）的持幣排名"
            "與近期增持/減持動向——機構級籌碼信號（增持＝長線買盤承接、減持/出售＝籌碼鬆動）。"
            "省略 ticker 回總覽（前幾大持有 + 全體近期淨增減持）；給 ticker 回單一公司。需一次性免費 SoSoValue 金鑰。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "公司代號，如 'MSTR','MARA','3350'（省略＝總覽）"},
                "top_n": {"type": "integer", "description": "總覽追蹤公司數（預設 8）", "default": 8},
            },
        }
    }
}

# ──────────────────────────────────────────────
#  Schema：get_crypto_sector_indices（板塊輪動）
# ──────────────────────────────────────────────
GET_CRYPTO_SECTOR_INDICES_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_crypto_sector_indices",
        "description": (
            "獲取加密板塊指數表現（DeFi/Layer1/AI/Meme/RWA/DePIN…）的 24h/7d/1m 漲跌與板塊輪動信號——"
            "判斷資金正輪動至哪些板塊、市場處於 risk-on（迷因/AI/DeFi 領漲）或 risk-off。需免費 SoSoValue 金鑰。"
        ),
        "parameters": {"type": "object", "properties": {
            "top_n": {"type": "integer", "description": "追蹤板塊數（預設 6）", "default": 6}}}
    }
}

# ──────────────────────────────────────────────
#  Schema：get_crypto_stocks（加密概念股）
# ──────────────────────────────────────────────
GET_CRYPTO_STOCKS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_crypto_stocks",
        "description": (
            "獲取加密概念股（MSTR/COIN/礦股…）。省略 ticker 回各板塊（BTC Treasury/Mining/Exchange）市值與漲跌總覽；"
            "給 ticker 回單一個股行情。用於從股市對加密的間接定價讀出情緒。需免費 SoSoValue 金鑰。"
        ),
        "parameters": {"type": "object", "properties": {
            "ticker": {"type": "string", "description": "個股代號如 'MSTR','COIN'（省略＝板塊總覽）"}}}
    }
}

# ──────────────────────────────────────────────
#  統一工具清單與映射
# ──────────────────────────────────────────────
MARKET_INTEL_TOOLS = [
    GET_COINGECKO_COIN_PRICE_SCHEMA,
    GET_COINGECKO_GLOBAL_STATS_SCHEMA,
    GET_COINGECKO_TRENDING_SCHEMA,
    GET_CMC_LATEST_QUOTES_SCHEMA,
    GET_CMC_GLOBAL_METRICS_SCHEMA,
    GET_BLOCKCHAIN_BTC_STATS_SCHEMA,
    GET_BTC_UNCONFIRMED_TX_SCHEMA,
    GET_CRYPTO_FEAR_AND_GREED_INDEX_SCHEMA,
    GET_LATEST_CRYPTO_NEWS_SCHEMA,
    FETCH_REDDIT_SENTIMENT_SCHEMA,
    SEARCH_WEB_DUCKDUCKGO_SCHEMA,
    FETCH_TRUMP_TRUTH_POSTS_SCHEMA,
    FETCH_TWITTER_USER_TWEETS_SCHEMA,
    GET_BTC_TREASURIES_SCHEMA,
    GET_CRYPTO_SECTOR_INDICES_SCHEMA,
    GET_CRYPTO_STOCKS_SCHEMA,
]

MARKET_INTEL_TOOL_MAP = {
    "get_coingecko_coin_price":   "skills.market_intel.coingecko_client.get_coingecko_coin_price",
    "get_coingecko_global_stats": "skills.market_intel.coingecko_client.get_coingecko_global_stats",
    "get_coingecko_trending":     "skills.market_intel.coingecko_client.get_coingecko_trending",
    "get_cmc_latest_quotes":      "skills.market_intel.cmc_client.get_cmc_latest_quotes",
    "get_cmc_global_metrics":     "skills.market_intel.cmc_client.get_cmc_global_metrics",
    "get_blockchain_btc_stats":   "skills.market_intel.blockchain_client.get_blockchain_btc_stats",
    "get_btc_unconfirmed_tx":     "skills.market_intel.blockchain_client.get_btc_unconfirmed_tx",
    "get_crypto_fear_and_greed_index": "skills.market_intel.fng_client.get_crypto_fear_and_greed_index",
    "get_latest_crypto_news":     "skills.market_intel.news_client.get_latest_crypto_news",
    "fetch_reddit_sentiment":     "skills.market_intel.reddit_client.fetch_reddit_sentiment",
    "search_web_duckduckgo":      "skills.market_intel.web_search_client.search_web_duckduckgo",
    "fetch_trump_truth_posts":    "skills.market_intel.social_scraper.fetch_trump_truth_posts",
    "fetch_twitter_user_tweets":  "skills.market_intel.social_scraper.fetch_twitter_user_tweets",
    "get_btc_treasuries":         "skills.market_intel.btc_treasuries.get_btc_treasuries",
    "get_crypto_sector_indices":  "skills.market_intel.sosovalue_extras.get_crypto_sector_indices",
    "get_crypto_stocks":          "skills.market_intel.sosovalue_extras.get_crypto_stocks",
}


