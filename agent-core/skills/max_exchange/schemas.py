"""
skills/max_exchange/schemas.py

模塊三：MAX 交易所 Tool JSON Schema 定義
=============================================
定義本模塊所有公開與私有 API 函數的 JSON Schema。
"""

# ──────────────────────────────────────────────
#  Schema 1：get_max_markets
# ──────────────────────────────────────────────
GET_MAX_MARKETS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_max_markets",
        "description": "獲取 MAX 交易所支持的所有交易對（例如 'btctwd', 'maxusdt'）及高精度的報價/最小下單量資訊。",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 1b：get_max_currencies（幣種 metadata）
# ──────────────────────────────────────────────
GET_MAX_CURRENCIES_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_max_currencies",
        "description": "獲取 MAX 幣種資訊：該幣可否質押(stakeable)、可否融資(m_wallet)，以及各區塊鏈網路的提幣手續費、最低提幣量、是否需要 memo/tag、存提是否開放。查特定幣帶 currency（如 'USDT'）。適合回答『X 提幣手續費多少 / 走哪條鏈 / 哪些幣可質押』。",
        "parameters": {
            "type": "object",
            "properties": {
                "currency": {
                    "type": "string",
                    "description": "選填。幣種代碼（如 'USDT'、'BTC'）。不填回傳全部幣種。"
                }
            }
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 1c：get_max_interest_rates（融資借幣利率）
# ──────────────────────────────────────────────
GET_MAX_INTEREST_RATES_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_max_interest_rates",
        "description": "獲取 MAX 融資（M-Wallet 借幣）利率，已換算日利率與年化 APR(%)。適合回答『借 USDT/BTC 的利息、融資資金成本、年化利率多少』。查特定幣帶 currency（如 'USDT'）。",
        "parameters": {
            "type": "object",
            "properties": {
                "currency": {"type": "string", "description": "選填。幣種代碼（如 'USDT'、'BTC'）。不填回傳全部。"}
            }
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 1d：get_max_index_prices（指數/標記價）
# ──────────────────────────────────────────────
GET_MAX_INDEX_PRICES_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_max_index_prices",
        "description": "獲取 MAX 指數/標記價格（跨交易所加權，融資計價與清算基準）。可與現貨價比較看溢價/折價。查特定交易對帶 market（如 'BTC/USDT'）。",
        "parameters": {
            "type": "object",
            "properties": {
                "market": {"type": "string", "description": "選填。交易對如 'BTC/USDT'、'ETH/USDT'。不填回傳全部。"}
            }
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 2：get_max_tickers
# ──────────────────────────────────────────────
GET_MAX_TICKERS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_max_tickers",
        "description": "獲取 MAX 最新行情報價。可獲取所有或指定交易對的買一、賣一、最新價與漲跌幅。",
        "parameters": {
            "type": "object",
            "properties": {
                "market": {
                    "type": "string",
                    "description": "選填。交易對符號，例如 'BTC/TWD' 或 'btctwd'。如果不填則返回全市場報價。"
                }
            }
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 3：get_max_depth
# ──────────────────────────────────────────────
GET_MAX_DEPTH_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_max_depth",
        "description": "獲取 MAX 特定交易對的買賣深度檔單 (Order Book)，用於分析當前買賣盤力道與掛單分佈。",
        "parameters": {
            "type": "object",
            "properties": {
                "market": {
                    "type": "string",
                    "description": "交易對符號，例如 'BTC/TWD' 或 'btctwd'"
                },
                "limit": {
                    "type": "integer",
                    "description": "返回買賣單的深度檔數，默認為 20",
                    "default": 20
                }
            },
            "required": ["market"]
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 4：get_max_klines
# ──────────────────────────────────────────────
GET_MAX_KLINES_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_max_klines",
        "description": "獲取 MAX 交易所指定交易對的 K 線歷史數據。支援自訂數量與分鐘週期。",
        "parameters": {
            "type": "object",
            "properties": {
                "market": {
                    "type": "string",
                    "description": "交易對符號，例如 'BTC/TWD'"
                },
                "limit": {
                    "type": "integer",
                    "description": "獲取 K 線條數，預設 100",
                    "default": 100
                },
                "period_minutes": {
                    "type": "integer",
                    "description": "K 線週期（分鐘），常用：1=1m, 5=5m, 15=15m, 30=30m, 60=1h, 240=4h, 1440=1d",
                    "enum": [1, 5, 15, 30, 60, 120, 240, 360, 720, 1440, 4320, 10080],
                    "default": 60
                },
                "timeframe": {
                    "type": "string",
                    "description": "也可用字串週期（與 get_ohlcv 相同），如 '1m','5m','15m','1h','4h','1d'；會自動換算為分鐘。",
                    "enum": ["1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"]
                }
            },
            "required": ["market"]
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 5：get_max_public_trades
# ──────────────────────────────────────────────
GET_MAX_PUBLIC_TRADES_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_max_public_trades",
        "description": "獲取 MAX 交易所指定交易對的公共近期歷史成交明細記錄。",
        "parameters": {
            "type": "object",
            "properties": {
                "market": {
                    "type": "string",
                    "description": "交易對符號，例如 'BTC/TWD'"
                },
                "limit": {
                    "type": "integer",
                    "description": "返回記錄筆數，預設 50",
                    "default": 50
                }
            },
            "required": ["market"]
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 6：get_max_member_info
# ──────────────────────────────────────────────
GET_MAX_MEMBER_INFO_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_max_member_info",
        "description": ("【私有/需授權】獲取帳戶會員資訊與手續費。回傳明確區分兩種等級："
                        "account_kyc_level（身份驗證等級 Lv，與手續費無關）與 vip_tier（VIP 交易等級，"
                        "決定手續費），另含 maker_fee_pct/taker_fee_pct 與升到下一級的門檻與屆時費率。"),
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 7：get_max_accounts
# ──────────────────────────────────────────────
GET_MAX_ACCOUNTS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_max_accounts",
        "description": "【私有/需授權】獲取指定錢包中餘額大於 0 的所有幣種資產（可用/鎖定/質押/總額）。預設現貨錢包；查融資錢包請帶 wallet_type='m'（另含融資本金 principal 與應計利息 interest）。",
        "parameters": {
            "type": "object",
            "properties": {
                "wallet_type": {
                    "type": "string",
                    "enum": ["spot", "m"],
                    "description": "錢包類型：'spot' 現貨（預設）、'm' 融資 M-Wallet"
                }
            }
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 7b：get_max_ad_ratio（融資維持率/清算風險）
# ──────────────────────────────────────────────
GET_MAX_AD_RATIO_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_max_ad_ratio",
        "description": "【私有/需授權】獲取融資 M-Wallet 的維持率/清算風險：ad_ratio（越高越安全，無負債時為很大的哨兵值如 999）、asset_in_usdt（總資產）、debt_in_usdt（總負債，USDT 計價）。",
        "parameters": {"type": "object", "properties": {}}
    }
}

# ──────────────────────────────────────────────
#  Schema 8：get_max_orders
# ──────────────────────────────────────────────
GET_MAX_ORDERS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_max_orders",
        "description": "【私有/需授權】獲取帳戶當前的活動訂單（掛單中/未完全成交）或歷史訂單清單。",
        "parameters": {
            "type": "object",
            "properties": {
                "market": {
                    "type": "string",
                    "description": "選填。限制獲取指定交易對，例如 'BTC/TWD'"
                },
                "state": {
                    "type": "string",
                    "description": "選填。訂單狀態過濾。常用 'wait' (等待成交/掛單中), 'done' (完全成交), 'cancel' (已撤銷)",
                    "enum": ["wait", "done", "cancel", "convert"]
                },
                "limit": {
                    "type": "integer",
                    "description": "返回筆數上限，預設 20",
                    "default": 20
                }
            }
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 9：get_max_order_history
# ──────────────────────────────────────────────
GET_MAX_ORDER_HISTORY_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_max_order_history",
        "description": "【私有/需授權】獲取當前帳戶所有的歷史訂單記錄，包含已完全成交和已取消的歷史掛單。",
        "parameters": {
            "type": "object",
            "properties": {
                "market": {
                    "type": "string",
                    "description": "選填。僅獲取特定交易對歷史"
                },
                "limit": {
                    "type": "integer",
                    "description": "返回歷史掛單的筆數上限，預設 50",
                    "default": 50
                }
            }
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 10：get_max_my_trades
# ──────────────────────────────────────────────
GET_MAX_MY_TRADES_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_max_my_trades",
        "description": "【私有/需授權】獲取當前帳戶的個人歷史成交記錄（成交明細），可用於分析交易盈虧 (PnL)。",
        "parameters": {
            "type": "object",
            "properties": {
                "market": {
                    "type": "string",
                    "description": "選填。僅獲取特定交易對的成交明細"
                },
                "limit": {
                    "type": "integer",
                    "description": "返回成交記錄筆數，預設 50",
                    "default": 50
                }
            }
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 11：get_max_deposits
# ──────────────────────────────────────────────
GET_MAX_DEPOSITS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_max_deposits",
        "description": "【私有/需授權】獲取帳戶入金/法幣或加密貨幣充值歷史記錄。",
        "parameters": {
            "type": "object",
            "properties": {
                "currency": {
                    "type": "string",
                    "description": "選填。過濾幣種代碼，例如 'TWD', 'USDT'"
                },
                "limit": {
                    "type": "integer",
                    "description": "返回記錄筆數，預設 20",
                    "default": 20
                }
            }
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 12：get_max_withdrawals
# ──────────────────────────────────────────────
GET_MAX_WITHDRAWALS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_max_withdrawals",
        "description": "【私有/需授權】獲取帳戶出金/法幣或加密貨幣提現歷史記錄。",
        "parameters": {
            "type": "object",
            "properties": {
                "currency": {
                    "type": "string",
                    "description": "選填。過濾幣種代碼，例如 'TWD', 'USDT'"
                },
                "limit": {
                    "type": "integer",
                    "description": "返回記錄筆數，預設 20",
                    "default": 20
                }
            }
        }
    }
}

# ──────────────────────────────────────────────
#  Schema：get_max_order（單筆訂單查詢）
# ──────────────────────────────────────────────
GET_MAX_ORDER_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_max_order",
        "description": "【私有/需授權】依訂單 id 或自訂委託編號 (client_oid) 查詢單一訂單的最新狀態（成交量、剩餘量、狀態等）。",
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "integer", "description": "MAX 訂單 id"},
                "client_oid": {"type": "string", "description": "下單時帶入的自訂委託編號"}
            }
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 15-18：個人帳戶資訊（資金流水/閃兌/提幣白名單/站內轉帳）
# ──────────────────────────────────────────────
GET_MAX_FUND_TRANSACTIONS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_max_fund_transactions",
        "description": "【私有/需授權】獲取資金異動記錄（比 deposits/withdrawals 更完整：含是否站內、區塊鏈網路、txid、提幣手續費、對方地址）。適合『我上次入金/出金/提幣到哪、現貨與融資錢包互轉』。",
        "parameters": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["deposit", "withdrawal", "transfer"],
                          "description": "deposit 入金 / withdrawal 出金 / transfer 現貨↔融資互轉（預設 deposit）"},
                "currency": {"type": "string", "description": "選填。幣種代碼，如 'USDT'、'BTC'"},
                "limit": {"type": "integer", "description": "筆數，預設 20"}
            }
        }
    }
}

GET_MAX_CONVERTS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_max_converts",
        "description": "【私有/需授權】獲取閃兌(convert)歷史：從哪個幣換到哪個幣、數量、手續費（含 TWD 計價）。適合『我的閃兌記錄、上次把 X 換成 Y』。",
        "parameters": {
            "type": "object",
            "properties": {
                "currency": {"type": "string", "description": "選填。比對來源或目標幣，如 'MAX'"},
                "limit": {"type": "integer", "description": "筆數，預設 20"}
            }
        }
    }
}

