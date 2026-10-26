"""Borrar un proyecto archivado del todo (ficha 22): la base se borra en cascada (versiones, marcas, bultos, cargas,
tareas, etiquetas, links…) y después sus archivos: las carpetas de sus versiones (originales, resultado y
combinaciones del probador) y las fotos de sus tareas, instalaciones y anotaciones. Si un archivo no se puede borrar
queda en el almacenamiento, sin nada que lo use (se anota en el log)."""
import logging

from django.core.files.storage import default_storage
from django.db import transaction

log = logging.getLogger(__name__)


def archivos_de(proyecto):
    """(carpetas, archivos sueltos) del proyecto, antes de borrarlo."""
    from avance.models import FotoDeAnotacion, FotoDeInstalacion
    from trabajos.models import Foto
    carpetas = [v.carpeta() for v in proyecto.versiones.all()]
    sueltos = [o.archivo.name for v in proyecto.versiones.all() for o in v.originales.all()]
    sueltos += list(Foto.objects.filter(trabajo__proyecto=proyecto).values_list('archivo', flat=True))
    sueltos += list(FotoDeInstalacion.objects.filter(instalacion__proyecto=proyecto).values_list('archivo', flat=True))
    sueltos += list(FotoDeAnotacion.objects.filter(anotacion__proyecto=proyecto).values_list('archivo', flat=True))
    return carpetas, [s for s in sueltos if s]


def borrar_carpeta(carpeta, conservar=frozenset()):
    try:
        carpetas, archivos = default_storage.listdir(carpeta)
    except (FileNotFoundError, NotADirectoryError):
        return
    for a in archivos:
        if carpeta + a not in conservar:
            default_storage.delete(carpeta + a)
    for c in carpetas:
        borrar_carpeta(f'{carpeta}{c}/', conservar)


def borrar_version(version):
    """Una versión vieja: su fila (con sus originales, combinaciones y Zicar en cascada) y su carpeta. "Volver a
    convertir" no copia los archivos subidos, la versión nueva apunta a los de la vieja: esos quedan."""
    from .models import Original
    otros = set(Original.objects.filter(version__proyecto_id=version.proyecto_id).exclude(version=version)
                .values_list('archivo', flat=True))
    carpeta = version.carpeta()
    with transaction.atomic():
        version.delete()
    try:
        borrar_carpeta(carpeta, otros)
    except Exception:                     # noqa: BLE001 — la base ya se borró: que no falle el pedido
        log.exception('No se pudo borrar la carpeta %s', carpeta)


def borrar(proyecto):
    carpetas, sueltos = archivos_de(proyecto)
    with transaction.atomic():
        proyecto.delete()
    for ruta in sueltos:
        try:
            default_storage.delete(ruta)
        except Exception:                 # noqa: BLE001 — la base ya se borró: que no falle el pedido
            log.exception('No se pudo borrar %s', ruta)
    for carpeta in carpetas:
        try:
            borrar_carpeta(carpeta)
        except Exception:                 # noqa: BLE001
            log.exception('No se pudo borrar la carpeta %s', carpeta)
