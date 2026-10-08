# Operación del servicio

Cómo está instalado, cómo se actualiza y qué hacer cuando algo falla. Hoy corre en el NAS (pilotos, ficha 07a); antes
de cobrar se muda a un VPS (ficha 07b) con el mismo compose.

## Cómo está armado

```
celular / PC ──HTTPS──> Cloudflare ──túnel (cloudflared, ya existe en el NAS)──> NAS :8090 ──> visor-saas-web
                           │                                                                  │
                           └── texturas, GLB, fotos: se bajan directo de R2 (no del NAS)   visor-saas-cola
                                                                                            postgres · redis
```

- **App en TrueNAS:** `visor-saas`, separada de `visor-armado` (el visor de Nord Good, puerto 8088, que no se toca).
- **Programa:** imagen `ghcr.io/caciquemar/visor-saas:<versión>`, privada. La arma GitHub sola con cada etiqueta
  `v…` (`.github/workflows/imagen.yml`), después de pasar las pruebas. El NAS no tiene el código ni el token de Zicar.
- **Contenedores** (`despliegue/compose.yml`):

  | contenedor | qué hace | memoria máx. |
  |---|---|---|
  | `visor-saas-web` | la página (gunicorn, 2 procesos); migra la base al arrancar | 384 MB |
  | `visor-saas-cola` | conversiones (una a la vez), latido de `/salud/`, copia diaria | 1800 MB |
  | `visor-saas-postgres` | base de datos (PostgreSQL 17) | 384 MB |
  | `visor-saas-redis` | cola y caché | 64 MB |
  | `visor-saas-preparar` | arranca, deja lista la base y se apaga (es normal verlo "Exited") | 128 MB |

- **Datos en el NAS:** dataset `pool1/Applications/visor-saas`: `postgres/`, `redis/` y `config/` (los dos `.env`).
- **Fuera del NAS:** archivos de los talleres en R2 (`visor-saas`), copias de la base en R2 (`visor-saas-copias`),
  errores en Sentry, aviso de caída en UptimeRobot, mails por Brevo.

## Instalar desde cero (una vez)

Lo hace Martín con estas pantallas; Claude acompaña.

0. **Medir la subida de internet** desde una PC de la casa: https://fast.com → "Más información" → "Subida".
   Anotarla en `docs/sesiones/07a-nas-pilotos.md`.
1. **GitHub** (github.com/settings/personal-access-tokens):
   - Token *fine-grained* "zicar-imagen": repositorio solo `Polyboard_to_zicar`, permiso *Contents: Read-only*, vence
     en 1 año. Guardarlo en visor-saas → Settings → Secrets and variables → Actions → `ZICAR_TOKEN`.
   - Token *classic* "nas-imagenes" con solo `read:packages` (los fine-grained no sirven para el registro). Es el
     que usa el NAS para bajar la imagen.
   - Subir el código y la primera versión (desde la PC, en la carpeta del repo):
     `git push`, `git tag v0.7.0`, `git push origin v0.7.0`. En la pestaña *Actions* del repo se ve cómo corre;
     cuando termina en verde, la imagen está en *Packages*.
2. **Cloudflare R2** (dash.cloudflare.com → R2):
   - Buckets `visor-saas` y `visor-saas-copias`.
   - *Manage API tokens* → dos tokens *Object Read & Write*: uno solo para `visor-saas`, otro solo para
     `visor-saas-copias`. Anotar Access Key ID, Secret y el Account ID.
   - `visor-saas` → Settings → CORS policy:
     ```json
     [{"AllowedOrigins": ["https://taller.nordgood.com.ar"], "AllowedMethods": ["GET", "HEAD"],
       "AllowedHeaders": ["*"], "MaxAgeSeconds": 86400}]
     ```
