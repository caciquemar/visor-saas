# Visor SaaS — instrucciones para Claude

Servicio por suscripción para talleres de muebles que diseñan en Polyboard: suben el proyecto,
el taller lo arma escaneando las piezas, el cliente final lo ve en 3D y en realidad aumentada,
y los trabajos pendientes quedan registrados con fotos.

- Plan de negocio y arquitectura: https://claude.ai/artifact/FjcEFqkNyJpgcm2f5R5VRw (resumen en `docs/plan.md`)
- Nombre comercial: **todavía sin definir**. En el código usar `visor` como nombre interno; no usar "Nord Good" en el producto.
- Dueño: Martín (Nord Good, fábrica de muebles en melamina). Nord Good es el primer taller cliente y el único con el módulo Zicar.

## Cómo trabajamos

- Cada sesión de Claude Code toma **una** ficha de `docs/sesiones/` (ver el índice en `docs/sesiones/README.md`).
  Leé la ficha completa antes de empezar. En tareas grandes, empezá en modo plan y esperá aprobación.
- No hagas trabajo de otra ficha "de paso". Si aparece algo, anotalo en la sección *Pendientes* de esta página.
- Al terminar una sesión:
  1. Pruebas pasando (`docs/sesiones/README.md` dice cómo correrlas, una vez que exista la app).
  2. Actualizar *Estado* abajo y, si se tomó una decisión, agregarla a `docs/decisiones.md`.
  3. Commit con mensaje en español que diga qué cambia para el usuario.
- Idioma: todo en español rioplatense (textos de pantalla, comentarios, commits, documentación). Los nombres de
  código siguen el estilo del visor actual: en español (`proyecto`, `pieza`, `taller`, `trabajo`).

## Stack

- Python (Martín tiene 3.14 en la PC). App web en **Django** con **PostgreSQL** (SQLite solo para pruebas locales rápidas).
- Cola de tareas para las conversiones (RQ + Redis o Huey; se decide en la ficha 01).
- Archivos (proyectos convertidos, texturas, GLB, fotos, ZIP) en **Cloudflare R2** vía API S3; en local, carpeta del disco.
- Visor: `visor/index.html`, JavaScript sin framework. Se adapta lo mínimo: hoy pide `data/…` y `api/…` con rutas relativas.
- Cobro: Mercado Pago Suscripciones (preapproval) + webhooks. Factura electrónica ARCA.
- Producción: VPS en la nube detrás de Cloudflare. **No** el NAS de la casa.

## Estructura

```
conversor/        polyboard_a_app.py (copia de armado/armado @59fc33b) -> se convierte en paquete importable
visor/            index.html (copia del visor actual) -> se adapta a multi-taller
referencia/       api.py y nginx.conf actuales, solo como referencia (no se ejecutan)
muestras/         proyectos reales de Polyboard para pruebas (ver muestras/README.md)
docs/             plan, decisiones y fichas de cada sesión
negocio/claude-ai instrucciones y archivos para el Proyecto de claude.ai (negocio, marca, entrevistas)
app/              (se crea en la ficha 01) proyecto Django
```

## Reglas que no se negocian

1. **Separación entre talleres.** Toda consulta y todo archivo se filtra por el taller de la sesión, desde una sola
   capa (manager/queryset o middleware), nunca a mano en cada vista. Cada modelo con datos de un taller tiene `taller`.
   Hay pruebas que intentan leer y escribir datos de otro taller y deben fallar.
2. **Todo pide login** salvo el link del cliente (`/c/<código>`), que muestra solo la versión sin datos de taller,
   y la página de venta.
3. **Módulos por taller.** Las funciones extra se prenden por taller (`taller_modulo`). El módulo **Zicar** está
   habilitado solo para Nord Good: para los demás no se muestra nada y el servidor rechaza el pedido.
   El código de Zicar vive fuera de este repo (`C:\Users\Asus\GitHub\polyboard\Polyboard_to_zicar`).
4. **Secretos** (claves de Mercado Pago, R2, base de datos) solo en `.env`, nunca en el repo.
5. **Muestras sin datos personales:** antes de subir un proyecto a `muestras/`, cambiar nombres de clientes finales.
6. **No tocar el visor en producción de Nord Good** (`C:\Users\Asus\GitHub\polyboard\armado\armado`, NAS,
   visor.nordgood.com.ar) salvo que la ficha lo diga (solo la ficha 00).
7. Los datos de un taller nunca se borran sin aviso: suscripción vencida -> solo lectura -> 90 días -> borrado avisado.

## Relación con el visor actual

El visor de Nord Good sigue funcionando en el NAS hasta que este servicio esté probado. Si se corrige algo del
conversor acá que también afecta al visor actual, avisar a Martín para llevarlo allá (no hacerlo automáticamente).

## Estado

- 2026-10-04: estructura inicial creada. Ninguna ficha empezada. Próxima: 01 (esqueleto Django). La 00 (seguridad del visor actual) quedó postergada por decisión de Martín.

## Pendientes

- Definir nombre comercial y dominio (Proyecto de claude.ai, ver `negocio/claude-ai`).
