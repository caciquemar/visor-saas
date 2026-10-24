# Ficha 19 — Procesos fijos, escanear es el registro, anotaciones y esquema en la etiqueta

Pedidos de Martín (2026-10-24) después de probar la v0.7.15 en el NAS. Hecha en la misma sesión que la 17 y la 18.

## Qué pidió

- Armado, Embalaje, Control de calidad, Carga e Instalar en obra son **procesos como los demás**, fijos (no se borran,
  sí se apagan). "Entregar en obra" sale.
- En cada proceso, indicar si se marca **por pieza o por mueble**.
- En la pantalla de escaneo: **escanear ya es el registro** (sin dar ok), **chequeo de duplicado** y opción de
  **agregar anotaciones**.
- Las etiquetas del mueble llevan un **esquema**: el mueble, o el proyecto con el mueble marcado, visto desde el frente
  del mueble.
- Arreglo: un control de calidad hecho a un mueble ya cargado no se veía en el tablero.

## Respuestas de Martín

- Orden fijo: Armado → Control → Embalaje → Carga → Instalar; los del taller van antes. Los fijos se renombran.
- Embalaje apagado: 1 bulto por mueble solo. Sin "Entregar en obra": instalar deja los bultos entregados (sin
  instalación, salir a obra entrega).
- Control de calidad sigue con Ok/Mal por punto (son sus subprocesos).
- Embalaje registra 1 bulto con − y +.
- **Sin correlatividad** por ahora: ningún proceso exige el anterior.
- Anotaciones: nota y foto en el registro, con opción de tarea.
- Esquema: lo elige el taller; de frente, considerando el frente del mueble.

## Qué se hizo

- `Etapa.tipo` (pieza / armado / control / embalaje / carga / instalacion) y `Etapa.por_mueble`; migración
  `avance 0004` (la etapa que hacía de armado pasa a ser el fijo Armado, con sus marcas; se suman los otros cuatro).
  `procesos()`, `etapas_activas()` (por pieza + Armado: cuentan para el %), `fijo(tipo)`.
- Procesos: una tabla, con "Se marca por" en los del taller y 🔒 en los fijos.
- Mi puesto: Proceso ▾ con los prendidos; por mueble = `puesto/api/armar` con `etapa`; `embalar` y `bultos` (−/+);
  `instalar` al escanear; duplicados en "ya"; `anotar` + fotos (`Anotacion`, `FotoDeAnotacion`, migración `0005`).
- Sin correlatividad: `terminar`, `salir`, `bulto_leido` (un mueble sin embalar se embala con 1 bulto) e instalar no
  piden motivo. `registrar_instalacion` entrega los bultos y cierra la carga.
- Pasos según lo prendido (`pasos_activos`); tablero con el control aparte y el último paso prendido como final.
- Esquema: `etiquetas/esquema.py` (frente del mueble por los nombres de Polyboard: Lateral Derecho/Izquierdo, Trasera,
  puertas y frentes; los cantos "frente/atrás" son de cada pieza y no sirven), `FormatoEtiquetas.esquema` (migración
  `etiquetas 0002`), `pdf._esquema`.

## Falta

- Probar con celular de verdad: cámara, fotos de anotaciones y la etiqueta impresa (que el QR, más chico con esquema,
  se lea bien).
- Un mueble con nombres de piezas que no son los de Polyboard (sin laterales, trasera ni puertas reconocibles) se dibuja
  con el frente del proyecto (+z).
