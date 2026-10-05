# Visor SaaS

Visor de armado de proyectos de Polyboard, por suscripción, para talleres de muebles.
Nombre comercial a definir.

- Instrucciones para Claude Code: [CLAUDE.md](CLAUDE.md)
- Plan: [docs/plan.md](docs/plan.md) · Decisiones: [docs/decisiones.md](docs/decisiones.md)
- Fichas de trabajo: [docs/sesiones/](docs/sesiones/README.md)
- Negocio y marca (Proyecto de claude.ai): [negocio/claude-ai/](negocio/claude-ai/LEEME.md)

## Cómo arrancar en la PC

Hace falta Python 3.12 o más nuevo (en la PC de Martín: 3.14). En PowerShell, desde la carpeta del repo:

```powershell
.\iniciar.ps1
```

La primera vez crea el entorno `.venv`, instala las dependencias, copia `.env.example` a `.env`, prepara la base y
levanta el servidor. Las veces siguientes, solo lo levanta. La app queda en http://127.0.0.1:8000/ y la administración
en http://127.0.0.1:8000/admin/.

Para crear el usuario de la administración (una sola vez; pide mail, nombre y contraseña):

```powershell
.venv\Scripts\python app\manage.py createsuperuser
```

Para probar un taller: en la administración, *Talleres → Añadir* con el mail del dueño. En la PC los mails no se
mandan: quedan como archivos en `datos/mails/`, y de ahí se copia el link de la invitación. Los armadores entran con
PIN en http://127.0.0.1:8000/<taller>/pin/.

Por defecto usa SQLite y la cola de tareas corre en el mismo proceso, así que no hace falta Docker. Para trabajar
con PostgreSQL y Redis como en el servidor: instalar Docker Desktop, correr `docker compose up -d` y descomentar
`DATABASE_URL` y `REDIS_URL` en el `.env`. Con `HUEY_INMEDIATO=0`, el consumidor de la cola se levanta en otra
consola con `.venv\Scripts\python app\manage.py run_huey`.

## Pruebas

```powershell
.venv\Scripts\python -m pytest                    # todo (las muestras tardan unos 8 minutos)
.venv\Scripts\python -m pytest -m "not muestras"  # solo las rápidas
```

Las pruebas de `muestras/` convierten cada proyecto real y lo comparan con lo guardado en `muestras/<nombre>/esperado/`.
Si un cambio del conversor modifica el resultado a propósito, se regenera con
`pytest -m muestras --actualizar-esperados`, y antes del commit se revisan con `git diff` los `resumen.json` que cambiaron.

## Conversor

Desde Python:

```python
from conversor import convertir, ErrorConversion

r = convertir('cocina.dxf', ['cocina.ocp'], 'salida/', texturas=[r'C:\...\PolyBoard\Textures'])
r.proyecto, r.codigo, r.avisos, r.resumen
```

Si el proyecto no se puede convertir, lanza `ErrorConversion` con un mensaje para el taller.

Desde la consola, como en el visor actual:

```powershell
.venv\Scripts\python conversor\polyboard_a_app.py cocina.dxf cocina.ocp -o data
.venv\Scripts\python -m conversor cocina.dxf "cocina parte 1.ocp" "cocina parte 2.ocp" -o data --texturas "C:\...\Textures"
```
