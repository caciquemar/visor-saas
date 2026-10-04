# 00 · Cerrar el visor actual de Nord Good

**Carpeta de trabajo:** `C:\Users\Asus\GitHub\polyboard\armado\armado` (no este repo).

## Objetivo
Que visor.nordgood.com.ar deje de mostrar los proyectos y de aceptar escrituras a cualquiera, sin romper los
links de clientes.

## Alcance
- Guiar a Martín paso a paso en Cloudflare Zero Trust → Access → Applications (Martín hace los cambios en el panel):
  - "Visor taller": `visor.nordgood.com.ar` completo, incluidos `/api/` y `/data/` → Allow a los mails del taller (código por mail).
  - "Visor clientes": `/data/clientes/`, `/data/texturas/`, `/data/materiales.json` y lo que el modo cliente (`?c=`)
    necesite → Bypass, Everyone. Revisar en `index.html` qué pide el modo cliente antes de definir las rutas.
- Verificar con curl desde afuera: `data/index.json` pide login, `data/.clientes.json` da 404, un link `?c=` real
  anda sin login, `POST /api/trabajos` sin login no pasa.

## Fuera de alcance
Cambios de funciones del visor.

## Listo cuando
Las cuatro verificaciones dan lo esperado y Martín probó desde el celular del taller con su mail.

## Para abrir la sesión
> Trabajamos en `armado/armado`. Leé `C:\Users\Asus\GitHub\visor-saas\docs\sesiones\00-seguridad-visor-actual.md`
> y guiame para cerrar el visor con Cloudflare Access. Primero revisá qué archivos pide el modo cliente.
