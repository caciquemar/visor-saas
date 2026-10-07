# 15 · Cotas internas: luces entre piezas y posición de taladros y herrajes

## Objetivo
Que el armador vea en el visor las medidas de adentro del mueble, además del ancho, alto y profundidad de afuera que
ya muestra el botón de cotas: cuánto mide cada hueco y dónde van los taladros y los herrajes de cada pieza.

## Alcance
- **Luces entre piezas (mueble elegido):** medida libre entre piezas paralelas que se enfrentan. Por ejemplo, entre
  estantes y entre estante y piso o techo (alto del hueco), entre laterales y divisiones (ancho del hueco) y del
  fondo al frente (profundidad útil). Se dibujan como las cotas de hoy (línea + número en mm), dentro del mueble.
  Solo se muestran con el botón de cotas prendido y un mueble elegido, para que no se llene la pantalla.
- **Taladros y herrajes (pieza elegida):** distancia de cada taladro a los dos bordes más cercanos de la pieza.
  Los taladros iguales en fila (sistema 32, minifix) se acotan una sola vez con el paso. Para bisagras y correderas,
  la distancia desde el borde de la pieza. Hay que revisar si alcanza con lo que ya trae el proyecto: `tal`
  de cada panel (centro, dirección, diámetro, profundidad, si es de canto) y `herrajes` (solo la caja y el mueble).
- **Dónde se calcula:** decidir si las luces y las posiciones se calculan en el conversor (quedan en el JSON y se
  prueban con las muestras) o en el visor con las mallas que ya tiene. Anotarlo en `docs/decisiones.md`.
- **Link del cliente:** no muestra taladros ni herrajes (son datos de taller). Las luces, preguntarle a Martín si las
  quiere en el link del cliente.

## Fuera de alcance
Editar medidas. Planos para imprimir. Cotas de piezas con ingletes o formas.

## Listo cuando
Con *cocina grondona* y *Rack florencia*: al elegir un mueble con estantes se ven las luces de cada hueco, y coinciden
con Polyboard (tomar dos o tres medidas a mano). Al elegir un lateral con sistema 32 y una puerta con bisagras, se ven
las distancias de los taladros a los bordes, y coinciden con el DXF del postprocesador de esa pieza.

## Para abrir la sesión
> Leé `CLAUDE.md` y `docs/sesiones/15-cotas-internas.md`. Empezá en modo plan. Mirá cómo dibuja hoy las cotas
> `visor/index.html` (función `cotas`) y qué trae cada panel en `tal` antes de proponer dónde calcular.