GET_MAX_WITHDRAW_ADDRESSES_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_max_withdraw_addresses",
        "description": "【私有/需授權】獲取指定幣種的提幣白名單地址（含備註標籤、鏈別）。適合『我 USDT 提幣白名單有哪些地址』。currency 必填。",
        "parameters": {
            "type": "object",
            "properties": {
                "currency": {"type": "string", "description": "必填。幣種代碼，如 'USDT'、'BTC'"},
                "limit": {"type": "integer", "description": "筆數，預設 50"}
            },
            "required": ["currency"]
        }
    }
}

GET_MAX_INTERNAL_TRANSFERS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_max_internal_transfers",
        "description": "【私有/需授權】獲取 MAX 用戶之間的站內轉帳記錄。side 必填：'in' 轉入 / 'out' 轉出。",
        "parameters": {
            "type": "object",
            "properties": {
                "side": {"type": "string", "enum": ["in", "out"], "description": "'in' 轉入 / 'out' 轉出"},
                "currency": {"type": "string", "description": "選填。幣種代碼"},
                "limit": {"type": "integer", "description": "筆數，預設 20"}
            },
            "required": ["side"]
        }
    }
}

TRACE_DEPOSIT_SOURCE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "trace_deposit_source",
        "description": ("【私有/需授權·免鏈上key】調查近期入金的鏈上來源：對每筆站外加密入金用 txid 上鏈"
                        "查出發送地址並給來源標籤——具名交易所(如『來自 Binance 14』，經 eth-labels)／交易所熱"
                        "錢包／🚩新錢包 → 辨識有無來路不明資金。支援 EVM/Solana/Tron/BTC。站內轉帳與法幣入金"
                        "無鏈上來源。適合『我這些入金從哪來、有沒有來路不明的錢、這筆入金來源可靠嗎』。"),
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "檢查最近幾筆入金，預設 10"}
            }
        }
    }
}

