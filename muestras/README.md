# Muestras de Polyboard

Proyectos reales para las pruebas del conversor. Es lo más valioso del repo: cada cambio del conversor se prueba
contra todos.

Una carpeta por proyecto:

```
muestras/
  <nombre>/
    <nombre>.dxf          DXF 3D exportado de Polyboard
    <nombre>.ocp          lista de OptiCut (puede haber varios: <nombre> parte 1.ocp, ...)
    NOTAS.md              versión de OptiCut y qué tiene de particular
    esperado/             resultado guardado: resumen.json (para leer) + proyecto.json.gz y cliente.json.gz
```

Para sumar una muestra: crear la carpeta con el .dxf y el/los .ocp, correr
`pytest -m muestras --actualizar-esperados -k "<nombre>"`, revisar `esperado/resumen.json` (piezas, paneles,
vinculados, avisos) y escribir `NOTAS.md`.

| Muestra | OptiCut | Piezas .ocp | Paneles 3D | Con ingletes | Avisos |
|---|---|---|---|---|---|
| cocina argerich | viejo | 135 | 189 | 23 | 1 |
| cocina grondona | viejo | 119 | 359 | 59 | 8 |
| cocina Juan v2 | viejo | 134 | 151 | 26 | 2 |
| Aguilar cocina | nuevo | 163 | 191 | 22 | 1 |
| Kogan | nuevo | 91 | 100 | 18 | 1 |
| Rack florencia | nuevo | 68 | 70 | 14 | 11 |
| rack tv terrero | nuevo | 69 | 110 | 0 | 3 |

Cubrir al menos:
- [x] OptiCut viejo y OptiCut nuevo.
- [ ] Mueble suelto (proyecto vacío en el .ocp).
- [x] Piezas con ingletes (más de 6 caras).
- [ ] Proyecto dividido en varios .ocp.
- [x] Tableros con textura (las pruebas no usan la carpeta Textures; se prueban aparte con imágenes generadas).

**Nombres de clientes:** el repo es privado y las muestras van con sus nombres reales (decisión del 2026-10-04,
ver `docs/decisiones.md`). Si el repo se comparte o se hace público, antes hay que re-exportarlas desde Polyboard
con otro nombre de proyecto (por ejemplo "cocina muestra 01") y regenerar `esperado/`.
