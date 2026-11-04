# backend/ai_analysis/retriever.py
"""
Retrieval module for AI analysis.

Turns a natural-language question into a ranked list of relevant articles
from the local database, plus real (never invented) counts for charts.

Matching rules:
- Keywords are matched on WHOLE WORDS, so "ai" no longer matches "said",
  and "national" no longer matches "international".
- Category words ("tech", "world", "business"...) and time words
  ("today", "this week") steer the search but are not required matches.
- If nothing relevant is found we return an empty list, so the AI tells
  the user the database lacks coverage instead of answering from
  unrelated articles.
"""
import re
from datetime import timedelta

from django.db.models import Q, Count
from django.utils import timezone

from news.models import NewsArticle


STOPWORDS = {
    'a', 'about', 'above', 'after', 'again', 'against', 'all', 'am', 'an', 'and', 'any',
    'are', 'as', 'at', 'be', 'because', 'been', 'before', 'being', 'below', 'between',
    'both', 'but', 'by', 'can', 'could', 'did', 'do', 'does', 'doing', 'down', 'during',
    'each', 'few', 'for', 'from', 'further', 'had', 'has', 'have', 'having', 'he',
    'her', 'here', 'hers', 'herself', 'him', 'himself', 'his', 'how', 'i', 'if', 'in',
    'into', 'is', 'it', 'its', 'itself', 'just', 'me', 'more', 'most', 'my', 'myself',
    'no', 'nor', 'not', 'now', 'of', 'off', 'on', 'once', 'only', 'or', 'other', 'ought',
    'our', 'ours', 'ourselves', 'out', 'over', 'own', 'same', 'she', 'should', 'so',
    'some', 'such', 'than', 'that', 'the', 'their', 'theirs', 'them', 'themselves',
    'then', 'there', 'these', 'they', 'this', 'those', 'through', 'to', 'too', 'under',
    'until', 'up', 'very', 'was', 'we', 'were', 'what', 'when', 'where', 'which', 'while',
    'who', 'whom', 'why', 'with', 'would', 'you', 'your', 'yours', 'yourself', 'yourselves',
    'tell', 'find', 'show', 'summarize', 'summarise', 'summary', 'explain', 'compare',
    'news', 'articles', 'article', 'latest', 'recent', 'recently', 'today', 'week',
    'month', 'database', 'give', 'get', 'happened', 'happening', 'developments',
    'development', 'update', 'updates', 'major', 'biggest', 'top', 'key', 'main',
    'report', 'reports', 'reporting', 'different', 'another', 'regarding', 'related',
    'potential', 'effects', 'impact', 'things', 'stories', 'story', 'please', 'year',
    'yesterday', 'past', 'last', 'days', 'day', 'weeks', 'months', 'many', 'much',
    'also', 'new', 'like', 'know', 'want', 'trends', 'trend', 'outlets', 'outlet',
    'sources', 'source', 'coverage', 'covered', 'cover', 'events', 'event', 'us',
    'announcements', 'announcement', 'publishers', 'publisher',
}

# Words in a question that point at a category. Matched as whole words.
CATEGORY_HINTS = {
    'international': ['international', 'world', 'global', 'foreign'],
    'national':      ['national', 'india', 'indian', 'domestic'],
    'politics':      ['politics', 'political', 'election', 'elections', 'government', 'parliament'],
    'business':      ['business', 'economy', 'economic', 'market', 'markets', 'finance',
                      'financial', 'stocks', 'companies', 'company'],
    'technology':    ['technology', 'tech', 'ai', 'software', 'startup', 'startups', 'gadgets'],
    'sports':        ['sports', 'sport', 'cricket', 'football', 'tennis', 'olympics'],
    'entertainment': ['entertainment', 'movie', 'movies', 'film', 'films', 'music', 'celebrity'],
    'health':        ['health', 'medical', 'medicine', 'disease', 'diseases', 'hospital'],
    'education':     ['education', 'school', 'schools', 'university', 'exam', 'exams'],
    'science':       ['science', 'scientific', 'research', 'space', 'climate'],
    'environment':   ['environment', 'environmental', 'pollution', 'wildlife'],
}

# Category words that are also meaningful topics and should still be matched
# in article text (e.g. "AI" is both a tech hint and a real topic).
TOPIC_CATEGORY_WORDS = {'ai', 'election', 'elections', 'cricket', 'football', 'tennis',
                        'olympics', 'climate', 'space', 'startup', 'startups', 'pollution',
                        'stocks', 'parliament', 'economy', 'economic', 'india', 'indian'}

# Very common words: they rank results but cannot qualify an article alone
# when the question also has a more specific keyword.
WEAK_KEYWORDS = {'india', 'indian'}

# Generic desks that should not dominate when a more specific desk is named
# (e.g. "Indian economy" -> business, not every national crime story).
GENERIC_CATEGORIES = {'national'}

