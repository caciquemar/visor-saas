# 08 · Planes, límites y suscripciones de Mercado Pago

## Objetivo
Que un taller pueda pagar solo y que la app respete lo que paga.

## Alcance
- Planes Taller, Pro y Fábrica (precios en `docs/plan.md`, en USD; se cobra en ARS al tipo de cambio que se defina)
  con sus límites: proyectos activos, usuarios, trabajos con fotos, realidad aumentada, marca en el link.
- Estados: prueba (30 días) → activa → pago rechazado (7 días de gracia) → solo lectura → suspendida (90 días) → borrado avisado.
- Mercado Pago Suscripciones: alta desde el panel del taller, webhooks verificados y una revisión diaria que corrige
  avisos perdidos. Modo prueba de Mercado Pago con credenciales de prueba en `.env`.
- Pantalla "Mi suscripción": plan, próximo cobro, cambiar de plan, cancelar.

## Listo cuando
En modo prueba funcionan alta, cobro, rechazo, gracia, solo lectura y reactivación, con pruebas automáticas de cada cambio de estado.

## Para abrir la sesión
> Leé `CLAUDE.md` y `docs/sesiones/08-planes-mercadopago.md`. Revisá la documentación vigente de Mercado Pago
> Suscripciones antes de proponer el plan.
