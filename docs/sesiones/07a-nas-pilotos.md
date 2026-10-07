# 07a · El servicio en el NAS para los pilotos

**Decisión de Martín (2026-10-07):** para la etapa de pilotos (gratis) el servicio corre en el NAS de Terrero.
Antes de cobrar (ficha 08) se muda a un VPS (ficha 07b).

## El NAS
TrueNAS SCALE 25.04, **8 GB de RAM**, apps instaladas con YAML (Apps → Discover → ⋮ → Install via YAML), sin SSH,
Tailscale `100.65.184.35`. Ya corren ahí Nextcloud, n8n y el visor de Nord Good (`visor-armado`, con su túnel
`cloudflared` a `http://<IP del NAS>:8088`). Ver `C:\Users\Asus\GitHub\polyboard\armado\armado\servidor\` como ejemplo
de cómo se instaló el visor.

## Objetivo
La app corriendo en internet desde el NAS, sin tocar el visor de Nord Good, armada de forma que mudarla al VPS sea
copiar la base y cambiar el destino del túnel.

## Alcance
- **Docker Compose único** para NAS y VPS: app (Django + servidor de producción), consumidor de Huey, PostgreSQL,
  Redis. Lo que cambia entre NAS y VPS va solo en el `.env` y en las rutas de los volúmenes.
- **App nueva en TrueNAS**, separada de `visor-armado`. Datos en un dataset propio
  (por ejemplo `/mnt/pool1/Applications/visor-saas`). Cómo llega el código y cómo se actualiza (sin SSH): decidir en el
  plan; por ejemplo imagen construida en la PC o en GitHub, o carpeta sincronizada por Nextcloud como el visor actual.
- **Memoria (8 GB compartidos con TrueNAS/ZFS, Nextcloud y n8n):** límites por contenedor (`mem_limit`), una sola
  conversión a la vez, `CONVERSION_MEMORIA_MB` alrededor de 1500. Medir cuánto usa convertir *cocina grondona*
  (la muestra más grande, 41 MB) y ajustar. Meta: la app entera por debajo de unos 2,5 GB en el peor momento.
- **Cloudflare:** subdominio de prueba en el túnel (el dominio de la marca cuando exista). HTTPS obligatorio.
  Tomar la IP real de `CF-Connecting-IP`.
- **Archivos en R2**, no en el NAS: proyectos convertidos, texturas, GLB y fotos se descargan desde Cloudflare y no
  gastan la subida de internet de la casa. Configurar CORS del bucket (ver *Pendientes* en `CLAUDE.md`).
- **Velocidad de subida:** Martín no la conoce. Medirla al principio (por ejemplo speedtest.net o fast.com desde una
  PC en la misma red del NAS) y anotarla aquí. Con los archivos en R2 alcanza con poca subida.
- **Copias:** base de datos todos los días a R2 (fuera de la casa), con una restauración probada.
- **Avisos:** caída del sitio por mail (UptimeRobot o similar) y errores de la app (Sentry, plan gratis).
- **Correo saliente** para invitaciones y "me olvidé la contraseña" (`EMAIL_URL`).
- Los pendientes de "Ficha 07" en `CLAUDE.md` (Zicar con token de solo lectura, row-level security, límite de PIN con
  Redis, estáticos, Huey como servicio) se resuelven acá.
- `docs/operacion.md`: cómo actualizar la versión, restaurar una copia, qué hacer si se corta la luz, y los pasos de la
  mudanza al VPS.

## Fuera de alcance
VPS (07b). Cobro (08). Las cuentas (Cloudflare R2, UptimeRobot, Sentry, correo) las crea Martín; Claude guía.

## Listo cuando
Desde un celular con datos móviles (no el wifi de la casa): se entra, se sube y convierte *cocina grondona*, se escanea
una pieza, abre el link del cliente con realidad aumentada. La copia se restauró una vez. Apagar la app dispara el aviso.
El visor de Nord Good sigue andando igual.

## Para abrir la sesión
> Leé `CLAUDE.md` y `docs/sesiones/07a-nas-pilotos.md`, y mirá cómo está instalado el visor actual en
> `polyboard/armado/armado/servidor`. Empezá en modo plan: primero cómo llega y se actualiza el código en el NAS sin SSH.
