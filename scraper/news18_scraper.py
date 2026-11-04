# backend/scraper/news18_scraper.py
"""
Scraper for News18 Odia (https://odia.news18.com).
Subclasses BaseScraper and integrates seamlessly with NewsOrbit.
Uses fast HTTP + BeautifulSoup (no heavy Playwright dependency needed for listing pages).
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

logger = logging.getLogger('scraper.news18')

BASE_URL = 'https://odia.news18.com'
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

GENRE_CATEGORY_MAP = {
    'odisha':        'national',
    'sport':         'sports',
    'entertainment': 'entertainment',
    'politics':      'politics',
    'trending':      'entertainment',
    'lifestyle':     'entertainment',
}


class News18Scraper(BaseScraper):
    """
    Scraper for News18 Odia.
    Iterates through genres and pages, extracting news articles into RawArticle records.
    """

    source_name = 'News18 Odia'
    language = 'or'

    def __init__(
        self,
        genres: Optional[List[str]] = None,
        max_pages: int = 2,
        request_delay: float = 0.5,
    ):
        super().__init__()
        self.genres = genres or [
            'odisha',
            'sport',
            'entertainment',
            'politics',
            'trending',
            'lifestyle',
        ]
        self.max_pages = max_pages
        self.request_delay = request_delay
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def fetch_articles(self) -> List[RawArticle]:
        all_articles: List[RawArticle] = []
        seen_urls = set()

        for genre in self.genres:
            self.logger.info(f'Scraping News18 Odia genre: {genre}')
            mapped_category = GENRE_CATEGORY_MAP.get(genre, 'other')

            for page_num in range(1, self.max_pages + 1):
                if page_num == 1:
                    page_url = f'{BASE_URL}/{genre}/'
                else:
                    page_url = f'{BASE_URL}/{genre}/page-{page_num}/'

                try:
                    resp = self.session.get(page_url, timeout=15)
                    if resp.status_code != 200:
                        self.logger.warning(
                            f'Non-200 status {resp.status_code} for {page_url}'
                        )
                        continue

                    soup = BeautifulSoup(resp.content, 'lxml')
                    rows = soup.select('ul.cn-videoList > li')

                    if not rows:
                        self.logger.debug(f'No items found on {page_url}')
                        break

                    self.logger.debug(
                        f'{genre} page {page_num}: found {len(rows)} items'
                    )

                    for row in rows:
                        article = self._extract_item(row, genre, mapped_category)
                        if article and article.url not in seen_urls and self.validate(article):
                            seen_urls.add(article.url)
                            all_articles.append(article)

                except requests.RequestException as exc:
                    self.logger.warning(f'Network error scraping {page_url}: {exc}')
                except Exception as exc:
                    self.logger.error(f'Unexpected error on {page_url}: {exc}')

                time.sleep(self.request_delay)

        self.logger.info(
            f'Total unique articles collected from News18 Odia: {len(all_articles)}'
        )
        return all_articles

    def _extract_item(self, row, genre: str, mapped_category: str) -> Optional[RawArticle]:
        try:
            link_el = row.select_one('a.CN-videoListbox') or row.select_one('a')
            if not link_el:
                return None

            raw_href = link_el.get('href', '').strip()
            if not raw_href:
                return None

            article_url = urljoin(BASE_URL, raw_href)

            caption_el = row.select_one('figcaption')
            title = caption_el.get_text(strip=True) if caption_el else ''

            img_el = row.select_one('figure img') or row.select_one('img')
            img_src = ''
            img_alt = ''
            if img_el:
                img_src = img_el.get('src', '') or img_el.get('data-src', '')
                img_alt = img_el.get('alt', '') or img_el.get('title', '')
                if not title:
                    title = img_alt.strip()

            if not title:
                return None

            # Try to extract date from link href (e.g. photogallery/odisha/...-422023.html) or fallback to now
            published_at = datetime.now(tz=IST)

            summary = f'{title}'

            return RawArticle(
                title=title,
                url=article_url,
                source_name=self.source_name,
                category=mapped_category,
                summary=summary,
                content=summary,
                image_url=img_src,
                author='News18 Odia Bureau',
                language=self.language,
                published_at=published_at,
                extra={
                    'genre': genre,
                    'image_url': img_src,
                    'image_alt': img_alt,
                },
            )
        except Exception as exc:
            self.logger.debug(f'Error parsing News18 item: {exc}')
            return None

