# backend/config/tests.py
"""
Rate-limit and security tests:  python manage.py test
"""
import json
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.throttling import SimpleRateThrottle

from news.models import NewsArticle

VISITOR = {'REMOTE_ADDR': '203.0.113.10'}
OTHER_VISITOR = {'REMOTE_ADDR': '198.51.100.20'}


def answered(query, *args, **kwargs):
    return {'query': query, 'model': 'test-model', 'summary': 'ok', 'citations': []}


class RateLimitTestCase(TestCase):
    rates = {}

    def setUp(self):
        cache.clear()
        patcher = mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, self.rates)
        patcher.start()
        self.addCleanup(patcher.stop)

    def post_json(self, url, body, **extra):
        return self.client.post(url, data=json.dumps(body), content_type='application/json', **extra)


class AIQueryLimitTests(RateLimitTestCase):
    url = '/api/v1/ai/query/'
    rates = {'ai_query': '5/d', 'ai_burst': '100/m'}

    def setUp(self):
        super().setUp()
        NewsArticle.objects.create(title='AI story', source_name='BBC News', category='technology',
                                   url='https://example.com/ai', published_at=timezone.now())

    def ask(self, **extra):
        return self.post_json(self.url, {'query': 'AI'}, **(extra or VISITOR))

    @mock.patch('ai_analysis.views.analyze_news_query', side_effect=answered)
    def test_five_questions_per_day_then_blocked(self, _):
        remaining = [self.ask().json()['usage']['remaining'] for _ in range(5)]
        self.assertEqual(remaining, [4, 3, 2, 1, 0])

        blocked = self.ask()
        self.assertEqual(blocked.status_code, 429)
        self.assertIn("today's AI research questions", blocked.json()['error'])
        self.assertGreater(blocked.json()['retry_after'], 0)
        self.assertIn('Retry-After', blocked.headers)

    @mock.patch('ai_analysis.views.analyze_news_query', side_effect=answered)
    def test_fake_forwarded_for_header_does_not_reset_limit(self, _):
        for i in range(5):
            self.ask()
        spoofed = self.ask(HTTP_X_FORWARDED_FOR=f'10.0.0.{99}', **VISITOR)
        self.assertEqual(spoofed.status_code, 429)

    @mock.patch('ai_analysis.views.analyze_news_query', side_effect=answered)
    def test_limits_are_per_visitor(self, _):
        for i in range(5):
            self.ask()
        self.assertEqual(self.ask(**OTHER_VISITOR).status_code, 200)

    def test_failed_ai_calls_do_not_use_up_questions(self):
        from ai_analysis.gemini_client import AIServiceError
        with mock.patch('ai_analysis.views.analyze_news_query', side_effect=AIServiceError('down')):
            for i in range(7):
                self.assertEqual(self.ask().status_code, 502)
        with mock.patch('ai_analysis.views.analyze_news_query', side_effect=answered):
            self.assertEqual(self.ask().json()['usage']['remaining'], 4)

    def test_no_match_answers_are_free(self):
        for i in range(7):
            res = self.post_json(self.url, {'query': 'volcanic eruptions in Iceland'}, **VISITOR)
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json()['usage']['remaining'], 5)

    def test_empty_question_is_free(self):
        for i in range(7):
            self.assertEqual(self.post_json(self.url, {'query': ''}, **VISITOR).status_code, 400)
        with mock.patch('ai_analysis.views.analyze_news_query', side_effect=answered):
            self.assertEqual(self.ask().json()['usage']['remaining'], 4)


class AIBurstLimitTests(RateLimitTestCase):
    rates = {'ai_query': '50/d', 'ai_burst': '3/m'}

    @mock.patch('ai_analysis.views.analyze_news_query', side_effect=answered)
    def test_rapid_fire_is_blocked_without_using_daily_questions(self, _):
        for i in range(3):
            self.assertEqual(self.post_json('/api/v1/ai/query/', {'query': 'AI'}, **VISITOR).status_code, 200)
        res = self.post_json('/api/v1/ai/query/', {'query': 'AI'}, **VISITOR)
        self.assertEqual(res.status_code, 429)
        self.assertIn('too quickly', res.json()['error'])
        daily_history = cache.get('throttle_ai_query_203.0.113.10')
        self.assertEqual(len(daily_history), 3)   # the blocked request didn't count


class SyncFeedsLimitTests(RateLimitTestCase):
    url = '/api/v1/scraper/trigger/'
    rates = {'scrape_trigger': '1/15m'}

    @mock.patch('scraper.views.runner.run_all_sources')
    def test_one_sync_per_cooldown_for_the_whole_site(self, run_all):
        first = self.post_json(self.url, {'source': 'all'}, **VISITOR)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()['cooldown_minutes'], 15)

        again = self.post_json(self.url, {'source': 'all'}, **OTHER_VISITOR)   # different person
        self.assertEqual(again.status_code, 429)
        self.assertIn('synced recently', again.json()['error'])
        self.assertLessEqual(again.json()['retry_after'], 15 * 60)

    @mock.patch('scraper.views.runner.run_all_sources')
    def test_unknown_source_is_rejected_and_does_not_start_cooldown(self, run_all):
        bad = self.post_json(self.url, {'source': 'evil.example.com'}, **VISITOR)
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(self.post_json(self.url, {'source': 'all'}, **VISITOR).status_code, 200)


class GeneralApiLimitTests(RateLimitTestCase):
    rates = {'anon': '3/m'}

    def test_visitors_are_limited_but_local_server_is_exempt(self):
        for i in range(3):
            self.assertEqual(self.client.get('/api/v1/news/sources/', **VISITOR).status_code, 200)
        self.assertEqual(self.client.get('/api/v1/news/sources/', **VISITOR).status_code, 429)
        # Next.js server-side rendering on the same machine (127.0.0.1) is exempt.
        for i in range(5):
            self.assertEqual(self.client.get('/api/v1/news/sources/').status_code, 200)


class SecurityHeaderTests(TestCase):
    def test_security_headers(self):
        res = self.client.get('/api/v1/news/sources/')
        self.assertEqual(res.headers.get('X-Content-Type-Options'), 'nosniff')
        self.assertEqual(res.headers.get('X-Frame-Options'), 'DENY')
        self.assertIn('Referrer-Policy', res.headers)

    def test_errors_use_error_key(self):
        res = self.client.get('/api/v1/news/articles/?page=999')
        self.assertEqual(res.status_code, 404)
        self.assertIn('error', res.json())