# ──────────────────────────────────────────────
#  統一工具清單與映射
# ──────────────────────────────────────────────
MAX_EXCHANGE_TOOLS = [
    GET_MAX_MARKETS_SCHEMA,
    GET_MAX_CURRENCIES_SCHEMA,
    GET_MAX_INTEREST_RATES_SCHEMA,
    GET_MAX_INDEX_PRICES_SCHEMA,
    GET_MAX_TICKERS_SCHEMA,
    GET_MAX_DEPTH_SCHEMA,
    GET_MAX_KLINES_SCHEMA,
    GET_MAX_PUBLIC_TRADES_SCHEMA,
    GET_MAX_MEMBER_INFO_SCHEMA,
    GET_MAX_ACCOUNTS_SCHEMA,
    GET_MAX_AD_RATIO_SCHEMA,
    GET_MAX_ORDERS_SCHEMA,
    GET_MAX_ORDER_SCHEMA,
    GET_MAX_ORDER_HISTORY_SCHEMA,
    GET_MAX_MY_TRADES_SCHEMA,
    GET_MAX_DEPOSITS_SCHEMA,
    GET_MAX_WITHDRAWALS_SCHEMA,
    GET_MAX_FUND_TRANSACTIONS_SCHEMA,
    GET_MAX_CONVERTS_SCHEMA,
    GET_MAX_WITHDRAW_ADDRESSES_SCHEMA,
    GET_MAX_INTERNAL_TRANSFERS_SCHEMA,
    TRACE_DEPOSIT_SOURCE_SCHEMA,
]

