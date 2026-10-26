"""Íconos de las secciones y pantallas (Inicio, pantalla de cada sección, menú ☰ de las páginas y del visor): el
interior de un SVG de 24×24 de trazo, para que el menú del visor (que se arma en JavaScript) use los mismos."""
from django.utils.html import format_html
from django.utils.safestring import mark_safe

ICONOS = {
    'inicio': '<path d="M4 11 12 4l8 7"/><path d="M6 10v9h12v-9"/><path d="M10 19v-5h4v5"/>',
    'armado': '<path d="M12 3 4 7.5v9L12 21l8-4.5v-9L12 3Z"/><path d="M4 7.5 12 12l8-4.5M12 12v9"/>',
    'proyectos': '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z"/><path d="M3 10h18"/>',
    'produccion': '<path d="M4 7V5h3M17 5h3v2M20 17v2h-3M7 19H4v-2"/><path d="M8 9v6M11 9v6M14 9v6M17 9v6"/>',
    'configuracion': '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/>'
                     '<circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
    # pantallas
    'visor': '<path d="M12 3 4 7.5v9L12 21l8-4.5v-9L12 3Z"/><path d="M4 7.5 12 12l8-4.5M12 12v9"/>',
    'tareas': '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V3h6v1"/><path d="m8.5 11 1.5 1.5 3-3M8.5 17h7"/>',
    'puesto': '<path d="M4 7V5h3M17 5h3v2M20 17v2h-3M7 19H4v-2"/><path d="M8 9v6M11 9v6M14 9v6M17 9v6"/>',
    'tablero': '<path d="M4 20h16"/><path d="M7 16v-5M12 16V7M17 16v-8"/>',
    'procesos': '<circle cx="6" cy="6" r="2"/><circle cx="6" cy="18" r="2"/><path d="M6 8v8M10 6h10M10 18h10M14 12h6"/>'
                '<path d="M6 12h4"/>',
    'materiales': '<rect x="4" y="4" width="10" height="10" rx="1"/><path d="M10 14v6h10V10h-6"/>',
    # pestañas de Materiales: una placa con veta y un rollo de canto
    'tableros': '<rect x="3" y="6" width="18" height="12" rx="1"/><path d="M6 10h7M9 14h9"/>',
    'cantos': '<circle cx="8" cy="12" r="5"/><circle cx="8" cy="12" r="1.5"/><path d="M8 7h12v4h-9"/>',
    'equipo': '<circle cx="9" cy="8" r="3"/><path d="M3 20a6 6 0 0 1 12 0"/><circle cx="17" cy="9" r="2.5"/>'
              '<path d="M16 14.2A5 5 0 0 1 21 19"/>',
    'marca': '<path d="M12 3.5 14.6 9l5.9.6-4.4 4 1.3 5.9L12 16.5l-5.4 3 1.3-5.9-4.4-4 5.9-.6Z"/>',
}


def svg(clave, clase='icono'):
    """El ícono como SVG para una plantilla (vacío si la clave no existe)."""
    interior = ICONOS.get(clave)
    if not interior:
        return ''
    return format_html('<svg class="{}" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" '
                       'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{}</svg>',
                       clase, mark_safe(interior))
