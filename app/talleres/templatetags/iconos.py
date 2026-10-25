"""{% load iconos %}{% icono 'produccion' %}: los íconos de talleres/iconos.py."""
from django import template

from talleres.iconos import svg

register = template.Library()


@register.simple_tag
def icono(clave, clase='icono'):
    return svg(clave, clase)
