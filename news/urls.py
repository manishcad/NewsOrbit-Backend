# news/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('articles/',               views.ArticleListView.as_view(),   name='article-list'),
    path('articles/<int:pk>/',      views.ArticleDetailView.as_view(), name='article-detail'),
    path('categories/',             views.CategoriesView.as_view(),    name='categories'),
    path('sources/',                views.SourcesView.as_view(),       name='sources'),
    path('stats/',                  views.StatsView.as_view(),         name='stats'),
    path('scraper-runs/',           views.ScraperRunListView.as_view(),name='scraper-runs'),
]
