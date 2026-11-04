# backend/config/settings.py
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

from django.core.exceptions import ImproperlyConfigured


def env_int(name, default):
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def env_list(name, default):
    return [v.strip() for v in os.getenv(name, default).split(',') if v.strip()]


INSECURE_DEV_KEY = 'django-insecure-fallback-key'
SECRET_KEY = os.getenv('SECRET_KEY', INSECURE_DEV_KEY)
DEBUG = os.getenv('DEBUG', 'True') == 'True'
ALLOWED_HOSTS = env_list('ALLOWED_HOSTS', 'localhost,127.0.0.1')

# Never run a live (non-debug) site with the placeholder key.
if not DEBUG and SECRET_KEY in ('', INSECURE_DEV_KEY, 'your-secret-key-here'):
    raise ImproperlyConfigured('Set a real SECRET_KEY in backend/.env before running with DEBUG=False.')

# Admin lives at /admin/ by default; set ADMIN_URL to something hard to guess in production.
ADMIN_URL = os.getenv('ADMIN_URL', 'admin/').strip('/') + '/'

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third-party
    'rest_framework',
    'corsheaders',
    # Local apps
    'news',
    'ai_analysis',
    'scraper',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',   # must be first
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database configuration: Supabase (PostgreSQL) when DB_PASSWORD / DATABASE_URL configured, or fallback to SQLite
SUPABASE_DB_PASSWORD = os.getenv('DB_PASSWORD')
DATABASE_URL = os.getenv('DATABASE_URL')

if SUPABASE_DB_PASSWORD or DATABASE_URL:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('DB_NAME', 'postgres'),
            'USER': os.getenv('DB_USER', 'postgres.vlxxaowmldcrgqcvcbsa'),
            'PASSWORD': SUPABASE_DB_PASSWORD or '',
            'HOST': os.getenv('DB_HOST', 'aws-0-ap-southeast-1.pooler.supabase.com'),
            'PORT': os.getenv('DB_PORT', '6543'),
            'OPTIONS': {
                'sslmode': 'require',
            },
        }
    }
else:
    # SQLite fallback
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# CORS — allow Next.js dev server to call this API
CORS_ALLOWED_ORIGINS = os.getenv(
    'CORS_ALLOWED_ORIGINS', 'http://localhost:3000'
).split(',')
CORS_ALLOW_CREDENTIALS = True

# ---------------------------------------------------------------------------
# Rate limits (see config/throttles.py). All values can be changed in .env.
# ---------------------------------------------------------------------------
AI_DAILY_LIMIT          = env_int('AI_DAILY_LIMIT', 5)            # AI questions per visitor per day
AI_BURST_LIMIT          = env_int('AI_BURST_LIMIT', 3)            # AI questions per visitor per minute
SCRAPE_COOLDOWN_MINUTES = env_int('SCRAPE_COOLDOWN_MINUTES', 15)  # one Sync Feeds per N minutes, site-wide
API_REQUESTS_PER_MINUTE = env_int('API_REQUESTS_PER_MINUTE', 120) # all other API calls, per visitor

# How many reverse proxies (nginx, a load balancer...) sit in front of Django.
# 0 = use the direct connection IP and IGNORE X-Forwarded-For, so visitors
# can't fake their IP to dodge limits. Set to 1 behind a single proxy.
NUM_PROXIES = env_int('NUM_PROXIES', 0)

# Servers allowed to skip the general limit (e.g. Next.js rendering article
# pages from the same machine). AI and Sync Feeds limits still apply to them.
THROTTLE_EXEMPT_IPS = env_list('THROTTLE_EXEMPT_IPS', '127.0.0.1,::1')

# Rate-limit counters live in the cache. In-memory is fine locally;
# use Redis (django.core.cache.backends.redis.RedisCache) in production.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'newsorbit-default',
    }
}

# Django REST Framework defaults
REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_RENDERER_CLASSES': ['rest_framework.renderers.JSONRenderer'],
    'DEFAULT_PARSER_CLASSES': ['rest_framework.parsers.JSONParser'],
    'DEFAULT_THROTTLE_CLASSES': ['config.throttles.GeneralAnonThrottle'],
    'DEFAULT_THROTTLE_RATES': {
        'anon':           f'{API_REQUESTS_PER_MINUTE}/m',
        'ai_query':       f'{AI_DAILY_LIMIT}/d',
        'ai_burst':       f'{AI_BURST_LIMIT}/m',
        'scrape_trigger': f'1/{SCRAPE_COOLDOWN_MINUTES}m',
    },
    'NUM_PROXIES': NUM_PROXIES,
    'EXCEPTION_HANDLER': 'config.exceptions.api_exception_handler',
}

# ---------------------------------------------------------------------------
# Request size & browser security headers
# ---------------------------------------------------------------------------
DATA_UPLOAD_MAX_MEMORY_SIZE = 256 * 1024     # API bodies are tiny; reject huge payloads
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'

if not DEBUG:
    # Production (HTTPS) hardening. SECURE_SSL_REDIRECT can be turned off if
    # your host/proxy already forces HTTPS.
    SECURE_SSL_REDIRECT = os.getenv('SECURE_SSL_REDIRECT', 'True') == 'True'
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = env_int('SECURE_HSTS_SECONDS', 60 * 60 * 24 * 30)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    if NUM_PROXIES:
        SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    CSRF_TRUSTED_ORIGINS = env_list('CSRF_TRUSTED_ORIGINS', '')

# Gemini — loaded from .env, never exposed to the frontend
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
# Model and optional thinking level (low / medium / high). Leave empty for defaults
# (see ai_analysis/gemini_client.py: DEFAULT_MODEL).
GEMINI_MODEL = os.getenv('GEMINI_MODEL', '')
GEMINI_THINKING_LEVEL = os.getenv('GEMINI_THINKING_LEVEL', '')

# Logging — scraper and AI errors go to console during development
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'scraper': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'ai_analysis': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'news': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
    },
}