# Expand short or ambiguous terms to the phrases articles actually use.
SYNONYMS = {
    'ai':       ['ai', 'artificial intelligence', 'genai', 'llm', 'chatgpt', 'openai'],
    'ev':       ['ev', 'evs', 'electric vehicle', 'electric vehicles'],
    'rbi':      ['rbi', 'reserve bank'],
    'us':       ['u.s.', 'united states'],
    'uk':       ['uk', 'britain', 'united kingdom'],
    'economy':  ['economy', 'economic', 'gdp', 'inflation', 'growth rate'],
    'economic': ['economy', 'economic', 'gdp', 'inflation', 'growth rate'],
    'india':    ['india', 'indian'],
    'indian':   ['india', 'indian'],
}

# Publisher names a user may mention -> stored source_name prefix.
# A named publisher becomes a source filter instead of a text keyword.
SOURCE_ALIASES = {
    'bbc': 'BBC', 'reuters': 'Reuters', 'hindu': 'The Hindu', 'ndtv': 'NDTV',
    'al jazeera': 'Al Jazeera', 'aljazeera': 'Al Jazeera', 'techcrunch': 'TechCrunch',
    'times of india': 'Times of India', 'toi': 'Times of India',
    'hacker news': 'Hacker News', 'cricinfo': 'ESPNcricinfo', 'espn': 'ESPNcricinfo',
    'odisha tv': 'Odisha TV', 'otv': 'Odisha TV', 'news18': 'News18', 'kanak': 'Kanak News',
}

# Upper-case acronyms that clash with stopwords ("WHO" vs "who").
ACRONYM_SOURCES = {'WHO': 'WHO'}
ACRONYM_KEYWORDS = {'US': 'us'}

# Time words -> look-back window in days.
TIME_HINTS = [
    (r'\btoday\b|\bpast 24 hours\b|\blast 24 hours\b', 1),
    (r'\byesterday\b', 2),
    (r'\bthis week\b|\bpast week\b|\blast week\b|\bweekly\b', 7),
    (r'\bthis month\b|\bpast month\b|\blast month\b|\bmonthly\b', 31),
]