3. **TrueNAS — carpetas:** Datasets → `Applications` → Add Dataset `visor-saas` (preset *Generic*). Adentro:
   `postgres` y `redis` (*Generic*) y `config` (preset *SMB*). Shares → SMB → Add: ruta `.../visor-saas/config`,
   nombre `visor-saas-config`, solo el usuario `martin` (Edit ACL). Desde la PC: `\\<NAS>\visor-saas-config`.
4. **Configuración:** copiar `despliegue/visor.env.ejemplo` y `despliegue/postgres.env.ejemplo` a esa carpeta como
   `visor.env` y `postgres.env`, y completar lo que dice CAMBIAR (claves de R2, mail, Sentry, claves nuevas al azar).
5. **TrueNAS — registro privado** (a confirmar en la instalación, depende de la versión de TrueNAS): Apps →
   Configuration → *Docker Registries* → `ghcr.io`, usuario `caciquemar`, clave = el token "nas-imagenes". Si esa
   pantalla no está: System → Shell y `sudo docker login ghcr.io -u caciquemar` (pide el token).
6. **TrueNAS — la app:** Apps → Discover → ⋮ → *Install via YAML*. Nombre `visor-saas`, pegar
   `despliegue/compose.yml` entero, Save. Esperar que `web` y `cola` queden *Running*.
7. **Cloudflare — túnel:** Zero Trust → Networks → Tunnels → el túnel del NAS → Public Hostname → Add:
   subdominio `taller`, dominio `nordgood.com.ar`, servicio `HTTP` → `<IP del NAS en la red de la casa>:8090`
   (la misma IP que usa el visor de Nord Good). En el dominio: SSL/TLS → Edge Certificates → *Always Use HTTPS*.
8. **Primer usuario:** Apps → visor-saas → contenedor `web` → *Shell* →
   `python app/manage.py createsuperuser`. Entrar a `https://taller.nordgood.com.ar/admin/`, crear el taller.
   Módulo Zicar para Nord Good: en la ficha del taller → Módulos.
9. **Avisos:**
   - UptimeRobot: monitor HTTP(s) `https://taller.nordgood.com.ar/salud/`, cada 5 minutos, aviso por mail.
   - Sentry: proyecto Django → copiar el DSN a `SENTRY_DSN` en `visor.env` y reiniciar la app.
   - Brevo: cuenta gratis (300 mails por día) → Senders & IP → dominio `nordgood.com.ar` → poner en Cloudflare DNS
     los registros que pide (DKIM, SPF, DMARC) → SMTP & API → la clave SMTP va en `EMAIL_URL`.

## Actualizar a una versión nueva

1. En la PC: `git tag v0.7.1` y `git push origin v0.7.1` (Claude lo hace con tu OK). GitHub corre las pruebas y, si
   pasan, arma la imagen (unos 5 minutos; se ve en *Actions*). Si las pruebas fallan, no hay imagen y el NAS sigue
   con la anterior.
2. TrueNAS: Apps → visor-saas → Edit → en la línea `image: ghcr.io/caciquemar/visor-saas:v0.7.0` cambiar el número
   → Save. Baja la imagen nueva y reinicia; `web` migra la base sola. El corte es de menos de un minuto.
3. Mirar `https://taller.nordgood.com.ar/salud/` → `ok`.

**Volver atrás:** lo mismo con el número anterior. Si la versión nueva traía migraciones de la base, la vieja puede no
andar con la base migrada: en ese caso restaurar la copia de antes de actualizar (abajo). Antes de una versión con
migraciones grandes conviene una copia a mano (`python app/manage.py copia_base` en la consola de `cola`).

## Ver qué pasa

- **Logs:** Apps → visor-saas → contenedor → *Logs*. En `cola`, cada conversión deja
  `Conversión terminada en N s; memoria pico: X MB reales, Y MB reservados`.
- **Errores:** llegan a Sentry (con mail).
- **¿Anda?** `/salud/` dice `ok`, o `falla: base`, `falla: cache`, `falla: cola` (la cola no late hace más de 10
  minutos: el contenedor `cola` está caído o trabado → reiniciar la app).
