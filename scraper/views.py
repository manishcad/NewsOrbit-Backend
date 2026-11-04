# scraper/views.py
"""
API endpoints to trigger scraping and check status.
Scraping runs in background threads so the HTTP response returns immediately.
"""
import logging
import threading
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from news.models import ScraperRun
from news.serializers import ScraperRunSerializer
from config.throttles import NamedThrottleMixin, GeneralAnonThrottle, ScrapeTriggerThrottle
from . import runner

logger = logging.getLogger('scraper')


class TriggerScrapeView(NamedThrottleMixin, APIView):
    """
    POST /api/v1/scraper/trigger/
    Body (JSON):
        { "source": "BBC News" }       ← scrape one source
        { "source": "all" }            ← scrape all sources in background

    Public, but limited to ONE sync per SCRAPE_COOLDOWN_MINUTES for the whole
    site. Only "all" or a configured source name is accepted.
    """
    throttle_classes = [GeneralAnonThrottle, ScrapeTriggerThrottle]

    def post(self, request):
        response = self._trigger(request)
        if response.status_code >= 400:
            # Invalid requests don't start the cooldown for everyone else.
            cooldown = self.get_throttle(ScrapeTriggerThrottle)
            if cooldown:
                cooldown.refund()
        return response

    def _trigger(self, request):
        source = str(request.data.get('source', '')).strip()

        if not source:
            return Response(
                {'error': 'Provide "source" field (source name or "all").'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if source.lower() != 'all' and source not in runner.get_available_sources():
            return Response(
                {'error': f'Unknown source "{source[:80]}".'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if source.lower() == 'all':
            # Fire all scrapers in background threads
            t = threading.Thread(
                target=runner.run_all_sources,
                kwargs={'background': True},
                daemon=True,
            )
            t.start()
            available = runner.get_available_sources()
            return Response({
                'status':  'started',
                'message': f'All {len(available)} sources queued in background.',
                'sources': available,
                'cooldown_minutes': settings.SCRAPE_COOLDOWN_MINUTES,
            })

        # Single source — run in a background thread
        def _run():
            runner.run_source(source)

        t = threading.Thread(target=_run, daemon=True)
        t.start()

        return Response({
            'status':  'started',
            'message': f'Scraper for "{source}" started in background.',
            'source':  source,
            'cooldown_minutes': settings.SCRAPE_COOLDOWN_MINUTES,
        })


class ScrapeStatusView(APIView):
    """
    GET /api/v1/scraper/status/
    Returns the 20 most recent scraper runs.
    """

    def get(self, request):
        runs = ScraperRun.objects.all()[:20]
        serializer = ScraperRunSerializer(runs, many=True)
        return Response({
            'runs':             serializer.data,
            'available_sources': runner.get_available_sources(),
        })


class AvailableSourcesView(APIView):
    """GET /api/v1/scraper/sources/ — lists all configured sources."""

    def get(self, request):
        return Response({'sources': runner.get_available_sources()})
