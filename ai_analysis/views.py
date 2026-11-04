# backend/ai_analysis/views.py
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .retriever import retrieve_relevant_articles
from .gemini_client import analyze_news_query, AIServiceError
from config.throttles import (
    NamedThrottleMixin, GeneralAnonThrottle, AIBurstThrottle, AIQueryThrottle,
)

logger = logging.getLogger('ai_analysis')

MAX_QUERY_LENGTH = 500


class AIQueryView(NamedThrottleMixin, APIView):
    """
    POST /api/v1/ai/query/
    Body JSON:
    {
        "query": "What are the major technology developments in AI?",
        "max_articles": 12
    }

    Limits: AI_BURST_LIMIT per minute and AI_DAILY_LIMIT per day per visitor.
    Successful responses include "usage": {"limit", "remaining"}.
    """
    # Burst first, so rapid repeats are blocked before they use a daily question.
    throttle_classes = [GeneralAnonThrottle, AIBurstThrottle, AIQueryThrottle]

    def _usage(self):
        daily = self.get_throttle(AIQueryThrottle)
        if not daily or daily.num_requests is None:
            return None
        return {'limit': daily.num_requests, 'remaining': daily.remaining, 'period': 'day'}

    def _refund(self):
        daily = self.get_throttle(AIQueryThrottle)
        if daily:
            daily.refund()

    def post(self, request):
        response = self._answer(request)
        # Only questions that actually got an AI answer count toward the daily limit.
        if response.status_code != 200 or response.data.get('model') is None:
            self._refund()
            if response.status_code == 200:
                response.data['usage'] = self._usage()
        return response

    def _answer(self, request):
        query = str(request.data.get('query', '')).strip()
        if not query:
            return Response(
                {'error': 'Please enter a question.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(query) > MAX_QUERY_LENGTH:
            return Response(
                {'error': f'Questions are limited to {MAX_QUERY_LENGTH} characters.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            max_articles = int(request.data.get('max_articles', 12))
        except (TypeError, ValueError):
            max_articles = 12
        max_articles = max(3, min(max_articles, 20))

        try:
            # 1. Find relevant articles in the local database
            articles, aggregate_stats = retrieve_relevant_articles(query, max_articles=max_articles)
            # 2. Ask Gemini, grounded on those articles only
            analysis = analyze_news_query(query, articles, aggregate_stats)
            analysis['usage'] = self._usage()
            return Response(analysis, status=status.HTTP_200_OK)

        except AIServiceError as exc:
            return Response({'error': str(exc)}, status=exc.status_code)

        except Exception:
            logger.exception('Unhandled error during AI query analysis')
            return Response(
                {'error': 'Something went wrong while researching this question.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
