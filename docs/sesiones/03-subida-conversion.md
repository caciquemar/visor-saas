# 03 · Subir un proyecto y convertirlo en el servidor

## Objetivo
El taller sube el DXF 3D y uno o varios .ocp desde el navegador y en minutos tiene el proyecto en el visor.

## Alcance
- Pantalla "Nuevo proyecto / nueva versión": arrastrar archivos, control de tipo y tamaño.
- Modelos `proyecto` y `version`: cada subida es una versión y se puede volver a una anterior. Se guardan los
  originales y el resultado en `talleres/<id>/proyectos/<id>/versiones/<n>/`.
- Conversión en la cola, en un proceso aparte con límite de tiempo y memoria. Estados: en cola, convirtiendo, listo, error.
  El error muestra el mensaje del conversor en lenguaje de taller.
- Biblioteca de materiales del taller (`material`): lo que hoy es `materiales.json`. Si falta una textura, el taller
  la sube una vez.
- Lista de proyectos del taller.

## Fuera de alcance
Mostrar el visor (ficha 04). Zicar (ficha 06).

## Listo cuando
Las muestras subidas desde el navegador quedan todas en "listo"; un archivo roto queda en "error" con mensaje claro;
las pruebas de separación cubren los archivos subidos.

## Para abrir la sesión
> Leé `CLAUDE.md` y `docs/sesiones/03-subida-conversion.md`. Empezá en modo plan.
