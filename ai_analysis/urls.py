# backend/ai_analysis/urls.py
from django.urls import path
from .views import AIQueryView

urlpatterns = [
    path('query/', AIQueryView.as_view(), name='ai-query'),
]
