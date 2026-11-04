# backend/config/urls.py
from django.conf import settings
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path('api/v1/news/', include('news.urls')),
    path('api/v1/ai/', include('ai_analysis.urls')),
    path('api/v1/scraper/', include('scraper.urls')),
]
