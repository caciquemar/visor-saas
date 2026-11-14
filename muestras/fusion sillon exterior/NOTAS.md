# fusion sillon exterior

Proyecto de **Autodesk Fusion** (ficha 24), exportado por Martín como DXF (2026-11-14). Sin lista de OptiCut.

- *sillon exterior 2m* (diseño v31): estructura de perfiles de 60×30 (respaldo, 4 patas, 4 vigas), parrilla de 7
  listones de 40×10 (`Component16`), un listón de la parrilla del respaldo y 2 almohadones.
- Cada cuerpo es un 3DSOLID; uno de los almohadones trae el `transform` en el formato nuevo que ezdxf 1.4 no lee
  (lo arregla `conversor/fusion.py`).
- Centímetros con escala ×10 en los INSERT, Y arriba. Sin materiales: el resultado guardado no tiene ninguno.
