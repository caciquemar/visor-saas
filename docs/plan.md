# Plan: visor de armado por suscripción

Versión completa y actualizada: https://claude.ai/artifact/FjcEFqkNyJpgcm2f5R5VRw
Este archivo es un resumen para trabajar. Si cambia una decisión, actualizar los dos.

## Producto
Servicio mensual para talleres y fábricas de muebles en melamina que diseñan en Polyboard.
- Proyecto 3D con texturas y veta, desde el DXF 3D y el .ocp de Polyboard.
- Escanear el código de una pieza mecanizada para ver a qué mueble va y dónde.
- Ficha de pieza: medidas, cantos con espesor, taladros.
- Link para el cliente final: vista transparente y realidad aumentada a tamaño real, con la marca del taller.
- Trabajos a realizar: pendiente → en proceso → hecho → instalado, con piezas, responsable, fecha y fotos.
- Módulos por taller. El módulo Zicar (Polyboard → CNC Zicar) es interno y solo está habilitado para Nord Good.

Nuevas, antes de los pilotos (decididas el 2026-10-06):
- Etiquetas con QR por pieza (para talleres sin etiqueta de mecanizado) y por mueble (bulto 1 de N), en A4 o térmica.
- Avance por etapas (cortada, canteada, mecanizada, armada), fin de fabricación por mueble y control de carga
  escaneando cada bulto antes de salir a obra.
- Probador de colores en el link del cliente: cambia tableros entre opciones del taller, en 3D y en realidad aumentada.

Para después de las entrevistas: piezas a rehacer (lista para OptiCut), uso sin señal en obra, resumen de materiales,
aprobación del cliente, estado del pedido en el link, tablero de producción, avisos, integraciones (API, Dolibarr),
instrucciones de armado para muebles en kit.

Diferenciales pendientes para el plan Pro: orden de armado paso a paso, herrajes en la ficha,
cotas y veta sobre la pieza, buscar por nombre de pieza (tildar piezas armadas queda dentro de la ficha 13).

## Cliente ideal
Taller de 3 a 30 personas que diseña en Polyboard, corta y mecaniza (propio o tercerizado), arma en taller y en obra.
Decide el dueño, que ya paga software. Primero Argentina, después Latinoamérica.
Dato pendiente: cuántos talleres usan Polyboard en la región (preguntar al distribuidor local).

## Marca
Marca propia, separada de Nord Good (los clientes son otros fabricantes). Nord Good aparece como caso real.
- Marca del servicio: página de venta, panel, mails, facturas, redes.
- Marca de cada taller: logo y colores en el link del cliente (dominio propio en el plan Fábrica), con un pie chico "hecho con [marca]".
- Ideas de nombre sin verificar: Pieza a Pieza, Armalo, Despiece, Ensamblá, Mueble Vivo.

## Planes (precio de lista en USD, cobrado en ARS)
| Plan | USD/mes | Incluye |
|---|---|---|
| Taller | 19 | 10 proyectos activos, 3 usuarios, visor, escaneo, ficha, link del cliente, etiquetas con QR |
| Pro | 39 | Ilimitados, trabajos con fotos, avance por etapas y control de carga, realidad aumentada, probador de colores, logo del taller en el link |
| Fábrica | 79 | Todo Pro, colores y dominio propio en el link, varias sucursales, reportes, soporte prioritario |

Prueba de 30 días con Pro sin tarjeta. Anual con 2 meses de regalo. Puesta en marcha opcional USD 100.
Pilotos: 3 a 5 talleres gratis 3 meses, después 50 % de descuento de por vida.

## Cobro y papeles
- Mercado Pago Suscripciones en Argentina. Exterior más adelante con Paddle o Lemon Squeezy (Stripe no opera con empresas argentinas).
- Factura electrónica ARCA automática por cobro.
- A definir con el contador: régimen, si se separa de la fábrica. Términos, privacidad (Ley 25.326), marca en el INPI.
- Revisar la licencia de Polyboard sobre leer el formato .ocp; evaluar hablar con Boole & Partners.

## Números
Costo fijo aproximado USD 15–50/mes más comisión de Mercado Pago. Con promedio USD 35 por taller:
10 talleres = USD 350/mes, 30 = USD 1.050/mes, 80 = USD 2.800/mes.

## Riesgos
Cambio de formato del .ocp; pocos talleres con Polyboard; soporte que consume tiempo de la fábrica; desconfianza por ser
otro fabricante; caídas del servicio.

## Hoja de ruta
1. Esta semana: cerrar el visor actual con Cloudflare Access.
2. Semanas 1–4: validar con 10 talleres, 3 pilotos; definir marca, logo y dominio; video demo.
3. Semanas 5–12: versión multi-taller (fichas 01–06), servicio en el NAS para pilotos (07a), etiquetas, avance y carga, probador de colores (fichas 12–14), pilotos (ficha 11).
4. Semanas 13–15: mudanza a un VPS (07b), cobro, factura, página de venta (fichas 08–10).
5. Semana 16 en adelante: lanzamiento y diferenciales.
