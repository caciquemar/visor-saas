# 07 · Servidor en la nube, Cloudflare, copias y monitoreo

## Objetivo
La app corriendo en internet de forma confiable, lista para pilotos.

## Alcance
- Elegir VPS (2–4 GB) y armar el despliegue con Docker Compose: app, worker de la cola, PostgreSQL, Redis, proxy.
- Cloudflare delante (dominio de la marca; mientras tanto un subdominio de prueba). HTTPS obligatorio.
- R2 para archivos. Variables en el `.env` del servidor.
- Copia diaria de la base a R2, con una restauración probada y documentada.
- Aviso de caída (UptimeRobot o similar) y registro de errores (Sentry, plan gratis).
- `docs/operacion.md`: cómo desplegar una versión nueva, cómo restaurar, a quién avisa cada alerta.

## Fuera de alcance
Cobro. Las cuentas (VPS, Cloudflare, Sentry) las crea Martín; Claude guía y configura el código.

## Listo cuando
Se despliega con un comando, la restauración está probada y la alerta de caída llega al mail de Martín.

## Para abrir la sesión
> Leé `CLAUDE.md` y `docs/sesiones/07-produccion.md`. Proponé proveedor y costo mensual antes de empezar.
