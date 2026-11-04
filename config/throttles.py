# backend/config/throttles.py
"""
Rate limits for the NewsOrbit API (built on DRF throttling, no extra packages).

- GeneralAnonThrottle: broad per-visitor limit on every endpoint, to stop scraping
  of the API and request floods. Trusted server IPs (e.g. the Next.js server
  rendering article pages) are exempt.
- AIQueryThrottle:  daily AI questions per visitor (Gemini costs money).
- AIBurstThrottle:  stops rapid-fire AI requests (scripts, double clicks).
- ScrapeTriggerThrottle: ONE "Sync Feeds" per cooldown for the WHOLE site,
  no matter who presses it.

Limits are counted in Django's cache. Locally that is in-memory (resets when the
server restarts). In production use a shared cache such as Redis so every server
process sees the same counts.

Visitors are identified by IP address. NUM_PROXIES in settings controls whether
X-Forwarded-For is trusted, so a visitor can't fake a new IP to reset limits.
"""
from django.conf import settings
from rest_framework.throttling import SimpleRateThrottle

PERIODS = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}


class FlexibleRateMixin:
    """Accept rates like "5/day", "1/15m" or "2/30s" (DRF alone only allows 1 unit)."""

    def parse_rate(self, rate):
        if rate is None:
            return (None, None)
        num, period = rate.split('/')
        digits = ''.join(ch for ch in period if ch.isdigit())
        unit = period[len(digits):][:1]
        return int(num), int(digits or 1) * PERIODS[unit]

    def refund(self):
        """Undo this request's count (e.g. the request was invalid or failed)."""
        if getattr(self, 'history', None) and getattr(self, 'key', None):
            self.history.pop(0)   # throttle_success() inserted the newest at index 0
            self.cache.set(self.key, self.history, self.duration)


class GeneralAnonThrottle(FlexibleRateMixin, SimpleRateThrottle):
    scope = 'anon'

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        if ident in getattr(settings, 'THROTTLE_EXEMPT_IPS', []):
            return None   # trusted server, e.g. Next.js server-side rendering
        return self.cache_format % {'scope': self.scope, 'ident': ident}


class AIQueryThrottle(FlexibleRateMixin, SimpleRateThrottle):
    """Daily AI question allowance per visitor."""
    scope = 'ai_query'

    def get_cache_key(self, request, view):
        return self.cache_format % {'scope': self.scope, 'ident': self.get_ident(request)}

    @property
    def remaining(self):
        history = getattr(self, 'history', None)
        if history is None or self.num_requests is None:
            return None
        return max(0, self.num_requests - len(history))


class AIBurstThrottle(FlexibleRateMixin, SimpleRateThrottle):
    scope = 'ai_burst'

    def get_cache_key(self, request, view):
        return self.cache_format % {'scope': self.scope, 'ident': self.get_ident(request)}


class ScrapeTriggerThrottle(FlexibleRateMixin, SimpleRateThrottle):
    """Site-wide cooldown: one sync for everybody, not one per visitor."""
    scope = 'scrape_trigger'

    def get_cache_key(self, request, view):
        return 'throttle_scrape_trigger_sitewide'


class NamedThrottleMixin:
    """
    View mixin that:
    - stops at the first failing throttle, so a blocked request doesn't use up
      the visitor's other allowances (e.g. a burst block doesn't eat a daily question);
    - records which limit was hit (request.throttle_scope) for a clear error message;
    - keeps the throttle instances on the view (self.active_throttles).
    """

    def check_throttles(self, request):
        self.active_throttles = []
        for throttle in self.get_throttles():
            self.active_throttles.append(throttle)
            if not throttle.allow_request(request, self):
                request.throttle_scope = getattr(throttle, 'scope', None)
                self.throttled(request, throttle.wait())

    def get_throttle(self, cls):
        return next((t for t in getattr(self, 'active_throttles', []) if isinstance(t, cls)), None)
