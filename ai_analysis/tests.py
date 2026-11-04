# backend/ai_analysis/tests.py
"""
Tests for retrieval and the AI query endpoint.
Gemini is mocked, so these run offline and cost nothing:
    python manage.py test
"""
import json
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from news.models import NewsArticle
from .retriever import retrieve_relevant_articles, extract_keywords, detect_categories
from .gemini_client import build_chart, _normalize


def make_article(title, source='BBC News', category='technology', summary='', days_ago=0, **kw):
    return NewsArticle.objects.create(
        title=title,
        summary=summary,
        source_name=source,
        category=category,
        url=f'https://example.com/{abs(hash(title + source))}',
        published_at=timezone.now() - timedelta(days=days_ago),
        **kw,
    )


class RetrieverTests(TestCase):
    def setUp(self):
        self.ai = make_article('OpenAI launches new AI model', summary='The AI lab released a model.')
        self.said = make_article('Minister said budget is ready', source='The Hindu', category='business',
                                 summary='The minister said the budget was ready.')
        self.world = make_article('Summit opens in Geneva', source='Al Jazeera', category='international')
        self.local = make_article('Bhubaneswar traffic update', source='Odisha TV', category='national')
        self.other = make_article('Train tour package launched', source='Odisha TV', category='other')

    def test_short_keyword_matches_whole_words_only(self):
        articles, _ = retrieve_relevant_articles('Latest on AI')
        ids = [a['id'] for a in articles]
        self.assertIn(self.ai.id, ids)
        self.assertNotIn(self.said.id, ids)   # "said" contains "ai" but is not a match

    def test_international_is_not_national(self):
        self.assertEqual(detect_categories('international news'), ['international'])
        articles, _ = retrieve_relevant_articles('What is happening in international news?')
        self.assertEqual([a['id'] for a in articles], [self.world.id])

    def test_another_does_not_select_other_category(self):
        self.assertNotIn('other', detect_categories('tell me about another AI startup'))
        articles, _ = retrieve_relevant_articles('tell me about another AI startup')
        self.assertNotIn(self.other.id, [a['id'] for a in articles])

    def test_no_match_returns_empty_instead_of_unrelated_articles(self):
        articles, stats = retrieve_relevant_articles('quantum entanglement breakthroughs')
        self.assertEqual(articles, [])
        self.assertEqual(stats['total_matched'], 0)

    def test_publisher_name_becomes_source_filter(self):
        articles, stats = retrieve_relevant_articles('What is Al Jazeera reporting?')
        self.assertEqual(stats['sources_detected'], ['Al Jazeera'])
        self.assertEqual([a['source_name'] for a in articles], ['Al Jazeera'])

    def test_time_window(self):
        old = make_article('Old AI story', days_ago=40)
        articles, stats = retrieve_relevant_articles('AI news this week')
        self.assertEqual(stats['time_window_days'], 7)
        self.assertNotIn(old.id, [a['id'] for a in articles])

    def test_stopwords_removed(self):
        self.assertEqual(extract_keywords('What are the latest developments regarding NVIDIA?'), ['nvidia'])


class GeminiResponseTests(TestCase):
    def test_invalid_citations_are_stripped(self):
        out = _normalize({
            'summary': 'Fact one [1]. Made up [9].',
            'key_findings': ['Finding [2] and [7]'],
            'perspectives': {'BBC': 'Covers it [1]'},
        }, max_ref=2)
        self.assertEqual(out['summary'], 'Fact one [1]. Made up .')
        self.assertEqual(out['key_findings'][0]['sources'], [2])
        self.assertEqual(out['perspectives'][0]['source'], 'BBC')

    def test_chart_uses_real_counts_and_needs_two_groups(self):
        self.assertIsNone(build_chart({'source_breakdown': [{'source_name': 'BBC', 'count': 3}]}))
        chart = build_chart({'source_breakdown': [
            {'source_name': 'BBC', 'count': 3}, {'source_name': 'NDTV', 'count': 1}]})
        self.assertEqual(chart['data'], [{'label': 'BBC', 'count': 3}, {'label': 'NDTV', 'count': 1}])


