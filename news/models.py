# news/models.py
import hashlib
from django.db import models
from django.utils import timezone


class NewsArticle(models.Model):
    """
    Stores a single news article collected from any source.
    URL hash is used as the primary duplicate-detection key.
    """

    CATEGORY_CHOICES = [
        ('national',        'National'),
        ('international',   'International'),
        ('politics',        'Politics'),
        ('business',        'Business'),
        ('technology',      'Technology'),
        ('sports',          'Sports'),
        ('entertainment',   'Entertainment'),
        ('health',          'Health'),
        ('education',       'Education'),
        ('science',         'Science'),
        ('environment',     'Environment'),
        ('other',           'Other'),
    ]

    # Core content
    title       = models.CharField(max_length=1024)
    content     = models.TextField(blank=True, default='')
    summary     = models.TextField(blank=True, default='')   # excerpt / lead paragraph

    # Source metadata
    source_name = models.CharField(max_length=255, db_index=True)
    url         = models.URLField(max_length=2048, unique=True)
    url_hash    = models.CharField(max_length=64, unique=True, db_index=True)
    image_url   = models.URLField(max_length=2048, blank=True, default='')
    category    = models.CharField(max_length=64, choices=CATEGORY_CHOICES,
                                   default='other', db_index=True)
    author      = models.CharField(max_length=512, blank=True, default='')
    language    = models.CharField(max_length=16, default='en')

    # Dates
    published_at  = models.DateTimeField(null=True, blank=True, db_index=True)
    collected_at  = models.DateTimeField(default=timezone.now, db_index=True)

    # Full-text search helper: pre-built lowercase blob for LIKE queries
    search_vector = models.TextField(blank=True, default='')

    class Meta:
        ordering = [models.F('published_at').desc(nulls_last=True), '-collected_at']
        indexes = [
            models.Index(fields=['source_name', 'category']),
            models.Index(fields=['category', 'published_at']),
            models.Index(fields=['collected_at']),
        ]
        verbose_name = 'News Article'
        verbose_name_plural = 'News Articles'

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def make_url_hash(url: str) -> str:
        return hashlib.sha256(url.strip().lower().encode()).hexdigest()

    def build_search_vector(self) -> str:
        """Concatenate searchable text fields into one lowercase blob."""
        parts = [self.title, self.summary, self.content,
                 self.source_name, self.author, self.category]
        return ' '.join(p for p in parts if p).lower()

    def save(self, *args, **kwargs):
        if not self.url_hash:
            self.url_hash = self.make_url_hash(self.url)
        self.search_vector = self.build_search_vector()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'[{self.source_name}] {self.title[:80]}'


class ScraperRun(models.Model):
    """
    Records each scraper execution so we can track status,
    prevent duplicate runs, and expose stats via the API.
    """

    STATUS_CHOICES = [
        ('running',   'Running'),
        ('completed', 'Completed'),
        ('failed',    'Failed'),
    ]

    source_name    = models.CharField(max_length=255)
    status         = models.CharField(max_length=32, choices=STATUS_CHOICES,
                                      default='running', db_index=True)
    started_at     = models.DateTimeField(default=timezone.now)
    finished_at    = models.DateTimeField(null=True, blank=True)
    articles_found = models.IntegerField(default=0)
    articles_new   = models.IntegerField(default=0)
    error_message  = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-started_at']
        verbose_name = 'Scraper Run'
        verbose_name_plural = 'Scraper Runs'

    def __str__(self):
        return f'{self.source_name} — {self.status} @ {self.started_at:%Y-%m-%d %H:%M}'
