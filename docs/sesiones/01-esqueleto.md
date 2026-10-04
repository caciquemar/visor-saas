# 01 · Esqueleto Django, conversor como paquete y pruebas con muestras

## Objetivo
Base del proyecto que corre en la PC de Martín con un comando, con el conversor importable y probado contra
proyectos reales.

## Alcance
- `app/`: proyecto Django (versión estable compatible con Python 3.14), configuración por `.env`, `docker-compose.yml`
  para desarrollo (PostgreSQL + Redis), comando para correr todo en local documentado en `CLAUDE.md`.
- Elegir cola (RQ o Huey) y almacenamiento (django-storages con R2; carpeta local en desarrollo). Registrar la
  decisión en `docs/decisiones.md`.
- `conversor/`: convertir `polyboard_a_app.py` en paquete con una función `convertir(dxf, ocps, destino, texturas)`
  que no use `sys.exit` ni rutas de la PC de Nord Good. Los errores son excepciones con mensaje claro para el taller.
  La línea de comandos sigue funcionando.
- Pruebas (pytest) que convierten cada proyecto de `muestras/` y comparan contra un resultado guardado.
- `.env.example` y `README.md` con cómo arrancar.

## Fuera de alcance
Usuarios, talleres, pantallas.

## Listo cuando
`pytest` pasa con al menos 3 muestras (una de OptiCut viejo y una de nuevo), y la app levanta en local mostrando
la administración de Django.

## Para abrir la sesión
> Leé `CLAUDE.md` y `docs/sesiones/01-esqueleto.md`. Empezá en modo plan. Antes de tocar el conversor, revisá qué
> muestras hay en `muestras/` y pedime las que falten.
