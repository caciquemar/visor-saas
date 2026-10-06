"""Dónde quedan los archivos de un proyecto (siempre dentro de la carpeta del taller, ver talleres/archivos.py):

    talleres/<taller>/proyectos/<proyecto>/versiones/<n>/originales/   lo que subió el taller (DXF y .ocp)
    talleres/<taller>/proyectos/<proyecto>/versiones/<n>/resultado/    lo que generó el conversor
"""
import posixpath
import re

from django.utils.text import get_valid_filename

from talleres.archivos import carpeta_de_taller


def carpeta_de_version(version):
    if version.taller_id is None or version.proyecto_id is None or not version.numero:
        raise ValueError('La versión no tiene taller, proyecto o número todavía')
    return f'{carpeta_de_taller(version.taller_id)}proyectos/{int(version.proyecto_id)}/versiones/{int(version.numero)}/'


def solo_nombre(nombre):
    """Nombre de archivo sin carpetas (el navegador puede mandar C:\\...\\x.dxf)."""
    return posixpath.basename((nombre or '').replace('\\', '/'))


def nombre_local(nombre):
    """Nombre seguro para escribir en una carpeta temporal, sin perder espacios ni acentos (el conversor usa el
    nombre del DXF como nombre del proyecto)."""
    limpio = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', solo_nombre(nombre)).strip(' .')
    return limpio[:150] or 'archivo'


def ruta_original(instancia, nombre):
    """upload_to de Original: <versión>/originales/<nombre>."""
    base = get_valid_filename(solo_nombre(nombre)) or 'archivo'
    return f'{carpeta_de_version(instancia.version)}originales/{base}'
