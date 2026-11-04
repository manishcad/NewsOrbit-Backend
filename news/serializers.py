# news/serializers.py
from rest_framework import serializers
from .models import NewsArticle, ScraperRun


class NewsArticleSerializer(serializers.ModelSerializer):
    class Meta:
        model  = NewsArticle
        fields = [
            'id', 'title', 'summary', 'source_name', 'url',
            'image_url', 'category', 'author', 'language',
            'published_at', 'collected_at',
        ]


class NewsArticleDetailSerializer(serializers.ModelSerializer):
    """Full detail including content (used for the single-article endpoint)."""
    class Meta:
        model  = NewsArticle
        fields = '__all__'
        exclude_fields = ['search_vector', 'url_hash']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data.pop('search_vector', None)
        data.pop('url_hash', None)
        return data


class ScraperRunSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ScraperRun
        fields = '__all__'

