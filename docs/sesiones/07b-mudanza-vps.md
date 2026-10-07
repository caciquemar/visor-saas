# 07b · Mudanza del NAS a un VPS

**Requiere:** 07a. Hacerla antes de cobrar (ficha 08).

## Objetivo
El servicio en un servidor en la nube, sin depender de la luz ni del internet de la casa.

## Alcance
- Elegir VPS (2–4 GB) y proponer proveedor y costo mensual.
- Instalar el mismo Docker Compose de la 07a con el `.env` del VPS.
- Mudanza: avisar a los pilotos, copiar la base (los archivos ya están en R2), cambiar el destino del túnel o el DNS
  de Cloudflare, probar y apagar la app del NAS. Corte de menos de una hora.
- Revisar límites de memoria y de tamaño de DXF para el VPS.
- Actualizar `docs/operacion.md`.

## Fuera de alcance
Cambios de funciones. La cuenta del VPS (con tarjeta) la crea Martín.

## Listo cuando
Los pilotos siguen entrando con la misma dirección, sus datos están todos, y el NAS ya no atiende el servicio.

## Para abrir la sesión
> Leé `CLAUDE.md`, `docs/sesiones/07b-mudanza-vps.md` y `docs/operacion.md`. Proponé proveedor y costo antes de empezar.
