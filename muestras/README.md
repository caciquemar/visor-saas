# Muestras de Polyboard

Proyectos reales para las pruebas del conversor. Es lo más valioso del repo: cada cambio del conversor se prueba
contra todos.

Una carpeta por proyecto:

```
muestras/
  <nombre>/
    <nombre>.dxf          DXF 3D exportado de Polyboard
    <nombre>.ocp          lista de OptiCut (puede haber varios: <nombre> parte 1.ocp, ...)
    NOTAS.md              versión de Polyboard/OptiCut y qué tiene de particular
    esperado/             resultado guardado (lo genera la prueba la primera vez y se revisa a mano)
```

Cubrir al menos:
- OptiCut viejo y OptiCut nuevo.
- Mueble suelto (proyecto vacío en el .ocp).
- Piezas con ingletes (más de 6 caras).
- Proyecto dividido en varios .ocp.
- Tableros sin textura (solo color) y con textura.

**Antes de subir:** cambiar los nombres de clientes finales (por ejemplo "cocina argerich" → "cocina muestra 01")
en el nombre de archivo y dentro del proyecto de Polyboard antes de exportar.
