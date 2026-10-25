# Ficha 23 — Equipo: ABM de personas y roles propios con permisos

Pedidos de Martín (2026-10-25).

## Qué pidió y eligió

- En Equipo, **ABM de personas**: un solo **"Agregar persona"** (nombre, rol y cómo entra) en vez de los cuadros
  "Invitar por mail" y "Alta con PIN". La baja es **desactivar** (no entra más; su nombre queda en lo que hizo; se
  reactiva).
- **ABM de roles propios con permisos**: crear, renombrar y borrar roles y tildar qué puede hacer cada uno. Los
  cuatro de antes quedan como iniciales.
- **"Dueño" pasa a llamarse "Administrador"** en todo lo que se ve.

## Qué se hizo

- `talleres/permisos.py`: el catálogo de permisos (Visor, Tareas, Editar y borrar tareas de otros, Ver proyectos,
  Subir y modificar proyectos, Borrar proyectos, Mi puesto, Tablero, Corregir producción, Ubicaciones, Procesos y
  puntos de control, Materiales, Equipo, Roles, Marca) y los roles iniciales con los mismos accesos de antes.
  `SENSIBLES` (Equipo, Roles, Marca, Borrar proyectos) no van en un rol que entra con PIN.
- `Rol(DatoDeTaller)`: nombre, permisos, `con_pin`, `base` (`admin`, `oficina`, `armador`, `instalador` o vacío),
  orden. `Membresia.rol` e `Invitacion.rol` son FK. Migraciones `talleres 0005–0007` (crear, pasar datos —`dueno` →
  `admin`—, cambiar a FK; en tres para PostgreSQL). Cada taller nuevo arranca con los cuatro (`post_save`).
- `talleres/roles.py`: `con_permiso(...)` reemplaza a `con_rol(...)`; `puede(request, permiso)`. Todas las vistas,
  el menú y Zicar usan permisos. Sesión con PIN: el rol tiene que tener `con_pin`.
- Equipo (`?ver=personas|roles`): tabla de personas e invitaciones con buscar, filtro (rol, estado) y orden; fila →
  ficha de la persona (rol de una lista, activo, PIN, link de entrada, huellas); invitaciones: Reenviar y Anular.
  "Agregar persona" en una ventana: con mail, invitación; sin mail (solo en roles con PIN), usuario y PIN. Roles:
  tabla, ficha del rol con las casillas por grupo, borrar solo si nadie lo tiene. El Administrador tiene todo, solo se
  renombra; solo un administrador lo da; siempre queda al menos uno activo.
- Arreglo de paso: en la ficha de la persona, el bloque "Huellas" estaba dentro del título de la página.
- Pruebas: `tests/app/test_equipo_roles.py`; `ayudas.sumar` y `rol_pk` buscan el rol por su base.

## Falta

- Al instalar en el NAS: la migración arma los roles sola; nadie cambia de acceso. Probarlo con la base de verdad
  (PostgreSQL con RLS).