MAX_EXCHANGE_TOOL_MAP = {
    "get_max_markets":       "skills.max_exchange.max_public.get_max_markets",
    "get_max_currencies":    "skills.max_exchange.max_public.get_max_currencies",
    "get_max_interest_rates": "skills.max_exchange.max_public.get_max_interest_rates",
    "get_max_index_prices":  "skills.max_exchange.max_public.get_max_index_prices",
    "get_max_tickers":       "skills.max_exchange.max_public.get_max_tickers",
    "get_max_depth":         "skills.max_exchange.max_public.get_max_depth",
    "get_max_klines":        "skills.max_exchange.max_public.get_max_klines",
    "get_max_public_trades": "skills.max_exchange.max_public.get_max_public_trades",
    "get_max_member_info":   "skills.max_exchange.max_private.get_max_member_info",
    "get_max_accounts":      "skills.max_exchange.max_private.get_max_accounts",
    "get_max_ad_ratio":      "skills.max_exchange.max_private.get_max_ad_ratio",
    "get_max_orders":        "skills.max_exchange.max_private.get_max_orders",
    "get_max_order":         "skills.max_exchange.max_private.get_max_order",
    "get_max_order_history": "skills.max_exchange.max_private.get_max_order_history",
    "get_max_my_trades":     "skills.max_exchange.max_private.get_max_my_trades",
    "get_max_deposits":      "skills.max_exchange.max_private.get_max_deposits",
    "get_max_withdrawals":   "skills.max_exchange.max_private.get_max_withdrawals",
    "get_max_fund_transactions": "skills.max_exchange.max_private.get_max_fund_transactions",
    "get_max_converts":      "skills.max_exchange.max_private.get_max_converts",
    "get_max_withdraw_addresses": "skills.max_exchange.max_private.get_max_withdraw_addresses",
    "get_max_internal_transfers": "skills.max_exchange.max_private.get_max_internal_transfers",
    "trace_deposit_source":      "skills.market_data.chain_trace.trace_deposit_source",
}
