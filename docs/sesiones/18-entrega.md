# Ficha 18 — Del armado a la instalación

Pedido de Martín (2026-10-24) con un dibujo: Armado → Imprimir etiqueta del mueble → Control de calidad (cantos,
todas las piezas, frentes, herrajes) → Embalaje → Carga → Instalado, y la carga y la instalación vistas "en lista y en
gráfica". Hecha en la misma sesión que la 17.

## Respuestas de Martín

- Armado en el taller, **por mueble** (no pieza por pieza). Las etiquetas del mueble se imprimen antes por lote o al
  terminar el armado.
- Control de calidad: la lista la arma cada taller. Un punto mal **crea una tarea y deja seguir**.
- Instalación **mueble por mueble**; la marca el instalador en la obra y la oficina corrige o completa. Si falta algo
  (bultos, tareas), **avisa y pide motivo**.
- "Lista y gráfica" = dos pantallas: una lista de muebles que se va marcando y el 3D del proyecto con los muebles en
  color según el paso.

## Qué se hizo

- Modelos `PuntoDeControl`, `Control`, `Instalacion`, `FotoDeInstalacion` (`avance/models.py`, migración
  `0003_entrega`). `avance/pasos.py`: el paso de cada mueble (sin armar, armado, control, embalado, cargado,
  entregado, instalado) con un color por paso, para todas las pantallas.
- Procesos: bloque "Control de calidad" (solo el dueño), con Cantos, Todas las piezas, Frentes y Herrajes por defecto.
- Mi puesto (`avance/entrega.py`, rutas en `avance/api.py`):
  - **Armado (mueble entero)**: la etiqueta de cualquier pieza deja el mueble armado (con la ubicación elegida;
    Deshacer saca todas) y ofrece imprimir la etiqueta del mueble sin número de bulto (`bultos=0` en
    `visor/api/etiquetas/pdf`).
  - **Control de calidad**: Ok/Mal por punto, nota y foto; cada Mal crea una tarea del mueble con la foto.
  - **Embalaje**: el "Fin de fabricación" de antes con otro nombre; muestra el último control.
  - **Instalar en obra**: bultos entregados, tareas del mueble con ✓, faltantes con motivo, nota y fotos; dueño y
    oficina deshacen.
  - En Cargar, Entregar e Instalar, botones Lista y 3D.
- **Lista de entrega** `/<taller>/proyectos/<id>/entrega/`: un mueble por tarjeta con sus pasos, barra por paso, se
  actualiza cada 15 s; dueño y oficina marcan instalado o lo deshacen.
- **3D**: Vista ▾ → "Colorear por entrega" (o `?entrega=1`), con leyenda; el bloque del mueble dice su paso.
- Proyecto: columnas Control e Instalado. Tablero: "por instalar", bloque Entrega e instalados por proyecto; en curso =
  le falta instalar algún mueble. Estado del pedido: `instalado`.

## Falta

- Probar en el NAS con celular de verdad: fotos con la cámara (control e instalación) y el escaneo en la obra.