class AIQueryEndpointTests(TestCase):
    url = '/api/v1/ai/query/'

    def setUp(self):
        cache.clear()   # reset rate-limit counters between tests
        make_article('OpenAI launches new AI model', summary='The AI lab released a model.')
        make_article('Google expands AI search', source='TechCrunch', summary='AI search grows.')

    def post(self, body):
        return self.client.post(self.url, data=json.dumps(body), content_type='application/json')

    def test_empty_query_is_rejected(self):
        self.assertEqual(self.post({'query': '  '}).status_code, 400)

    def test_bad_max_articles_does_not_crash(self):
        with mock.patch('ai_analysis.views.analyze_news_query', return_value={'ok': True}):
            self.assertEqual(self.post({'query': 'AI', 'max_articles': 'abc'}).status_code, 200)

    def test_no_matches_skips_gemini(self):
        with mock.patch('ai_analysis.gemini_client.get_gemini_client') as client:
            res = self.post({'query': 'volcanic eruptions in Iceland'})
        client.assert_not_called()
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['answer_status'], 'insufficient')
        self.assertEqual(res.json()['citations'], [])

    @override_settings(GEMINI_API_KEY='', DEBUG=True)
    def test_missing_api_key_returns_503_with_hint_for_developer(self):
        with mock.patch.dict('os.environ', {'GEMINI_API_KEY': ''}):
            res = self.post({'query': 'AI'})
        self.assertEqual(res.status_code, 503)
        self.assertIn('GEMINI_API_KEY', res.json()['error'])

    @override_settings(GEMINI_API_KEY='', DEBUG=False)
    def test_missing_api_key_hides_setup_details_from_public(self):
        with mock.patch.dict('os.environ', {'GEMINI_API_KEY': ''}):
            res = self.post({'query': 'AI'})
        self.assertEqual(res.status_code, 503)
        self.assertNotIn('.env', res.json()['error'])

    def _fake_client(self, *, text=None, parsed=None, error=None):
        client = mock.Mock()
        if error is not None:
            client.models.generate_content.side_effect = error
        else:
            client.models.generate_content.return_value = mock.Mock(text=text, parsed=parsed)
        return client

    def test_full_answer_shape(self):
        fake = self._fake_client(text=json.dumps({
            'answer_status': 'answered',
            'summary': 'OpenAI released a model [1] and Google expanded search [2].',
            'key_findings': [{'text': 'A model launched [1]', 'sources': [1]}],
            'analysis': 'Competition is rising [1][2].',
            'perspectives': [],
            'entities': {'organizations': ['OpenAI', 'Google'], 'people': [], 'locations': []},
            'limitations': '',
        }))
        with mock.patch('ai_analysis.gemini_client.get_gemini_client', return_value=fake):
            res = self.post({'query': 'AI developments'})
        data = res.json()
        self.assertEqual(res.status_code, 200)
        self.assertEqual(data['articles_used_count'], 2)
        self.assertEqual([c['ref'] for c in data['citations']], [1, 2])
        self.assertTrue(all(c['url'].startswith('https://') for c in data['citations']))
        self.assertEqual(data['chart']['x_key'], 'label')
        self.assertEqual(data['entities']['organizations'], ['OpenAI', 'Google'])

    def test_schema_parsed_response_is_used(self):
        from .gemini_client import ResearchAnswer
        answer = ResearchAnswer(answer_status='partial', summary='Only one source [1].')
        fake = self._fake_client(parsed=answer, text='ignored')
        with mock.patch('ai_analysis.gemini_client.get_gemini_client', return_value=fake):
            data = self.post({'query': 'AI developments'}).json()
        self.assertEqual(data['answer_status'], 'partial')
        self.assertEqual(data['summary'], 'Only one source [1].')

    @override_settings(GEMINI_MODEL='test-model')
    def test_request_uses_new_sdk_with_schema_and_system_instruction(self):
        from google.genai import types
        from .gemini_client import ResearchAnswer
        fake = self._fake_client(text=json.dumps({'answer_status': 'answered', 'summary': 'x [1]'}))
        with mock.patch('ai_analysis.gemini_client.get_gemini_client', return_value=fake):
            data = self.post({'query': 'AI developments'}).json()
        kwargs = fake.models.generate_content.call_args.kwargs
        self.assertEqual(kwargs['model'], 'test-model')
        self.assertIsInstance(kwargs['config'], types.GenerateContentConfig)
        self.assertIs(kwargs['config'].response_schema, ResearchAnswer)
        self.assertIn('ONLY the numbered news articles', kwargs['config'].system_instruction)
        self.assertIn('[1] ', kwargs['contents'])
        self.assertEqual(data['model'], 'test-model')

    def test_gemini_failure_returns_502(self):
        fake = self._fake_client(error=RuntimeError('quota exceeded'))
        with mock.patch('ai_analysis.gemini_client.get_gemini_client', return_value=fake):
            res = self.post({'query': 'AI developments'})
        self.assertEqual(res.status_code, 502)
        self.assertNotIn('quota', res.json()['error'])   # internal details stay in the logs

    def test_sdk_errors_map_to_clear_statuses(self):
        import httpx
        from google.genai import errors as genai_errors

        def api_error(code):
            body = {'error': {'code': code, 'message': 'internal detail', 'status': 'X'}}
            cls = genai_errors.ServerError if code >= 500 else genai_errors.ClientError
            return cls(code, body)

        cases = [
            (api_error(429), 503, 'busy'),
            (api_error(404), 503, None),
            (api_error(403), 503, None),
            (api_error(400), 502, 'rephrasing'),
            (api_error(500), 502, 'try again'),
            (httpx.ReadTimeout('slow'), 504, 'too long'),
        ]
        for error, status_code, phrase in cases:
            with self.subTest(error=error):
                cache.clear()
                fake = self._fake_client(error=error)
                with mock.patch('ai_analysis.gemini_client.get_gemini_client', return_value=fake):
                    res = self.post({'query': 'AI developments'})
                self.assertEqual(res.status_code, status_code)
                self.assertNotIn('internal detail', res.json()['error'])
                if phrase:
                    self.assertIn(phrase, res.json()['error'])

    def test_empty_model_reply_is_an_error(self):
        fake = self._fake_client(text=None, parsed=None)
        with mock.patch('ai_analysis.gemini_client.get_gemini_client', return_value=fake):
            res = self.post({'query': 'AI developments'})
        self.assertEqual(res.status_code, 502)


class GeminiClientSetupTests(TestCase):
    @override_settings(GEMINI_API_KEY='key-123')
    def test_client_is_built_once_with_timeout_and_retries(self):
        from . import gemini_client
        gemini_client._client_cache.clear()
        with mock.patch('ai_analysis.gemini_client.genai.Client') as Client:
            first = gemini_client.get_gemini_client()
            second = gemini_client.get_gemini_client()
        self.assertIs(first, second)
        Client.assert_called_once()
        options = Client.call_args.kwargs['http_options']
        self.assertEqual(Client.call_args.kwargs['api_key'], 'key-123')
        self.assertEqual(options.timeout, gemini_client.REQUEST_TIMEOUT_MS)
        self.assertEqual(options.retry_options.attempts, gemini_client.RETRY_ATTEMPTS)
        gemini_client._client_cache.clear()
