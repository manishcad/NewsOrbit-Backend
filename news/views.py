# news/views.py
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.pagination import PageNumberPagination

from .models import NewsArticle, ScraperRun
from .serializers import (
    NewsArticleSerializer,
    NewsArticleDetailSerializer,
    ScraperRunSerializer,
)
from . import services

logger = logging.getLogger('news')


class StandardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


# Only these sort orders may be requested; anything else falls back to newest first.
ALLOWED_ORDERINGS = {
    'published_at', '-published_at',
    'collected_at', '-collected_at',
    'title', '-title',
    'source_name', '-source_name',
}


def _parse_ordering(value):
    return value if value in ALLOWED_ORDERINGS else '-published_at'


def _parse_days(value, default=None, maximum=3650):
    """Return a positive int number of days, or `default` if missing/invalid."""
    try:
        days = int(value)
    except (TypeError, ValueError):
        return default
    if days < 1:
        return default
    return min(days, maximum)


# -----------------------------------------------------------------------
# Articles
# -----------------------------------------------------------------------

class ArticleListView(APIView):
    """
    GET /api/v1/news/articles/
    Query params: category, source, search, days, ordering, page, page_size
    """

    def get(self, request):
        articles = services.get_articles(
            category=request.query_params.get('category'),
            source=request.query_params.get('source'),
            search=request.query_params.get('search'),
            days=_parse_days(request.query_params.get('days')),
            ordering=_parse_ordering(request.query_params.get('ordering')),
        )

        paginator = StandardPagination()
        page = paginator.paginate_queryset(articles, request)
        serializer = NewsArticleSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class ArticleDetailView(APIView):
    """GET /api/v1/news/articles/<id>/"""

    def get(self, request, pk):
        article = services.get_article_by_id(pk)
        if not article:
            return Response({'error': 'Article not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = NewsArticleDetailSerializer(article)
        return Response(serializer.data)


# -----------------------------------------------------------------------
# Metadata
# -----------------------------------------------------------------------

class CategoriesView(APIView):
    """GET /api/v1/news/categories/ — returns categories that have articles"""

    def get(self, request):
        categories = list(services.get_categories())
        # Also return display labels
        label_map = dict(NewsArticle.CATEGORY_CHOICES)
        data = [{'value': c, 'label': label_map.get(c, c.title())} for c in categories]
        return Response(data)


class SourcesView(APIView):
    """GET /api/v1/news/sources/"""

    def get(self, request):
        sources = list(services.get_sources())
        return Response(sources)


# -----------------------------------------------------------------------
# Stats
# -----------------------------------------------------------------------

class StatsView(APIView):
    """GET /api/v1/news/stats/ — database counts for the dashboard"""

    def get(self, request):
        days = _parse_days(request.query_params.get('days'), default=30, maximum=365)
        data = services.database_stats()
        data['timeline'] = services.articles_by_date(days=days)
        return Response(data)


# -----------------------------------------------------------------------
# Scraper runs log
# -----------------------------------------------------------------------

class ScraperRunListView(APIView):
    """GET /api/v1/news/scraper-runs/"""

    def get(self, request):
        runs = ScraperRun.objects.all()[:50]
        serializer = ScraperRunSerializer(runs, many=True)
        return Response(serializer.data)
