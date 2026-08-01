from skills.market_intel.coingecko_client import (
    get_coingecko_coin_price,
    get_coingecko_global_stats,
    get_coingecko_trending
)
from skills.market_intel.cmc_client import (
    get_cmc_latest_quotes,
    get_cmc_global_metrics
)
from skills.market_intel.blockchain_client import (
    get_blockchain_btc_stats,
    get_btc_unconfirmed_tx
)
from skills.market_intel.fng_client import (
    get_crypto_fear_and_greed_index
)
from skills.market_intel.news_client import (
    get_latest_crypto_news
)
from skills.market_intel.reddit_client import (
    fetch_reddit_sentiment
)
from skills.market_intel.web_search_client import (
    search_web_duckduckgo
)
from skills.market_intel.social_scraper import (
    fetch_trump_truth_posts,
    fetch_twitter_user_tweets
)


