#!/bin/sh
# Arranque del contenedor. Uno solo para los dos servicios del compose:
#   preparar  crea el usuario y la base de la app en PostgreSQL si no existen (docker/preparar_base.py)
#   web   migra la base y levanta gunicorn en el puerto 8000
#   cola  espera a que la base esté migrada y levanta el consumidor de Huey (conversiones, latido, copias)
# Cualquier otra cosa se corre tal cual (ej. "python app/manage.py createsuperuser" desde la consola de TrueNAS).
set -e
cd /app

esperar_base() {
  until python app/manage.py migrate --check >/dev/null 2>&1; do
    echo "Esperando la base de datos..."
    sleep 3
  done
}

case "$1" in
  preparar)
    exec python docker/preparar_base.py
    ;;
  web)
    until python app/manage.py migrate --noinput; do
      echo "La base todavía no responde; reintento en 3 segundos"
      sleep 3
    done
    exec gunicorn config.wsgi:application --chdir app \
      --bind 0.0.0.0:8000 \
      --workers "${GUNICORN_WORKERS:-2}" --threads "${GUNICORN_HILOS:-4}" --worker-class gthread \
      --timeout "${GUNICORN_TIMEOUT:-300}" --max-requests 1000 --max-requests-jitter 100 \
      --access-logfile - --forwarded-allow-ips '*'
    ;;
  cola)
    esperar_base
    exec python app/manage.py run_huey
    ;;
  *)
    exec "$@"
    ;;
esac
