# Proyecto de claude.ai: negocio y marca

El código se trabaja en Claude Code. Todo lo demás (entrevistas, nombre, logo, textos, precios, preguntas al
contador) va en un **Proyecto de claude.ai**, para que cada conversación tenga el mismo contexto.

## Cómo armarlo (una sola vez, en claude.ai)

1. claude.ai → **Projects** → **Create project**. Nombre: `Visor SaaS · Negocio`.
2. **Set project instructions**: pegar el contenido de [instrucciones-proyecto.md](instrucciones-proyecto.md)
   (desde la línea "Sos mi socio de negocio…" hasta el final).
3. **Project knowledge** → subir todos los archivos de [conocimiento/](conocimiento/):
   - `plan.md`: el plan (copia de `docs/plan.md`).
   - `guia-entrevistas.md`: cómo hacer las entrevistas a talleres.
   - `plantilla-entrevista.md`: para cargar las notas de cada entrevista.
   - `brief-marca.md`: lo que se necesita para nombre, logo e identidad.
   - `preguntas-contador.md`: preguntas para el contador y el abogado.
   - `decisiones-negocio.md`: registro de decisiones de negocio.
4. Opcional: agregar el link del plan publicado (https://claude.ai/artifact/FjcEFqkNyJpgcm2f5R5VRw).

## Conversaciones sugeridas (una por tema)

| Conversación | Para qué | Primer mensaje |
|---|---|---|
| Entrevistas | Preparar, cargar notas y sacar conclusiones | "Tengo la entrevista con [taller] el [día]. Ayudame a prepararla." |
| Nombre y dominio | Lista larga, filtro, verificación | "Arranquemos la lista de nombres con el brief de marca." |
| Logo e identidad | Brief para diseñador, revisar propuestas | "Armame el pedido de presupuesto para un diseñador." |
| Video demo | Guion de 2 minutos | "Escribí el guion del video demo con un proyecto de cocina." |
| Página de venta | Textos, preguntas frecuentes | "Armá los textos de la página de venta." |
| Precios | Ajustar planes con lo que dicen las entrevistas | "Con las entrevistas cargadas, ¿los precios se sostienen?" |
| Contador y legal | Preparar reuniones y ordenar respuestas | "Preparame la reunión con el contador." |

## Mantenerlo al día

- Después de cada entrevista, cargar las notas con la plantilla (como archivo en Project knowledge o pegadas en la conversación de Entrevistas).
- Cuando se decide algo, pedirle a Claude la entrada para `decisiones-negocio.md`, actualizar el archivo en el
  Proyecto y en este repo.
- Si cambia el plan, actualizar `docs/plan.md` y volver a subir `conocimiento/plan.md`.
- Lo que sale de acá para el código (nombre, colores, textos) se lleva a la ficha 10 de Claude Code.
