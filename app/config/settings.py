"""Configuración del visor. Todo lo que cambia entre la PC y el servidor viene del .env de la raíz
del repo (ver .env.example). Los secretos solo van ahí, nunca en el código."""
import sys
from pathlib import Path

import environ

RAIZ = Path(__file__).resolve().parents[2]          # raíz del repo
BASE_DIR = RAIZ / 'app'
DATOS = RAIZ / 'datos'                              # base local, cola y archivos en desarrollo (no va a git)
DATOS.mkdir(exist_ok=True)
if str(RAIZ) not in sys.path:                       # el paquete conversor/ está en la raíz, fuera de app/
    sys.path.append(str(RAIZ))

env = environ.Env()
environ.Env.read_env(RAIZ / '.env')

DEBUG = env.bool('DEBUG', default=False)
SECRET_KEY = env('SECRET_KEY', default='') or ('solo-para-desarrollo-no-usar-en-produccion' if DEBUG else '')
if not SECRET_KEY:
    raise environ.ImproperlyConfigured('Falta SECRET_KEY en el .env (obligatoria con DEBUG=0)')

# Dirección de la app (app.<dominio>): los talleres quedan en app.<dominio>/<taller>/. Se usa para los links de
# los mails y, si no se dice otra cosa, para ALLOWED_HOSTS y CSRF_TRUSTED_ORIGINS.
DOMINIO_APP = env('DOMINIO_APP', default='127.0.0.1:8000' if DEBUG else '')
if not DOMINIO_APP:
    raise environ.ImproperlyConfigured('Falta DOMINIO_APP en el .env (obligatorio con DEBUG=0), ej. app.ejemplo.com')
URL_APP = f"{'http' if DEBUG else 'https'}://{DOMINIO_APP}"
_host_app = DOMINIO_APP.split(':')[0]
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['localhost', '127.0.0.1', _host_app] if DEBUG else [_host_app])
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[] if DEBUG else [URL_APP])

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'huey.contrib.djhuey',
    'usuarios',
    'talleres',
    'proyectos',
    'trabajos',
    'modulos',
    'modulos.zicar',
    'servicio',
]

AUTH_USER_MODEL = 'usuarios.Usuario'
LOGIN_URL = 'entrar'
LOGIN_REDIRECT_URL = 'inicio'
LOGOUT_REDIRECT_URL = 'entrar'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',    # estáticos (íconos del visor, administración) sin nginx
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'talleres.middleware.TallerMiddleware',          # separación entre talleres: ver talleres/separacion.py
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
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
# En PostgreSQL hay además row-level security entre talleres: ver talleres/rls.py.
DATABASES = {'default': env.db('DATABASE_URL', default=f"sqlite:///{(DATOS / 'dev.sqlite3').as_posix()}")}
DATABASES['default']['CONN_MAX_AGE'] = env.int('CONN_MAX_AGE', default=0 if DEBUG else 60)
DATABASES['default']['CONN_HEALTH_CHECKS'] = True
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

# Caché compartida entre los procesos (intentos de PIN por IP, latido de la cola): Redis en el servidor; en la PC y
# en las pruebas, memoria del proceso.
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.redis.RedisCache', 'LOCATION': _redis,
                      'KEY_PREFIX': 'visor'} if _redis else
          {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}

# ---------------------------------------------------------------- conversión de proyectos
# Ver proyectos/tareas.py. Cada conversión corre en un proceso aparte con estos límites.
CONVERSION_SEGUNDOS = env.int('CONVERSION_SEGUNDOS', default=600)
CONVERSION_MEMORIA_MB = env.int('CONVERSION_MEMORIA_MB', default=2048)   # solo en Linux (en Windows no se limita)
# El plan gratis de Cloudflare corta los pedidos de más de 100 MB: el DXF tiene que quedar por debajo.
MAX_DXF_MB = env.int('MAX_DXF_MB', default=95)
MAX_OCP_MB = env.int('MAX_OCP_MB', default=10)
MAX_TEXTURA_MB = env.int('MAX_TEXTURA_MB', default=15)
MAX_ZICAR_MB = env.int('MAX_ZICAR_MB', default=50)       # carpeta del postprocesador (módulo Zicar)
DATA_UPLOAD_MAX_NUMBER_FILES = 30

