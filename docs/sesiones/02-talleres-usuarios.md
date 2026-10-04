# 02 · Talleres, usuarios, roles y separación entre talleres

## Objetivo
Varios talleres en la misma app sin que uno pueda ver nada del otro.

## Alcance
- Modelos `taller`, `usuario`, `membresia` (rol: dueño, oficina, armador, instalador). Un usuario puede estar en
  más de un taller.
- Ingreso por mail (contraseña o link mágico; decidir y anotar). Invitar usuarios por mail.
- Armadores: ingreso con PIN corto en un celular compartido del taller, para registrar quién hizo cada cosa.
- Capa única de filtrado por taller (manager o middleware) y pruebas que intentan cruzar datos entre dos talleres
  (lectura, escritura, archivos) y deben fallar.
- Direcciones `app.<dominio>/<taller>/…` (el dominio se configura en `.env`).
- Administración: crear taller, ver miembros.

## Fuera de alcance
Planes y cobro (ficha 08). Logo del taller en el link del cliente (ficha 04).

## Listo cuando
Las pruebas de separación pasan; se puede crear un taller, invitar a un usuario y entrar con PIN.

## Para abrir la sesión
> Leé `CLAUDE.md` y `docs/sesiones/02-talleres-usuarios.md`. Empezá en modo plan. La separación entre talleres es la
> regla 1: quiero ver primero cómo la vas a garantizar y las pruebas.
