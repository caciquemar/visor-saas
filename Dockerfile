# Imagen del visor para el servidor (NAS o VPS). La arma GitHub Actions (.github/workflows/imagen.yml) y queda en
# ghcr.io/caciquemar/visor-saas:<versión>. Ver docs/operacion.md.
#
# Para armarla a mano (con Docker y el token de Zicar en un archivo):
#   docker build --secret id=zicar,src=token.txt -t visor-saas:prueba .
# Sin el secreto se arma igual, sin el módulo Zicar.

FROM python:3.13-slim-trixie

# postgresql-client: pg_dump / pg_restore de las copias (mismo 17 que la base). git: instalar Zicar desde GitHub.
RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client git \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# Dependencias primero (cambian poco: Docker reusa esta capa entre versiones)
COPY pyproject.toml requirements-zicar.txt ./
RUN pip install '.[servidor]'
# Zicar (solo Nord Good) desde su repo privado. El token llega como secreto: no queda en ninguna capa.
RUN --mount=type=secret,id=zicar \
    if [ -s /run/secrets/zicar ]; then \
      git config --global url."https://x-access-token:$(cat /run/secrets/zicar)@github.com/".insteadOf "https://github.com/" \
      && pip install -r requirements-zicar.txt \
      && rm ~/.gitconfig; \
    else echo 'Sin token de Zicar: la imagen queda sin el módulo Zicar'; fi

COPY conversor/ conversor/
COPY visor/ visor/
COPY app/ app/
COPY docker/ docker/

ARG VERSION=desarrollo
ENV VISOR_VERSION=$VERSION DJANGO_SETTINGS_MODULE=config.settings

# Estáticos dentro de la imagen (los sirve whitenoise). Para collectstatic alcanza una configuración de mentira.
RUN DEBUG=0 SECRET_KEY=solo-para-armar DOMINIO_APP=armando.local python app/manage.py collectstatic --noinput \
 && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin visor \
 && mkdir -p /app/datos && chown -R visor /app/datos \
 && chmod +x docker/entrada.sh

USER visor
EXPOSE 8000
ENTRYPOINT ["/app/docker/entrada.sh"]
CMD ["web"]
