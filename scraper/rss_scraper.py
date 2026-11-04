# scraper/rss_scraper.py
"""
Generic RSS/Atom feed scraper built on feedparser.
Pass it a feed URL, source name, and category — it handles the rest.

To add a new RSS source, just register a new entry in sources.py.
No new Python class needed.
"""
import logging
import time
from datetime import datetime, timezone as dt_timezone
from email.utils import parsedate_to_datetime
from typing import List

import feedparser
import requests
from bs4 import BeautifulSoup

from .base import BaseScraper, RawArticle

logger = logging.getLogger('scraper')

HEADERS = {
    'User-Agent': (
        'NewsOrbit/1.0 (educational news aggregator; '
        'contact: newsorbitscraper@example.com)'
    )
}


def _parse_date(entry) -> datetime | None:
    """Try several feedparser date fields; return timezone-aware datetime or None."""
    for attr in ('published_parsed', 'updated_parsed'):
        val = getattr(entry, attr, None)
        if val:
            try:
                # feedparser returns time.struct_time in UTC
                return datetime(*val[:6], tzinfo=dt_timezone.utc)
            except Exception:
                pass

    # Fallback: raw string fields
    for attr in ('published', 'updated'):
        raw = getattr(entry, attr, None)
        if raw:
            try:
                return parsedate_to_datetime(raw)
            except Exception:
                pass
    return None


def _extract_text(html: str, max_chars: int = 2000) -> str:
    """Strip HTML tags and return plain text up to max_chars."""
    if not html:
        return ''
    try:
        soup = BeautifulSoup(html, 'lxml')
        text = soup.get_text(separator=' ', strip=True)
        return text[:max_chars]
    except Exception:
        return html[:max_chars]


class RssScraper(BaseScraper):
    """
    Scrapes a single RSS/Atom feed URL.
    Instantiated by the runner for each source definition in sources.py.
    """

    def __init__(self, feed_url: str, source_name: str,
                 category: str = 'other', language: str = 'en',
                 max_articles: int = 50):
        self.feed_url    = feed_url
        self.source_name = source_name
        self.category    = category
        self.language    = language
        self.max_articles = max_articles
        super().__init__()

    # ------------------------------------------------------------------
    def fetch_articles(self) -> List[RawArticle]:
        self.logger.info(f'Fetching RSS: {self.feed_url}')
        articles = []

        try:
            # Use requests so we can pass custom headers + timeout
            resp = requests.get(self.feed_url, headers=HEADERS,
                                timeout=15, allow_redirects=True)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
        except requests.RequestException as exc:
            self.logger.error(f'Network error fetching {self.feed_url}: {exc}')
            return []
        except Exception as exc:
            self.logger.error(f'Unexpected error fetching {self.feed_url}: {exc}')
            return []

        if feed.bozo and not feed.entries:
            self.logger.warning(
                f'Feed parse error for {self.feed_url}: {feed.bozo_exception}'
            )
            return []

        self.logger.info(f'Found {len(feed.entries)} entries in feed')

        for entry in feed.entries[: self.max_articles]:
            try:
                article = self._parse_entry(entry)
                if article and self.validate(article):
                    articles.append(article)
            except Exception as exc:
                self.logger.warning(f'Skipped entry due to error: {exc}')
            time.sleep(0.1)   # tiny delay between entries

        self.logger.info(f'Parsed {len(articles)} valid articles from {self.source_name}')
        return articles

    # ------------------------------------------------------------------
    def _parse_entry(self, entry) -> RawArticle | None:
        title = getattr(entry, 'title', '').strip()
        url   = getattr(entry, 'link', '').strip()

        if not title or not url:
            return None

        # Summary / content
        summary = ''
        content = ''

        # feedparser normalises content into entry.content list
        if hasattr(entry, 'content') and entry.content:
            raw_html = entry.content[0].get('value', '')
            content  = _extract_text(raw_html)
            summary  = content[:500]

        # Fallback: summary field
        if not summary:
            raw_sum = getattr(entry, 'summary', '') or ''
            summary = _extract_text(raw_sum, max_chars=500)

        author = ''
        if hasattr(entry, 'author'):
            author = entry.author.strip()
        elif hasattr(entry, 'authors') and entry.authors:
            author = entry.authors[0].get('name', '').strip()

        # Extract image if present in media_content, media_thumbnail, enclosures, or links
        image_url = ''
        if hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
            image_url = entry.media_thumbnail[0].get('url', '')
        elif hasattr(entry, 'media_content') and entry.media_content:
            image_url = entry.media_content[0].get('url', '')
        elif hasattr(entry, 'enclosures') and entry.enclosures:
            for enc in entry.enclosures:
                if enc.get('type', '').startswith('image/'):
                    image_url = enc.get('href') or enc.get('url', '')
                    break
        if not image_url and hasattr(entry, 'links'):
            for link in entry.links:
                if link.get('type', '').startswith('image/') or link.get('rel') == 'enclosure':
                    image_url = link.get('href', '')
                    break

        return RawArticle(
            title        = title,
            url          = url,
            source_name  = self.source_name,
            category     = self.category,
            content      = content,
            summary      = summary,
            image_url    = image_url,
            author       = author,
            language     = self.language,
            published_at = _parse_date(entry),
        )

