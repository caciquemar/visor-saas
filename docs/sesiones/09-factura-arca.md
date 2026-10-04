# 09 · Factura electrónica ARCA automática

## Objetivo
Cada cobro aprobado genera su factura y le llega al taller por mail.

## Alcance
- Reutilizar lo que sirva de `C:\Users\Asus\GitHub\dolibarr-arcafacturacion`.
- Tipo de comprobante y punto de venta según lo que defina el contador
  (ver `negocio/claude-ai/conocimiento/preguntas-contador.md`).
- Datos fiscales del taller en su panel (CUIT, condición frente al IVA).
- Reintentos si ARCA no responde; cada factura queda registrada junto al pago.
- Homologación (entorno de prueba de ARCA) antes de producción.

## Listo cuando
En homologación, un cobro de prueba de Mercado Pago genera una factura válida con su PDF.

## Para abrir la sesión
> Leé `CLAUDE.md` y `docs/sesiones/09-factura-arca.md`, y revisá `dolibarr-arcafacturacion`. Empezá en modo plan.
