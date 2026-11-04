# backend/scraper/otv_scraper.py
"""
BeautifulSoup-based scraper for OdishaTV (https://odishatv.in).
Replaces the browser-heavy Playwright version with high-speed HTTP + BeautifulSoup,
while retaining all selectors and data extraction logic.
"""
import logging
import re
import time
from datetime import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from .base import BaseScraper, RawArticle

logger = logging.getLogger('scraper.odishatv')

DEFAULT_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

GENRE_CATEGORY_MAP = {
    'international': 'international',
    'national':      'national',
    'odisha':        'national',
    'sports':        'sports',
    'entertainment': 'entertainment',
    'politics':      'politics',
    'business':      'business',
    'technology':    'technology',
    'lifestyle':     'entertainment',
    'health':        'health',
    'education':     'education',
    'crime':         'national',
    'travel':        'other',
}

IST = ZoneInfo('Asia/Kolkata')


def _parse_otv_date(date_str: str) -> Optional[datetime]:
    """
    Parse OTV date formats such as:
    'Oct 29, 2026 11:53 IST' or 'Oct 29, 2026 11:53:00 IST' or '29 Oct 2026'
    Returns a timezone-aware datetime in IST, or None on failure.
    """
    if not date_str:
        return None
    cleaned = date_str.strip()
    cleaned = re.sub(r'\s+', ' ', cleaned)

    # Format: "Oct 29, 2026 11:53 IST"
    for fmt in (
        '%b %d, %Y %H:%M IST',
        '%b %d, %Y %I:%M %p IST',
        '%b %d, %Y %H:%M:%S IST',
        '%d %b %Y %H:%M IST',
        '%b %d, %Y',
    ):
        try:
            # Strip trailing timezone name for strptime, then attach IST
            s = cleaned
            if s.endswith(' IST'):
                s = s[:-4].strip()
            dt = datetime.strptime(s, fmt.replace(' IST', ''))
            return dt.replace(tzinfo=IST)
        except ValueError:
            continue
    return None


class OtvScraper(BaseScraper):
    """
    Scraper for OdishaTV.
    Iterates through configured genres and page numbers using BeautifulSoup.
    """

    source_name = 'Odisha TV'
    language = 'en'

    def __init__(
        self,
        genres: Optional[List[str]] = None,
        max_pages: int = 2,
        request_delay: float = 0.5,
    ):
        super().__init__()
        self.genres = genres or [
            'odisha',
            'national',
            'international',
            'technology',
            'business',
            'sports',
            'entertainment',
            'health',
            'education',
            'politics',
            'crime',
            'lifestyle',
            'travel',
        ]
        self.max_pages = max_pages
        self.request_delay = request_delay
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def fetch_articles(self) -> List[RawArticle]:
        all_articles: List[RawArticle] = []
        seen_urls = set()

        for genre in self.genres:
            self.logger.info(f'Scraping OdishaTV genre: {genre}')
            mapped_category = GENRE_CATEGORY_MAP.get(genre, 'other')

            for page_number in range(1, self.max_pages + 1):
                url = f'https://odishatv.in/{genre}?page={page_number}'
                try:
                    resp = self.session.get(url, timeout=15)
                    if resp.status_code != 200:
                        self.logger.warning(
                            f'Non-200 status {resp.status_code} for {url}'
                        )
                        continue

                    soup = BeautifulSoup(resp.content, 'lxml')
                    news_items = soup.select('.desktop-latest-news')
                    if not news_items:
                        # Fallback selector in case mobile or alternate grid is served
                        news_items = soup.select('.news-card, article.latest-news')

                    self.logger.debug(
                        f'{genre} page {page_number}: found {len(news_items)} items'
                    )

                    for item in news_items:
                        article = self._extract_item(item, genre, mapped_category)
                        if article and article.url not in seen_urls and self.validate(article):
                            seen_urls.add(article.url)
                            all_articles.append(article)

                except requests.RequestException as exc:
                    self.logger.warning(f'Network error scraping {url}: {exc}')
                except Exception as exc:
                    self.logger.error(f'Unexpected error on {url}: {exc}')

                time.sleep(self.request_delay)

        self.logger.info(
            f'Total unique articles collected from OdishaTV: {len(all_articles)}'
        )
        return all_articles

    def _extract_item(self, item, genre: str, mapped_category: str) -> Optional[RawArticle]:
        try:
            # 1. Title & URL from .desc > a
            article_link = item.select_one('.desc > a')
            if not article_link:
                article_link = item.select_one('a')
            if not article_link:
                return None

            article_url = article_link.get('href', '').strip()
            if not article_url:
                return None

            # Fix relative URLs if any
            if article_url.startswith('/'):
                article_url = f'https://odishatv.in{article_url}'

            # Title extraction: prefer .paragraph inside the link, or link text
            title_node = article_link.select_one('.paragraph') or article_link
            title = title_node.get_text(strip=True)
            if not title:
                title = article_link.get('aria-label', '').strip()
            if not title:
                return None

            # 2. Category tag
            category_tag_node = item.select_one('.small_category_tag a .category_tag') or item.select_one('.small_category_tag a')
            display_category = category_tag_node.get_text(strip=True) if category_tag_node else genre

            # 3. Publish Date
            date_node = item.select_one('.publish-date')
            publish_date_str = date_node.get_text(strip=True) if date_node else ''
            published_at = _parse_otv_date(publish_date_str)

            # 4. Image
            img_node = item.select_one('.l-cover img') or item.select_one('img')
            image_url = img_node.get('src', '') if img_node else ''
            image_alt = img_node.get('alt', '') if img_node else ''

            # 5. Summary
            aria_label = article_link.get('aria-label', '').strip()
            summary = aria_label if aria_label and aria_label != title else f"{display_category} coverage from OdishaTV: {title}"

            return RawArticle(
                title=title,
                url=article_url,
                source_name='Odisha TV',
                category=mapped_category,
                summary=summary,
                content=summary,
                image_url=image_url,
                author='OdishaTV Bureau',
                language=self.language,
                published_at=published_at,
                extra={
                    'genre': genre,
                    'category_display': display_category,
                    'image_url': image_url,
                    'image_alt': image_alt,
                },
            )

        except Exception as exc:
            self.logger.debug(f'Error parsing item: {exc}')
            return None

