# Fichas de sesión

Una sesión de Claude Code por ficha, en el grupo **Visor SaaS** de la barra lateral.
Para empezar una: nueva sesión con carpeta `C:\Users\Asus\GitHub\visor-saas` y pegar el bloque
"Para abrir la sesión" de la ficha. Al terminar, marcar la ficha como hecha acá.

| Ficha | Tema | Depende de | Semanas (plan) | Estado |
|---|---|---|---|---|
| [00](00-seguridad-visor-actual.md) | Cerrar el visor actual de Nord Good | — | más adelante | postergada (2026-10-04) |
| [01](01-esqueleto.md) | Esqueleto Django, conversor como paquete, pruebas con muestras | — | 5 | hecha (2026-10-04) |
| [02](02-talleres-usuarios.md) | Talleres, usuarios, roles, PIN, separación entre talleres | 01 | 5–6 | hecha (2026-10-05) |
| [03](03-subida-conversion.md) | Subir proyecto, cola de conversión, versiones, archivos | 02 | 6–8 | hecha (2026-10-06) |
| [04](04-visor-link-cliente.md) | Visor dentro de la app y link del cliente con la marca del taller | 03 | 8–9 | hecha (2026-10-06) |
| [05](05-trabajos.md) | Trabajos a realizar y fotos | 04 | 9–10 | hecha (2026-10-07) |
| [06](06-modulos-zicar.md) | Módulos por taller y módulo Zicar (solo Nord Good) | 03 | 10–11 | hecha (2026-10-07) |
| [07a](07a-nas-pilotos.md) | El servicio en el NAS para los pilotos: Cloudflare, R2, copias y avisos | 06 | antes de pilotos | código hecho (2026-10-07), falta instalar |
| [07b](07b-mudanza-vps.md) | Mudanza del NAS a un VPS | 07a | antes de cobrar | pendiente |
| [08](08-planes-mercadopago.md) | Planes, límites y suscripciones (pasarela a elegir) | 07b | 13–14 | postergada: elegir pasarela (2026-10-09) |
| [09](09-factura-arca.md) | Factura electrónica ARCA automática | 08 | 14 | pendiente |
| [10](10-pagina-venta-mails.md) | Página de venta, mails y marca aplicada | 08 + marca definida | 15 | pendiente |
| [11](11-pilotos.md) | Alta de pilotos y migración de Nord Good | 07a | 12+ | pendiente |
| [12](12-etiquetas-qr.md) | Etiquetas con QR por pieza y por mueble (A4 y térmica) | 04 | antes de pilotos | pendiente |
| [13](13-avance-carga.md) | Avance por etapas, fin de fabricación por mueble y control de carga | 05 + 12 | antes de pilotos | pendiente |
| [14](14-probador-colores.md) | Probador de colores en el link del cliente | 04 | antes de pilotos | pendiente |
| [15](15-cotas-internas.md) | Cotas internas: luces entre piezas, taladros y herrajes | 04 | después de pilotos | pendiente |

Orden sugerido desde acá: 06 → 12 → 13 → 14 → 07a → 11 (pilotos) → 07b → 08 → 09 → 10 → 15. Las fichas 12 a 14 se sumaron el
2026-10-06: son las tres funcionalidades nuevas que Martín eligió para tener antes de los pilotos. La 15 (cotas
internas) se sumó el 2026-10-07 y va después de los pilotos, por decisión de Martín. La 07 se partió el 2026-10-07:
los pilotos usan el NAS (07a) y antes de cobrar se pasa a un VPS (07b). Lo que en `CLAUDE.md` dice "Ficha 07" va en la 07a.

Reglas comunes (también en `CLAUDE.md`): una ficha por sesión, modo plan en las grandes, pruebas antes de cerrar,
actualizar *Estado* en `CLAUDE.md` y `docs/decisiones.md`, commit en español.
