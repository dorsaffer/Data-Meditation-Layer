from pathlib import Path
from datetime import timedelta
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-insecure-key-replace-before-production')
DEBUG = os.environ.get('DEBUG', 'True') == 'True'
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1,backend').split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'apps.dhis2',
    'apps.data_products',
    'apps.fhir',
    'apps.terminology',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
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

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('POSTGRES_DB', 'mediation'),
        'USER': os.environ.get('POSTGRES_USER', 'mediation'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD', 'mediation'),
        'HOST': os.environ.get('POSTGRES_HOST', 'db'),
        'PORT': os.environ.get('POSTGRES_PORT', '5432'),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'AUTH_HEADER_TYPES': ('Bearer',),
}

CORS_ALLOWED_ORIGINS = os.environ.get(
    'CORS_ALLOWED_ORIGINS',
    'http://localhost:3000,http://127.0.0.1:3000',
).split(',')

# DHIS2 connection config (official Sierra Leone demo, DHIS2 demo service).
# play.dhis2.org/dev is the stable public alias; it 302-redirects to a
# versioned play.im.dhis2.org host that changes over time, which is why
# this is env-configurable rather than pointing at the versioned host
# directly. See apps/core/services/dhis2_client.py for how auth is kept
# across that redirect (requests/curl both drop Authorization on a
# cross-host redirect by default).
DHIS2_BASE_URL = os.environ.get('DHIS2_BASE_URL', 'https://play.dhis2.org/dev')
DHIS2_USERNAME = os.environ.get('DHIS2_USERNAME', 'admin')
DHIS2_PASSWORD = os.environ.get('DHIS2_PASSWORD', 'district')
DHIS2_TIMEOUT_SECONDS = int(os.environ.get('DHIS2_TIMEOUT_SECONDS', '15'))

# FR6.3: self-hosted FHIR R4 conformity validator (HAPI FHIR JPA server,
# see docker-compose.yml's fhir-validator service). Self-hosted rather
# than a public test server so exported resources never leave our trust
# boundary, even though they carry no patient-level data.
FHIR_VALIDATOR_URL = os.environ.get('FHIR_VALIDATOR_URL', 'http://fhir-validator:8080/fhir')
FHIR_VALIDATOR_TIMEOUT_SECONDS = int(os.environ.get('FHIR_VALIDATOR_TIMEOUT_SECONDS', '30'))
