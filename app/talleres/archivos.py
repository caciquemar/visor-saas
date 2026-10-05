"""Archivos de los talleres. Todo archivo se guarda bajo talleres/<id del taller>/ y se entrega solo por
`abrir_de_taller`, que rechaza cualquier ruta fuera del taller del pedido. MEDIA_URL no se publica."""
import posixpath
import secrets

from django.conf import settings
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404
from django.shortcuts import redirect
from django.utils.text import get_valid_filename


def carpeta_de_taller(taller_id):
    return f'talleres/{int(taller_id)}/'


def ruta_de_taller(instancia, nombre):
    """upload_to común: talleres/<taller>/<modelo>/<azar>_<nombre>."""
    if instancia.taller_id is None:
        raise ValueError('El dato no tiene taller todavía')
    base = get_valid_filename(posixpath.basename(nombre.replace('\\', '/'))) or 'archivo'
    return f'{carpeta_de_taller(instancia.taller_id)}{instancia._meta.model_name}/{secrets.token_hex(8)}_{base}'


def ruta_valida(taller, ruta):
    """La ruta si está dentro de la carpeta del taller; None si no (o si tiene algo raro)."""
    if taller is None or not ruta or '\\' in ruta or '\x00' in ruta or ':' in ruta or ruta.startswith('/'):
        return None
    partes = ruta.split('/')
    if any(p in ('', '.', '..') for p in partes):
        return None
    if not ruta.startswith(carpeta_de_taller(taller.pk)) or len(partes) < 3:
        return None
    return ruta


def abrir_de_taller(request, ruta, descarga=False):
    """Única forma de entregar un archivo de taller: 404 si no es del taller del pedido."""
    ruta = ruta_valida(getattr(request, 'taller', None), ruta)
    if ruta is None or not default_storage.exists(ruta):
        raise Http404('No existe el archivo')
    if settings.ALMACENAMIENTO == 'r2':
        return redirect(default_storage.url(ruta))          # URL firmada, vence en una hora
    return FileResponse(default_storage.open(ruta, 'rb'), as_attachment=descarga,
                        filename=posixpath.basename(ruta).partition('_')[2] or posixpath.basename(ruta))
