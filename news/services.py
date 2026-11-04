# news/services.py
"""
Pure database-query helpers used by the views.
Keeps business logic out of views.py.
"""
from django.db.models import Q, Count, F
from django.utils import timezone
from datetime import timedelta

from .models import NewsArticle


# -----------------------------------------------------------------------
# Article retrieval
# -----------------------------------------------------------------------

def get_articles(*, category=None, source=None, search=None,
                 days=None, ordering='-published_at'):
    """
    Return a filtered queryset of NewsArticle.
    All parameters are optional and stack together.
    """
    qs = NewsArticle.objects.all()

    if category:
        qs = qs.filter(category__iexact=category)

    if source:
        qs = qs.filter(source_name__iexact=source)

    if search:
        # Case-insensitive keyword search across the pre-built search_vector
        qs = qs.filter(search_vector__icontains=search.lower())

    if days:
        cutoff = timezone.now() - timedelta(days=int(days))
        qs = qs.filter(
            Q(published_at__gte=cutoff) | Q(collected_at__gte=cutoff)
        )

    if ordering == '-published_at':
        return qs.order_by(F('published_at').desc(nulls_last=True), '-collected_at')
    elif ordering == 'published_at':
        return qs.order_by(F('published_at').asc(nulls_last=True))

    return qs.order_by(ordering)


def get_article_by_id(article_id):
    try:
        return NewsArticle.objects.get(pk=article_id)
    except NewsArticle.DoesNotExist:
        return None


# -----------------------------------------------------------------------
# Metadata helpers
# -----------------------------------------------------------------------

def get_categories():
    """Return list of categories that actually have articles."""
    return (
        NewsArticle.objects
        .values_list('category', flat=True)
        .distinct()
        .order_by('category')
    )


def get_sources():
    """Return list of source names that actually have articles."""
    return (
        NewsArticle.objects
        .values_list('source_name', flat=True)
        .distinct()
        .order_by('source_name')
    )


# -----------------------------------------------------------------------
# Stats helpers (used for charts)
# -----------------------------------------------------------------------

def articles_by_category():
    return (
        NewsArticle.objects
        .values('category')
        .annotate(count=Count('id'))
        .order_by('-count')
    )


def articles_by_source():
    return (
        NewsArticle.objects
        .values('source_name')
        .annotate(count=Count('id'))
        .order_by('-count')
    )


def articles_by_date(days=30):
    cutoff = timezone.now() - timedelta(days=days)
    qs = (
        NewsArticle.objects
        .filter(
            Q(published_at__gte=cutoff) | Q(collected_at__gte=cutoff)
        )
        .extra(select={'day': "date(COALESCE(published_at, collected_at))"})
        .values('day')
        .annotate(count=Count('id'))
        .order_by('day')
    )
    return list(qs)


def database_stats():
    total = NewsArticle.objects.count()
    last_24h = NewsArticle.objects.filter(
        collected_at__gte=timezone.now() - timedelta(hours=24)
    ).count()
    return {
        'total_articles': total,
        'collected_last_24h': last_24h,
        'categories': list(articles_by_category()),
        'sources': list(articles_by_source()),
    }

