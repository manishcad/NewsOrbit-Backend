# news/admin.py
from django.contrib import admin
from .models import NewsArticle, ScraperRun


@admin.register(NewsArticle)
class NewsArticleAdmin(admin.ModelAdmin):
    list_display  = ['title', 'source_name', 'category', 'published_at', 'collected_at']
    list_filter   = ['category', 'source_name', 'language']
    search_fields = ['title', 'source_name', 'author']
    readonly_fields = ['url_hash', 'search_vector', 'collected_at']
    ordering      = ['-published_at']
    date_hierarchy = 'published_at'


@admin.register(ScraperRun)
class ScraperRunAdmin(admin.ModelAdmin):
    list_display  = ['source_name', 'status', 'articles_found',
                     'articles_new', 'started_at', 'finished_at']
    list_filter   = ['status', 'source_name']
    readonly_fields = ['started_at']
    ordering      = ['-started_at']
