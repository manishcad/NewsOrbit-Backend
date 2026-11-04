# scraper/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('trigger/',  views.TriggerScrapeView.as_view(),    name='scraper-trigger'),
    path('status/',   views.ScrapeStatusView.as_view(),     name='scraper-status'),
    path('sources/',  views.AvailableSourcesView.as_view(), name='scraper-sources'),
]