# ---------------------------------------------------------------- marca del servicio
# Pie del link del cliente ("hecho con …") hasta tener nombre comercial; MARCA_URL: la página de venta.
MARCA_SERVICIO = env('MARCA_SERVICIO', default='Visor')
MARCA_URL = env('MARCA_URL', default='')

# ---------------------------------------------------------------- archivos
# ALMACENAMIENTO=local: carpeta datos/archivos/ (desarrollo). r2: Cloudflare R2 por la API de S3.
ALMACENAMIENTO = env('ALMACENAMIENTO', default='local')
STATIC_URL = 'static/'
STATIC_ROOT = DATOS / 'static'                      # en el servidor lo llena collectstatic al armar la imagen
STATIC_ROOT.mkdir(exist_ok=True)
WHITENOISE_USE_FINDERS = DEBUG                      # en la PC sirve los estáticos sin collectstatic
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
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage' if not DEBUG else
                    'django.contrib.staticfiles.storage.StaticFilesStorage'},
}

# Copias diarias de la base (servicio/copias.py). Con r2 van a un bucket aparte, con su propia clave (si se pierde la
# de los archivos, las copias siguen a salvo); sin clave propia usan la de los archivos. En local: datos/copias/.
if ALMACENAMIENTO == 'r2':
    COPIAS = {'BACKEND': 'storages.backends.s3.S3Storage', 'OPTIONS': {
        **_archivos['OPTIONS'],
        'bucket_name': env('R2_COPIAS_BUCKET'),
        'access_key': env('R2_COPIAS_ACCESS_KEY_ID', default=env('R2_ACCESS_KEY_ID')),
        'secret_key': env('R2_COPIAS_SECRET_ACCESS_KEY', default=env('R2_SECRET_ACCESS_KEY')),
    }}
else:
    COPIAS = {'BACKEND': 'django.core.files.storage.FileSystemStorage', 'OPTIONS': {'location': DATOS / 'copias'}}
STORAGES['copias'] = COPIAS
COPIAS_DIARIAS = env.int('COPIAS_DIARIAS', default=30)
COPIAS_MENSUALES = env.int('COPIAS_MENSUALES', default=12)

# ---------------------------------------------------------------- mails
# EMAIL_URL=smtp+tls://usuario:clave@servidor:587 (se define en la ficha 07/10). Sin EMAIL_URL, los mails se
# guardan como archivos en datos/mails/ para poder abrir los links de invitación en la PC.
if env('EMAIL_URL', default=''):
    globals().update(env.email_url('EMAIL_URL'))
else:
    EMAIL_BACKEND = 'django.core.mail.backends.filebased.EmailBackend'
    EMAIL_FILE_PATH = DATOS / 'mails'
DEFAULT_FROM_EMAIL = env('MAIL_REMITENTE', default='Visor <no-responder@localhost>')

# ---------------------------------------------------------------- seguridad en el servidor
# Detrás de Cloudflare: el pedido llega por HTTPS aunque al servidor le llegue por HTTP.
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = env.int('SECURE_HSTS_SECONDS', default=0)   # subir cuando el dominio esté fijo
    SECURE_CONTENT_TYPE_NOSNIFF = True

# Detrás del túnel de Cloudflare la IP de quien entra viene en CF-Connecting-IP (ver talleres/vistas.py, ip_de).
# Solo con 1: sin Cloudflare adelante, cualquiera podría inventar ese encabezado.
DETRAS_DE_CLOUDFLARE = env.bool('DETRAS_DE_CLOUDFLARE', default=False)

# Errores de la app y de la cola a Sentry (plan gratis). Sin SENTRY_DSN no se manda nada.
SENTRY_DSN = env('SENTRY_DSN', default='')
if SENTRY_DSN:
    import sentry_sdk
    sentry_sdk.init(dsn=SENTRY_DSN, environment=env('SENTRY_ENTORNO', default='nas'),
                    release=env('VISOR_VERSION', default=None), send_default_pii=False, traces_sample_rate=0)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'consola': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['consola'], 'level': 'INFO'},
    'loggers': {'ezdxf': {'level': 'WARNING'}},
}
