# scraper/sources.py
"""
Master list of news sources.

To add a new source, append a dict to NEWS_SOURCES.
Required keys : feed_url, source_name, category
Optional keys : language (default 'en'), max_articles (default 50)

All sources use publicly accessible RSS / Atom feeds —
no paywalls, no login walls, no robots.txt violations.
"""

NEWS_SOURCES = [

    # ── Odisha Regional Scrapers (BeautifulSoup HTML Scrapers) ───────────
    {
        'feed_url':    'https://odishatv.in',
        'source_name': 'Odisha TV',
        'category':    'national',
        'language':    'en',
        'scraper_type': 'otv',
        'max_pages':   2,
    },
    {
        'feed_url':    'https://odia.news18.com',
        'source_name': 'News18 Odia',
        'category':    'national',
        'language':    'or',
        'scraper_type': 'news18',
        'max_pages':   2,
    },
    {
        'feed_url':    'https://kanaknews.com',
        'source_name': 'Kanak News',
        'category':    'national',
        'language':    'or',
        'scraper_type': 'kanak',
        'max_pages':   2,
    },

    # ── International ──────────────────────────────────────────────────
    {
        'feed_url':    'http://feeds.bbci.co.uk/news/rss.xml',
        'source_name': 'BBC News',
        'category':    'international',
        'language':    'en',
        'max_articles': 30,
    },
    {
        'feed_url':    'http://feeds.bbci.co.uk/news/technology/rss.xml',
        'source_name': 'BBC Technology',
        'category':    'technology',
        'language':    'en',
        'max_articles': 20,
    },
    {
        'feed_url':    'http://feeds.bbci.co.uk/news/business/rss.xml',
        'source_name': 'BBC Business',
        'category':    'business',
        'language':    'en',
        'max_articles': 20,
    },
    {
        'feed_url':    'http://feeds.bbci.co.uk/news/health/rss.xml',
        'source_name': 'BBC Health',
        'category':    'health',
        'language':    'en',
        'max_articles': 20,
    },
    {
        'feed_url':    'http://feeds.bbci.co.uk/news/science_and_environment/rss.xml',
        'source_name': 'BBC Science',
        'category':    'science',
        'language':    'en',
        'max_articles': 20,
    },

    # ── Reuters ────────────────────────────────────────────────────────
    {
        'feed_url':    'https://feeds.reuters.com/reuters/topNews',
        'source_name': 'Reuters',
        'category':    'international',
        'language':    'en',
        'max_articles': 30,
    },
    {
        'feed_url':    'https://feeds.reuters.com/reuters/technologyNews',
        'source_name': 'Reuters Technology',
        'category':    'technology',
        'language':    'en',
        'max_articles': 20,
    },
    {
        'feed_url':    'https://feeds.reuters.com/reuters/businessNews',
        'source_name': 'Reuters Business',
        'category':    'business',
        'language':    'en',
        'max_articles': 20,
    },

    # ── The Hindu (India) ─────────────────────────────────────────────
    {
        'feed_url':    'https://www.thehindu.com/news/national/?service=rss',
        'source_name': 'The Hindu',
        'category':    'national',
        'language':    'en',
        'max_articles': 30,
    },
    {
        'feed_url':    'https://www.thehindu.com/business/?service=rss',
        'source_name': 'The Hindu Business',
        'category':    'business',
        'language':    'en',
        'max_articles': 20,
    },
    {
        'feed_url':    'https://www.thehindu.com/sci-tech/technology/?service=rss',
        'source_name': 'The Hindu Technology',
        'category':    'technology',
        'language':    'en',
        'max_articles': 20,
    },

    # ── Times of India ────────────────────────────────────────────────
    {
        'feed_url':    'https://timesofindia.indiatimes.com/rssfeedstopstories.cms',
        'source_name': 'Times of India',
        'category':    'national',
        'language':    'en',
        'max_articles': 30,
    },
    {
        'feed_url':    'https://timesofindia.indiatimes.com/rssfeeds/1898055.cms',
        'source_name': 'Times of India Tech',
        'category':    'technology',
        'language':    'en',
        'max_articles': 20,
    },
    {
        'feed_url':    'https://timesofindia.indiatimes.com/rssfeeds/1898047.cms',
        'source_name': 'Times of India Business',
        'category':    'business',
        'language':    'en',
        'max_articles': 20,
    },
    {
        'feed_url':    'https://timesofindia.indiatimes.com/rssfeeds/4719161.cms',
        'source_name': 'Times of India Sports',
        'category':    'sports',
        'language':    'en',
        'max_articles': 20,
    },

    # ── NDTV ──────────────────────────────────────────────────────────
    {
        'feed_url':    'https://feeds.feedburner.com/ndtvnews-top-stories',
        'source_name': 'NDTV',
        'category':    'national',
        'language':    'en',
        'max_articles': 30,
    },
    {
        'feed_url':    'https://feeds.feedburner.com/ndtvprofit-latest',
        'source_name': 'NDTV Profit',
        'category':    'business',
        'language':    'en',
        'max_articles': 20,
    },

    # ── Al Jazeera ────────────────────────────────────────────────────
    {
        'feed_url':    'https://www.aljazeera.com/xml/rss/all.xml',
        'source_name': 'Al Jazeera',
        'category':    'international',
        'language':    'en',
        'max_articles': 25,
    },

    # ── TechCrunch ────────────────────────────────────────────────────
    {
        'feed_url':    'https://techcrunch.com/feed/',
        'source_name': 'TechCrunch',
        'category':    'technology',
        'language':    'en',
        'max_articles': 25,
    },

    # ── Hacker News (top stories via unofficial RSS) ──────────────────
    {
        'feed_url':    'https://hnrss.org/frontpage',
        'source_name': 'Hacker News',
        'category':    'technology',
        'language':    'en',
        'max_articles': 25,
    },

    # ── ESPN Cricinfo (sports) ─────────────────────────────────────────
    {
        'feed_url':    'https://www.espncricinfo.com/rss/content/story/feeds/0.xml',
        'source_name': 'ESPNcricinfo',
        'category':    'sports',
        'language':    'en',
        'max_articles': 20,
    },

    # ── WHO Health alerts ─────────────────────────────────────────────
    {
        'feed_url':    'https://www.who.int/rss-feeds/news-english.xml',
        'source_name': 'WHO',
        'category':    'health',
        'language':    'en',
        'max_articles': 20,
    },
]

