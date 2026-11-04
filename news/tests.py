# backend/news/tests.py
from django.test import TestCase
from django.utils import timezone

from .models import NewsArticle


class ArticleApiParamTests(TestCase):
    def setUp(self):
        NewsArticle.objects.create(
            title='Test story', source_name='BBC News', category='technology',
            url='https://example.com/test-story', published_at=timezone.now(),
        )

    def test_invalid_params_fall_back_instead_of_500(self):
        for url in [
            '/api/v1/news/articles/?ordering=foo',
            '/api/v1/news/articles/?ordering=search_vector',
            '/api/v1/news/articles/?days=abc',
            '/api/v1/news/articles/?days=-5',
            '/api/v1/news/stats/?days=x',
        ]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_valid_ordering_still_works(self):
        res = self.client.get('/api/v1/news/articles/?ordering=title')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['count'], 1)
