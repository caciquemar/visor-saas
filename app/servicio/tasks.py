"""Huey busca un `tasks.py` en cada app al arrancar el consumidor (`run_huey`). Las tareas del visor están en
`tareas.py` de cada app: se importan acá para que el consumidor las conozca todas sin depender de otra cosa."""
import modulos.zicar.tareas  # noqa: F401
import proyectos.tareas  # noqa: F401
import servicio.tareas  # noqa: F401
