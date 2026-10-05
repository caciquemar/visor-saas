"""Configuración del visor. Todo lo que cambia entre la PC y el servidor viene del .env de la raíz
del repo (ver .env.example). Los secretos solo van ahí, nunca en el código."""
from pathlib import Path

import environ

RAIZ = Path(__file__).resolve().parents[2]          # raíz del repo
BASE_DIR = RAIZ / 'app'
DATOS = RAIZ / 'datos'                              # base local, cola y archivos en desarrollo (no va a git)
DATOS.mkdir(exist_ok=True)

env = environ.Env()
environ.Env.read_env(RAIZ / '.env')

DEBUG = env.bool('DEBUG', default=False)
SECRET_KEY = env('SECRET_KEY', default='') or ('solo-para-desarrollo-no-usar-en-produccion' if DEBUG else '')
if not SECRET_KEY:
    raise environ.ImproperlyConfigured('Falta SECRET_KEY en el .env (obligatoria con DEBUG=0)')
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['localhost', '127.0.0.1'] if DEBUG else [])
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'huey.contrib.djhuey',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
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
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# ---------------------------------------------------------------- base de datos
# Local: SQLite en datos/. Con Docker o en el servidor: DATABASE_URL=postgres://...
DATABASES = {'default': env.db('DATABASE_URL', default=f"sqlite:///{(DATOS / 'dev.sqlite3').as_posix()}")}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'es-ar'
TIME_ZONE = 'America/Argentina/Buenos_Aires'
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------- cola de tareas (Huey)
# Ver docs/decisiones.md. HUEY_INMEDIATO=1: las tareas corren en el mismo proceso (local y pruebas,
# no hace falta el consumidor). Si no, la cola va a Redis (REDIS_URL) o, sin Redis, a un SQLite en
# datos/; en ese caso hay que levantar el consumidor con:  python app/manage.py run_huey
_redis = env('REDIS_URL', default='')
HUEY = {
    'name': 'visor',
    'immediate': env.bool('HUEY_INMEDIATO', default=DEBUG),
    'utc': True,
    'consumer': {'workers': env.int('HUEY_TRABAJADORES', default=2), 'worker_type': 'thread'},
}
if _redis:
    HUEY.update(huey_class='huey.RedisHuey', url=_redis)
else:
    HUEY.update(huey_class='huey.SqliteHuey', filename=str(DATOS / 'huey.db'))

# ---------------------------------------------------------------- archivos
# ALMACENAMIENTO=local: carpeta datos/archivos/ (desarrollo). r2: Cloudflare R2 por la API de S3.
ALMACENAMIENTO = env('ALMACENAMIENTO', default='local')
STATIC_URL = 'static/'
STATIC_ROOT = DATOS / 'static'
MEDIA_URL = '/archivos/'
MEDIA_ROOT = DATOS / 'archivos'

if ALMACENAMIENTO == 'r2':
    _archivos = {
        'BACKEND': 'storages.backends.s3.S3Storage',
        'OPTIONS': {
            'bucket_name': env('R2_BUCKET'),
            'endpoint_url': f"https://{env('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
            'access_key': env('R2_ACCESS_KEY_ID'),
            'secret_key': env('R2_SECRET_ACCESS_KEY'),
            'region_name': 'auto',
            'signature_version': 's3v4',
            'default_acl': None,          # R2 no usa ACL: los archivos son privados y se sirven con URL firmada
            'querystring_auth': True,
            'querystring_expire': 3600,
            'file_overwrite': False,
        },
    }
elif ALMACENAMIENTO == 'local':
    _archivos = {'BACKEND': 'django.core.files.storage.FileSystemStorage'}
else:
    raise environ.ImproperlyConfigured(f"ALMACENAMIENTO debe ser 'local' o 'r2', no {ALMACENAMIENTO!r}")

STORAGES = {
    'default': _archivos,
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}

# ---------------------------------------------------------------- seguridad en el servidor
# Detrás de Cloudflare: el pedido llega por HTTPS aunque al servidor le llegue por HTTP.
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = env.int('SECURE_HSTS_SECONDS', default=0)   # subir cuando el dominio esté fijo
    SECURE_CONTENT_TYPE_NOSNIFF = True

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'consola': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['consola'], 'level': 'INFO'},
    'loggers': {'ezdxf': {'level': 'WARNING'}},
}