# How many recent candidates to score in Python. SQLite has no relevance
# ranking, so we narrow with a cheap SQL filter, then score precisely.
CANDIDATE_POOL = 600


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9][a-z0-9\-\.']*[a-z0-9]|[a-z0-9]", text.lower())


def detect_sources(query: str) -> tuple[list[str], set[str]]:
    """
    Return (source_name_prefixes, words_consumed) for publishers named in the query.
    Consumed words are removed from the keyword list.
    """
    q = ' ' + ' '.join(_tokenize(query)) + ' '
    prefixes, consumed = [], set()
    for alias, prefix in SOURCE_ALIASES.items():
        if f' {alias} ' in q:
            if prefix not in prefixes:
                prefixes.append(prefix)
            consumed.update(alias.split())
    for acronym, prefix in ACRONYM_SOURCES.items():
        if re.search(r'\b' + acronym + r'\b', query):   # case-sensitive
            if prefix not in prefixes:
                prefixes.append(prefix)
    return prefixes, consumed


def extract_keywords(query: str, exclude: set[str] = frozenset()) -> list[str]:
    """Return de-duplicated content words from the query (order preserved)."""
    seen, keywords = set(), []
    for w in _tokenize(query):
        if w in STOPWORDS or w in seen or w in exclude or len(w) < 2:
            continue
        if w.isdigit() and len(w) < 4:   # keep years like 2026, drop "3"
            continue
        seen.add(w)
        keywords.append(w)
    # Upper-case acronyms that would otherwise be dropped as stopwords.
    for acronym, kw in ACRONYM_KEYWORDS.items():
        if re.search(r'\b' + acronym + r'\b', query) and kw not in seen:
            seen.add(kw)
            keywords.append(kw)
    return keywords


def detect_categories(query: str) -> list[str]:
    words = set(_tokenize(query))
    return [cat for cat, hints in CATEGORY_HINTS.items() if words & set(hints)]


def detect_time_window(query: str):
    q = query.lower()
    for pattern, days in TIME_HINTS:
        if re.search(pattern, q):
            return days
    return None


def _term_patterns(keyword: str) -> list[re.Pattern]:
    terms = SYNONYMS.get(keyword, [keyword])
    return [re.compile(r'(?<![a-z0-9])' + re.escape(t) + r'(?![a-z0-9])') for t in terms]


def _score(article: NewsArticle, keyword_patterns: dict, categories: list[str],
           sources: list[str] = ()) -> tuple[int, int]:
    """Return (distinct_keywords_matched, weighted_score) for one article."""
    title = (article.title or '').lower()
    summary = (article.summary or '').lower()
    content = (article.content or '').lower()

    matched, score = 0, 0
    for patterns in keyword_patterns.values():
        hit = 0
        for p in patterns:
            if p.search(title):
                hit = max(hit, 5)
            elif p.search(summary):
                hit = max(hit, 3)
            elif p.search(content):
                hit = max(hit, 1)
        if hit:
            matched += 1
            score += hit
    if categories and article.category in categories:
        score += 2
    if sources and any(article.source_name.startswith(p) for p in sources):
        score += 3
    return matched, score


def _sql_prefilter(keyword_patterns: dict) -> Q:
    """Cheap substring pre-filter; precise whole-word scoring happens in Python."""
    q = Q()
    for kw in keyword_patterns:
        for term in SYNONYMS.get(kw, [kw]):
            q |= Q(search_vector__icontains=term)
    return q


def _recency_key(article):
    dt = article.published_at or article.collected_at
    return dt.timestamp() if dt else 0


def retrieve_relevant_articles(query: str, max_articles: int = 12) -> tuple[list[dict], dict]:
    """
    Search the database for articles relevant to the user's question.
    Returns (articles_list, aggregate_stats). articles_list is empty when
    the database has no relevant coverage.
    """
    sources, source_words = detect_sources(query)
    keywords = extract_keywords(query, exclude=source_words)
    categories = detect_categories(query)
    if len(categories) > 1:
        specific = [c for c in categories if c not in GENERIC_CATEGORIES]
        categories = specific or categories
    window_days = detect_time_window(query)

    # Category words steer the search; they are not required content matches.
    category_words = {h for cats in CATEGORY_HINTS.values() for h in cats}
    content_keywords = [
        k for k in keywords if k not in category_words or k in TOPIC_CATEGORY_WORDS
    ]

    qs = NewsArticle.objects.all()
    if window_days:
        cutoff = timezone.now() - timedelta(days=window_days)
        qs = qs.filter(
            Q(published_at__gte=cutoff) |
            Q(published_at__isnull=True, collected_at__gte=cutoff)
        )
    newest_first = ('-published_at', '-collected_at')

    if content_keywords:
        keyword_patterns = {k: _term_patterns(k) for k in content_keywords}
        candidates = list(
            qs.filter(_sql_prefilter(keyword_patterns)).order_by(*newest_first)[:CANDIDATE_POOL]
        )
        strong_patterns = {k: p for k, p in keyword_patterns.items() if k not in WEAK_KEYWORDS}
        scored = []
        for a in candidates:
            matched, score = _score(a, keyword_patterns, categories, sources)
            if not matched:
                continue
            if strong_patterns and len(strong_patterns) < len(keyword_patterns):
                if not _score(a, strong_patterns, [], [])[0]:
                    continue   # matched only a weak word like "India"
            scored.append((matched, score, a))

        # With several keywords, prefer articles that match more than one.
        if len(content_keywords) > 1:
            multi = [s for s in scored if s[0] >= 2]
            if len(multi) >= 3:
                scored = multi

        scored.sort(key=lambda s: (s[0], s[1], _recency_key(s[2])), reverse=True)
        matching_articles = [s[2] for s in scored[:max_articles]]
        match_mode = 'keywords'

    elif sources or categories:
        # e.g. "latest business news" or "compare BBC and Al Jazeera":
        # take the newest articles from each named publisher / desk, evenly.
        groups = [qs.filter(source_name__startswith=p) for p in sources]
        groups += [qs.filter(category=c) for c in categories]
        per_group = max(2, -(-max_articles // len(groups)))
        buckets = [list(g.order_by(*newest_first)[:per_group]) for g in groups]
        matching_articles, seen = [], set()
        for i in range(per_group):
            for bucket in buckets:
                if i < len(bucket) and bucket[i].id not in seen:
                    seen.add(bucket[i].id)
                    matching_articles.append(bucket[i])
        matching_articles = matching_articles[:max_articles]
        match_mode = 'browse'

    elif window_days:
        # e.g. "what happened today?" — a general briefing of that window.
        matching_articles = list(qs.order_by(*newest_first)[:max_articles])
        match_mode = 'recent'

    else:
        matching_articles = []
        match_mode = 'none'

    # Real counts from the matched set (used for charts — never invented).
    matching_ids = [a.id for a in matching_articles]
    stats_qs = NewsArticle.objects.filter(id__in=matching_ids)
    category_counts = list(
        stats_qs.values('category').annotate(count=Count('id')).order_by('-count')
    )
    source_counts = list(
        stats_qs.values('source_name').annotate(count=Count('id')).order_by('-count')
    )

    formatted_articles = []
    for a in matching_articles:
        formatted_articles.append({
            'id': a.id,
            'title': a.title,
            'source_name': a.source_name,
            'url': a.url,
            'category': a.category,
            'image_url': a.image_url,
            'published_at': a.published_at.isoformat() if a.published_at else None,
            'summary': a.summary or (a.content or '')[:300],
            'content': (a.content or '')[:1500] if a.content else a.summary,
        })

    aggregate_stats = {
        'total_matched': len(matching_articles),
        'keywords_used': content_keywords,
        'categories_detected': categories,
        'sources_detected': sources,
        'time_window_days': window_days,
        'match_mode': match_mode,
        'category_breakdown': category_counts,
        'source_breakdown': source_counts,
    }
    return formatted_articles, aggregate_stats
