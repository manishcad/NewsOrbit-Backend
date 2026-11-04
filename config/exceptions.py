# backend/config/exceptions.py
"""
API error formatting.

Every error goes out as {"error": "...readable message..."} so the frontend can
show it directly. Rate-limit errors also include "retry_after" in seconds.
"""
import math

from rest_framework.exceptions import Throttled
from rest_framework.views import exception_handler

THROTTLE_MESSAGES = {
    'ai_query': "You've used all of today's AI research questions. Your allowance resets in {wait}.",
    'ai_burst': "You're asking questions too quickly. Please wait {wait} and try again.",
    'scrape_trigger': 'News feeds were synced recently. The next sync is available in {wait}.',
}
DEFAULT_THROTTLE_MESSAGE = 'Too many requests. Please wait {wait} and try again.'


def _human_wait(seconds):
    seconds = max(1, math.ceil(seconds or 1))
    if seconds < 60:
        return f'{seconds} second{"s" if seconds != 1 else ""}'
    minutes = math.ceil(seconds / 60)
    if minutes < 60:
        return f'{minutes} minute{"s" if minutes != 1 else ""}'
    hours = math.ceil(minutes / 60)
    return f'{hours} hour{"s" if hours != 1 else ""}'


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None   # unhandled -> Django's normal 500 handling

    if isinstance(exc, Throttled):
        scope = getattr(context.get('request'), 'throttle_scope', None)
        template = THROTTLE_MESSAGES.get(scope, DEFAULT_THROTTLE_MESSAGE)
        response.data = {
            'error': template.format(wait=_human_wait(exc.wait)),
            'retry_after': math.ceil(exc.wait or 0),
            'limit': scope or 'general',
        }
        return response

    if isinstance(response.data, dict) and 'detail' in response.data and 'error' not in response.data:
        response.data = {'error': str(response.data['detail'])}
    return response
