# backend/scraper/kanak_scraper.py
"""
Scraper for Kanak News (https://kanaknews.com).
Subclasses BaseScraper and integrates seamlessly with NewsOrbit.
Extracts title, URL, published date, author, category tag, and image using BeautifulSoup.
"""
import logging
import re
import time
from datetime import datetime
from typing import List, Optional
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from .base import BaseScraper, RawArticle

logger = logging.getLogger('scraper.kanak')

BASE_DOMAIN = 'https://kanaknews.com'
IST = ZoneInfo('Asia/Kolkata')

DEFAULT_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9,or;q=0.8',
}

# Routes that exist on Kanak News website mapped to NewsOrbit categories
ROUTE_CATEGORY_MAP = {
    'state':            'national',
    'news':             'national',
    'politics':         'politics',
    'odisha-politics':  'politics',
    'national-politics':'national',
    'world-and-nation': 'international',
    'sports':           'sports',
    'crime':            'national',
    'health':           'health',
    'lifestyle':        'entertainment',
    'special-report':   'other',
}


def _parse_kanak_date(date_str: str) -> Optional[datetime]:
    """
    Parse Kanak News datetime strings like 'Oct 31, 2026 09:47' or '2026-10-31T09:47:00'.
    Returns an IST-aware datetime or None.
    """
    if not date_str:
        return None
    cleaned = date_str.strip()
    cleaned = re.sub(r'\s+', ' ', cleaned)

    for fmt in (
        '%b %d, %Y %H:%M',
        '%b %d, %Y %I:%M %p',
        '%d %b %Y %H:%M',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d',
    ):
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.replace(tzinfo=IST)
        except ValueError:
            continue

    # ISO format fallback
    try:
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST)
        return dt
    except ValueError:
        pass

    return None


class KanakScraper(BaseScraper):
    """
    Scraper for Kanak News.
    Iterates through active routes/genres and pages.
    """

    source_name = 'Kanak News'
    language = 'or'

    def __init__(
        self,
        routes: Optional[List[str]] = None,
        max_pages: int = 2,
        request_delay: float = 0.5,
    ):
        super().__init__()
        self.routes = routes or [
            'state',
            'news',
            'politics',
            'world-and-nation',
            'sports',
            'crime',
            'health',
            'lifestyle',
        ]
        self.max_pages = max_pages
        self.request_delay = request_delay
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def fetch_articles(self) -> List[RawArticle]:
        all_articles: List[RawArticle] = []
        seen_urls = set()

        for route in self.routes:
            self.logger.info(f'Scraping Kanak News route: {route}')
            mapped_category = ROUTE_CATEGORY_MAP.get(route, 'other')

            for page_num in range(1, self.max_pages + 1):
                target_url = f'{BASE_DOMAIN}/{route}?page={page_num}'

                try:
                    resp = self.session.get(target_url, timeout=15)
                    if resp.status_code != 200:
                        self.logger.warning(
                            f'Non-200 status {resp.status_code} for {target_url}'
                        )
                        continue

                    soup = BeautifulSoup(resp.content, 'lxml')
                    posts = soup.select('.gh-archive-page-posts-feed .gh-archive-page-post, .gh-archive-page-post')

                    if not posts:
                        self.logger.debug(f'No posts found on {target_url}')
                        break

                    self.logger.debug(
                        f'{route} page {page_num}: found {len(posts)} posts'
                    )

                    for post in posts:
                        article = self._extract_post(post, route, mapped_category)
                        if article and article.url not in seen_urls and self.validate(article):
                            seen_urls.add(article.url)
                            all_articles.append(article)

                except requests.RequestException as exc:
                    self.logger.warning(f'Network error scraping {target_url}: {exc}')
                except Exception as exc:
                    self.logger.error(f'Unexpected error on {target_url}: {exc}')

                time.sleep(self.request_delay)

        self.logger.info(
            f'Total unique articles collected from Kanak News: {len(all_articles)}'
        )
        return all_articles

    def _extract_post(self, post, route: str, mapped_category: str) -> Optional[RawArticle]:
        try:
            # 1. Title and URL
            title_el = post.select_one('h2.gh-archive-page-post-title a') or post.select_one('h2 a') or post.select_one('a')
            if not title_el:
                return None

            title = title_el.get_text(strip=True)
            if not title:
                title = title_el.get('aria-label', '').strip()

            raw_href = title_el.get('href', '').strip()
            if not raw_href:
                return None

            article_url = urljoin(BASE_DOMAIN, raw_href)

            # 2. Image
            img_el = post.select_one('img.gh-archive-page-post-image') or post.select_one('img')
            image_url = ''
            image_alt = ''
            if img_el:
                image_url = img_el.get('src', '') or img_el.get('data-src', '')
                image_alt = img_el.get('alt', '') or ''

            # 3. Category Tag
            tag_el = post.select_one('.gh-tags-wrapper a.gh-tag-link') or post.select_one('.gh-tags-wrapper a')
            display_tag = tag_el.get_text(strip=True) if tag_el else route

            # 4. Author
            author_el = post.select_one('a.gh-post-info__author-link') or post.select_one('.gh-post-info__author-link')
            author_name = author_el.get_text(strip=True) if author_el else 'Kanak News Bureau'

            # 5. Timestamp
            time_el = post.select_one('time.gh-post-info__date') or post.select_one('time')
            datetime_raw = time_el.get('datetime', '') if time_el else ''
            published_at = _parse_kanak_date(datetime_raw)

            summary = f'{title}'

            return RawArticle(
                title=title,
                url=article_url,
                source_name=self.source_name,
                category=mapped_category,
                summary=summary,
                content=summary,
                image_url=image_url,
                author=author_name,
                language=self.language,
                published_at=published_at,
                extra={
                    'route': route,
                    'tag': display_tag,
                    'image_url': image_url,
                    'image_alt': image_alt,
                },
            )
        except Exception as exc:
            self.logger.debug(f'Error parsing Kanak post: {exc}')
            return None