- **Memoria:** Apps → visor-saas muestra lo que usa cada contenedor.

## Memoria

El NAS tiene 8 GB compartidos con TrueNAS/ZFS, Nextcloud, n8n y el visor de Nord Good. Meta: la app entera por
debajo de 2,5 GB en el peor momento (convirtiendo el proyecto más grande).

- `CONVERSION_MEMORIA_MB` (en `visor.env`) es el tope de memoria **reservada** de cada conversión: si un proyecto lo
  pasa, la conversión se corta con "El proyecto es demasiado grande…" y el resto sigue andando.
- `mem_limit` de `cola` (en el compose) es el tope de memoria **real** del contenedor; tiene que dejar unos 200 MB
  más que la conversión.
- Medición con *cocina grondona* (41 MB, la muestra más grande): _pendiente, se anota al instalar_.

## Copias de la base

- Todos los días a las 4 de la mañana la cola hace `pg_dump` y lo sube a R2 `visor-saas-copias`: `diarias/` (quedan
  30) y la primera de cada mes también a `mensuales/` (quedan 12). Si falla, reintenta 2 veces y avisa en Sentry.
- Hacer una ahora: consola de `cola` → `python app/manage.py copia_base`.
- Ver las que hay: `python app/manage.py restaurar_copia`.
- **Probar una copia sin tocar nada** (hacerlo cada tanto):
  `python app/manage.py restaurar_copia diarias/visor-AAAA-MM-DD-HHMM.dump --base prueba_copia`
  Muestra cuántas filas tiene cada tabla en la copia y en la base de la app. Después borrar la base de prueba:
  `python app/manage.py restaurar_copia --borrar-base prueba_copia`.
- **Restaurar de verdad** (se pierde lo hecho después de esa copia; avisar a los pilotos):
  `python app/manage.py restaurar_copia diarias/visor-AAAA-MM-DD-HHMM.dump --si`
  Reemplaza todas las tablas en una sola transacción (si falla, la base queda como estaba). Después: Apps →
  visor-saas → Stop y Start.
- Los archivos (proyectos, texturas, fotos) no están en la copia: están en R2, que no se borra al restaurar.

## Si se corta la luz o internet

- Las apps de TrueNAS arrancan solas cuando vuelve el NAS (`restart: unless-stopped`); la base se recupera sola.
- Mientras tanto la página no anda y UptimeRobot avisa por mail; al volver, avisa que volvió.
- Al volver, revisar: `/salud/` → `ok`. Las conversiones que estaban corriendo quedan en "error" con el mensaje de
  siempre: "Volver a convertir". Las que estaban "en cola" siguen solas (Redis guarda la cola en disco).
- Si el corte fue largo, avisar a los pilotos. Para clientes que pagan, esto es lo que resuelve el VPS (07b).

## Mudanza al VPS (ficha 07b)

1. En el VPS: Docker, la carpeta de datos (ej. `/srv/visor-saas` con `config/`), los dos `.env` copiados del NAS
   (cambiar `SENTRY_ENTORNO=vps`), y `compose.yml` con `VISOR_DATOS=/srv/visor-saas` en un `.env` al lado.
   `docker login ghcr.io` con el token "nas-imagenes". `docker compose up -d` y ver que `/salud/` ande por la IP.
2. Avisar a los pilotos (corte de menos de una hora). En el NAS, consola de `cola`: `python app/manage.py copia_base`.
3. En el VPS: `docker compose exec cola python app/manage.py restaurar_copia diarias/<la recién hecha> --si`.
4. Cloudflare: el hostname `taller` (o el dominio de la marca) pasa a apuntar al túnel nuevo del VPS (cloudflared
   instalado en el VPS). Los archivos ya están en R2: no se copian.
5. Probar entrar, abrir un proyecto y un link de cliente. Apagar la app `visor-saas` del NAS (Stop) y, unos días
   después, borrarla. UptimeRobot sigue con la misma dirección.
