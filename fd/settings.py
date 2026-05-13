"""
Django settings for fd project.
Pronto para produção no Render.com com domínio personalizado.
"""

from pathlib import Path
import os
import dj_database_url
from decouple import config

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Quick-start development settings - unsuitable for production
SECRET_KEY = config('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=False, cast=bool)

# ======================================================================
# CONFIGURAÇÃO DOS HOSTS PERMITIDOS
# ======================================================================
ALLOWED_HOSTS = []

# Puxa hosts extras do arquivo .env se existirem
hosts_env = config('ALLOWED_HOSTS', default='')
if hosts_env:
    ALLOWED_HOSTS.extend([host.strip() for host in hosts_env.split(',')])

# Domínios de produção e locais atualizados
CUSTOM_DOMAINS = [
    'fd.art',
    'www.fd.art',
    'one00xmagico.onrender.com',
    '127.0.0.1',
    'localhost',
]

for domain in CUSTOM_DOMAINS:
    if domain not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(domain)

if not DEBUG:
    RENDER_EXTERNAL_HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
    if RENDER_EXTERNAL_HOSTNAME and RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # WhiteNoise para arquivos estáticos
    'whitenoise.runserver_nostatic',
    
    'core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware', 
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'fd.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
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

WSGI_APPLICATION = 'fd.wsgi.application'

# ======================================================================
# DATABASE (PostgreSQL no Render / SQLite local)
# ======================================================================
DATABASES = {
    'default': dj_database_url.config(
        default=config('DATABASE_URL', default=f'sqlite:///{BASE_DIR}/db.sqlite3'),
        conn_max_age=600
    )
}

# Internationalization
LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'Africa/Luanda'
USE_I18N = True
USE_TZ = True

# ======================================================================
# STATIC FILES (CSS, JS, Imagens do Sistema)
# ======================================================================
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

# Armazenamento de arquivos estáticos (WhiteNoise com compressão)
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# ======================================================================
# MEDIA FILES (Uploads de usuários)
# ======================================================================
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

if not os.path.exists(MEDIA_ROOT):
    os.makedirs(MEDIA_ROOT)

# ======================================================================
# SEGURANÇA E REDIRECIONAMENTO
# ======================================================================
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'core.CustomUser'
LOGIN_URL = 'login'

if not DEBUG:
    # Essencial para o Render identificar o HTTPS vindo do proxy
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True
    
    # Cookies seguros
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    
    # Proteções básicas de navegador
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    
    # Redirecionamento de domínio
    PREPEND_WWW = False

    # HSTS (Ativado para segurança máxima)
    SECURE_HSTS_SECONDS = 31536000  # 1 ano
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    