# Ficha 24 — Proyectos de Fusion (DXF)

Pedido de Martín (2026-11-14): algunos muebles los diseña en Autodesk Fusion y quiere subirlos al visor como los de
Polyboard. Muestra: `muestras/fusion sillon exterior/` (*sillon exterior 2m*: estructura de perfiles, parrilla de
listones y almohadones).

## Lo que trae el DXF que exporta Fusion

- Un bloque por componente, con su nombre, anidados como en el árbol de Fusion (`estructrura` → `pata`, `pata(1)`…,
  `parrilla` → `Component16` ×7). Fusion agrega `(n)` a las copias.
- Cada cuerpo como **3DSOLID** (ACIS binario, SAB), no como 3DFACE. ezdxf los pasa a malla (`ezdxf.acis`); el
  `transform` de algunos cuerpos viene en un formato más nuevo que ezdxf no lee: el conversor lo arregla.
- Centímetros, con la escala ×10 en los INSERT (queda en mm al aplicar la matriz), y **Y arriba** (Z hacia adelante).
- **Sin materiales**: todo en la capa 0, sin color ni material.
- Sin números de mecanizado (no hay lista de OptiCut), sin cantos ni taladros.

## Decisiones (Martín eligió el camino del DXF, sin complemento en Fusion)

1. Se sube **solo el DXF**: si es de Fusion (sólidos y nada de 3DFACE), no se pide el .ocp.
2. **Un mueble por archivo**, con el nombre del archivo. Si todos los componentes de primer nivel tienen
   componentes adentro, cada uno es un mueble (proyecto con varios muebles en un diseño).
3. **Pieza = cuerpo.** Nombre: el del componente sin el `(n)` de Fusion. Medidas: la caja de la pieza (los perfiles
   de Fusion van alineados a los ejes). Las piezas salen "s/n": etiquetas, avance y escáner por QR andan igual.
4. **Materiales en el visor** (pantalla del proyecto, sección Versiones, "Materiales de Fusion", quien gestiona
   proyectos): un tablero de la biblioteca para todo el mueble y, si hace falta, otro para cada grupo de piezas
   con el mismo nombre; o **No se fabrica** (almohadones, vidrios, herrajes de Fusion): se ve en el 3D y en la AR
   como herraje (caja gris) y no cuenta en etiquetas ni avance. También el eje vertical (Y, lo normal en Fusion, o
   Z). Se guarda en el proyecto (`Proyecto.fusion`) y vale para las versiones siguientes; guardar vuelve a convertir
   la versión en uso.
5. Los lados de cada pieza van del mismo material que la pieza (madera maciza: "canto igual al tablero").

## Listo cuando

- El sillón de muestra se sube solo con el DXF y se ve en el visor con sus 19 piezas + 2 almohadones.
- Elegir materiales cambia el 3D y la AR; "No se fabrica" saca las piezas de etiquetas y avance.
- Un DXF de Polyboard sigue pidiendo el .ocp y da el mismo resultado que antes (pruebas de muestras).
