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

## Decisiones previas (2026-10-09, sesión que se postergó)
Martín postergó la ficha: como se van a recibir pagos del exterior, prefiere evaluar **Payway u otra pasarela con
cuenta en EE. UU.** en vez de Mercado Pago. Antes de proponer el plan hay que comparar pasarelas (cobro recurrente,
tarjetas del exterior y de Argentina, cuenta o empresa en EE. UU., factura ARCA) y que Martín elija; el título y el
alcance de esta ficha cambian según lo que elija.

Ya decidido, vale para cualquier pasarela:
- Precio en USD pasado a pesos con el **dólar oficial, leído automáticamente** todos los días (solo para lo que se
  cobre en ARS).
- Si termina la prueba de 30 días sin suscripción: **solo lectura** (igual que un pago vencido) y a los 90 días,
  suspendida.
- Entra el **plan anual** (12 meses al precio de 10). El 50 % de por vida para pilotos queda fuera de esta ficha.

Lo que se averiguó de Mercado Pago (por si se usa para Argentina): suscripción sin plan (`POST /preapproval`,
`status: pending`, el taller paga en el `init_point`), cambio de plan y baja con `PUT /preapproval/{id}`, webhooks
`subscription_preapproval` y `subscription_authorized_payment` con firma `x-signature` (HMAC-SHA256, una clave para
prueba y otra para producción, responder 200 en menos de 22 s), reintentos de cobro hasta 4 en 10 días y baja
automática con 3 cobros seguidos rechazados, revisión con `/preapproval/search`.

## Decisiones (2026-11-05): Payway Argentina, pago por período
Payway Argentina no tiene API de suscripciones ni permite cobrar una tarjeta guardada sin el código de seguridad
(guardar el código está prohibido por PCI DSS). Martín eligió **pago por período, sin cobro automático**:
- Mensual, **semestral (6 meses al precio de 5½)** o **anual (12 al precio de 10)**, en **un solo pago** (sin cuotas).
- Cobro con **Payway Link Checkout** (página de Payway; la app no ve la tarjeta). El aviso de Payway no se cree:
  se consulta el pago en Payway. El cobro va detrás de una "pasarela" intercambiable (Payway y una simulada para
  pruebas), para sumar después una del exterior.
- Precio en ARS = USD × dólar oficial leído cada día (BCRA), fijo al generar el link; cotización a mano en la
  administración si hace falta.
- Estados: prueba (30 días, Pro) → activa (pagado hasta) → vencida (7 días de gracia) → solo lectura → suspendida
  (90 días) → borrado avisado (aviso 30 y 7 días antes; el borrado lo confirma Martín en la administración).
- Subir de plan: paga la diferencia proporcional y cambia al instante. Bajar: desde el próximo pago. Sin devoluciones.
- **Los usuarios con PIN cuentan** como usuarios del plan. Los límites de cada plan (proyectos activos, usuarios,
  funciones) y los precios se **cambian desde la administración**, no en el código.
- Pilotos: "sin cobro hasta" por taller en la administración. El 50 % de por vida queda fuera de esta ficha.
- Esta ficha se hace en modo prueba (sandbox de Payway) antes de la 07b; cobrar de verdad, después del VPS.

## Hecho (2026-11-05, modo prueba)
Ver *Estado* en `CLAUDE.md`. Falta lo de *Pendientes* de `CLAUDE.md`: probar Payway Sandbox con las claves de prueba
y la respuesta de soporte, y decidir el sitio de Payway y cuándo prender `SUSCRIPCIONES_ACTIVAS`.
