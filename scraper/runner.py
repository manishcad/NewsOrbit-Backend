# scraper/runner.py
"""
Orchestrates scraping:
- Prevents duplicate concurrent runs for the same source.
- Saves valid articles to the DB (with duplicate detection via url_hash).
- Records each run in ScraperRun for status reporting.
"""
import logging
import threading
from datetime import datetime, timezone as dt_timezone
from typing import Optional

from django.utils import timezone

from news.models import NewsArticle, ScraperRun
from .rss_scraper import RssScraper
from .otv_scraper import OtvScraper
from .news18_scraper import News18Scraper
from .kanak_scraper import KanakScraper
from .sources import NEWS_SOURCES

logger = logging.getLogger('scraper')

# Thread-level lock to prevent two identical runs launching simultaneously
_running_sources: set = set()
_lock = threading.Lock()


# -----------------------------------------------------------------------
# Internal helpers
# -----------------------------------------------------------------------

def _is_running(source_name: str) -> bool:
    with _lock:
        return source_name in _running_sources


def _mark_running(source_name: str):
    with _lock:
        _running_sources.add(source_name)


def _mark_done(source_name: str):
    with _lock:
        _running_sources.discard(source_name)


def _save_articles(raw_articles, run: ScraperRun) -> tuple[int, int]:
    """
    Persist raw articles to the DB.
    Returns (total_found, new_saved).
    Duplicates are detected by url_hash (unique constraint).
    """
    found = len(raw_articles)
    saved = 0

    for raw in raw_articles:
        url_hash = NewsArticle.make_url_hash(raw.url)
        if NewsArticle.objects.filter(url_hash=url_hash).exists():
            continue   # already stored — skip

        try:
            NewsArticle.objects.create(
                title        = raw.title[:1024],
                content      = raw.content,
                summary      = raw.summary[:2000] if raw.summary else '',
                source_name  = raw.source_name[:255],
                url          = raw.url[:2048],
                url_hash     = url_hash,
                image_url    = (raw.image_url or raw.extra.get('image_url') or '')[:2048],
                category     = raw.category,
                author       = raw.author[:512] if raw.author else '',
                language     = raw.language,
                published_at = raw.published_at,
            )
            saved += 1
        except Exception as exc:
            logger.warning(f'Could not save article "{raw.title[:60]}": {exc}')

    return found, saved


# -----------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------

def run_source(source_name: str) -> dict:
    """
    Run the scraper for a single named source.
    Looks up the source config in NEWS_SOURCES by source_name.
    Returns a result dict.
    """
    # Find the matching source config
    cfg = next(
        (s for s in NEWS_SOURCES if s['source_name'] == source_name),
        None
    )
    if not cfg:
        return {'error': f'Source "{source_name}" not found in sources.py'}

    if _is_running(source_name):
        return {'error': f'Scraper for "{source_name}" is already running.'}

    _mark_running(source_name)
    run = ScraperRun.objects.create(source_name=source_name, status='running')

    try:
        scraper_type = cfg.get('scraper_type')
        if scraper_type == 'otv':
            scraper = OtvScraper(
                max_pages=cfg.get('max_pages', 2)
            )
        elif scraper_type == 'news18':
            scraper = News18Scraper(
                max_pages=cfg.get('max_pages', 2)
            )
        elif scraper_type == 'kanak':
            scraper = KanakScraper(
                max_pages=cfg.get('max_pages', 2)
            )
        else:
            scraper = RssScraper(
                feed_url    = cfg['feed_url'],
                source_name = cfg['source_name'],
                category    = cfg.get('category', 'other'),
                language    = cfg.get('language', 'en'),
                max_articles= cfg.get('max_articles', 50),
            )
        raw_articles = scraper.fetch_articles()
        found, saved = _save_articles(raw_articles, run)

        run.status         = 'completed'
        run.articles_found = found
        run.articles_new   = saved
        run.finished_at    = timezone.now()
        run.save()

        logger.info(f'{source_name}: {found} found, {saved} new')
        return {
            'source':          source_name,
            'status':          'completed',
            'articles_found':  found,
            'articles_new':    saved,
            'run_id':          run.id,
        }

    except Exception as exc:
        logger.error(f'Scraper run failed for {source_name}: {exc}')
        run.status        = 'failed'
        run.error_message = str(exc)
        run.finished_at   = timezone.now()
        run.save()
        return {'source': source_name, 'status': 'failed', 'error': str(exc)}

    finally:
        _mark_done(source_name)


def run_all_sources(background: bool = False) -> list:
    """
    Run every source defined in NEWS_SOURCES, sequentially.
    If background=True, each source runs in its own thread (fire and forget).
    Returns a list of result dicts (empty when background=True).
    """
    results = []
    for cfg in NEWS_SOURCES:
        sname = cfg['source_name']
        if background:
            t = threading.Thread(target=run_source, args=(sname,), daemon=True)
            t.start()
        else:
            result = run_source(sname)
            results.append(result)
            logger.info(f'Finished: {result}')
    return results


def get_available_sources() -> list:
    """Return all source names defined in NEWS_SOURCES."""
    return [s['source_name'] for s in NEWS_SOURCES]

