# scraper/base.py
"""
Abstract base class for all news scrapers.
Every new source must subclass BaseScraper and implement `fetch_articles`.
"""
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger('scraper')


@dataclass
class RawArticle:
    """
    Raw data returned by a scraper before it is written to the DB.
    Only `title` and `url` are strictly required; the rest can be empty.
    """
    title:       str
    url:         str
    source_name: str
    category:    str           = 'other'
    content:     str           = ''
    summary:     str           = ''
    image_url:   str           = ''
    author:      str           = ''
    language:    str           = 'en'
    published_at: Optional[datetime] = None
    extra:       dict          = field(default_factory=dict)


class BaseScraper(ABC):
    """
    Inherit from this class to add a new news source.
    Override `source_name`, `category`, and implement `fetch_articles`.
    """

    source_name: str = 'Unknown'
    category:    str = 'other'
    language:    str = 'en'

    # Polite delay between HTTP requests (seconds)
    request_delay: float = 1.0

    def __init__(self):
        self.logger = logging.getLogger(f'scraper.{self.source_name}')

    @abstractmethod
    def fetch_articles(self) -> List[RawArticle]:
        """
        Fetch and parse articles from the source.
        Must return a list of RawArticle instances.
        Should NOT raise — catch exceptions internally and return
        whatever was collected before the error.
        """
        ...

    def validate(self, article: RawArticle) -> bool:
        """Basic sanity check before saving."""
        if not article.title or not article.title.strip():
            return False
        if not article.url or not article.url.startswith('http'):
            return False
        return True

