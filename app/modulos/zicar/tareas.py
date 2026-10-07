"""Paso Zicar de la conversión: baja el ZIP de la carpeta del postprocesador, lo descomprime, corre pb2zicar en un
proceso aparte con límite de tiempo (modulos/zicar/proceso.py) y guarda `<proyecto>_zicar.zip` en la carpeta de la
versión. Va en su propia tarea: si falla, el visor del proyecto sigue andando."""
import json
import logging
import os
import subprocess
import sys
import tempfile
from datetime import timedelta
from functools import partial
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone
from django.utils.text import get_valid_filename
from huey.contrib.djhuey import db_task

from proyectos.archivos import nombre_local
from proyectos.models import Original
from proyectos.tareas import bajar
from talleres.separacion import tarea_de_taller

from .models import ResultadoZicar
from .zips import ZipInvalido, comprimir, extraer

log = logging.getLogger('visor.zicar')

TARDO = 'La conversión para la Zicar tardó demasiado y se cortó. Probá "Volver a convertir"; si vuelve a pasar, avisanos.'
GENERICO = ('No pudimos convertir la carpeta para la Zicar. Revisá que sea la carpeta que genera Polyboard en '
            '"Exportar a postprocesador" (tipo DXF). Si está todo bien, avisanos.')
NINGUNA = ('No se pudo convertir ninguna pieza para la Zicar. Revisá que la carpeta sea la del postprocesador de '
           'Polyboard (tipo DXF).')


def encolar(version):
    """Si la versión trae la carpeta del postprocesador, la anota y la manda a la cola al confirmar."""
    if not version.originales.filter(tipo=Original.Tipo.POSTPROCESADOR).exists():
        return
    ResultadoZicar.objects.update_or_create(version=version, defaults=dict(
        estado=ResultadoZicar.Estado.EN_COLA, mensaje='', avisos=[], piezas=0, archivo='', nombre='',
        empezado=None, terminado=None))
    transaction.on_commit(partial(convertir_zicar, version.taller_id, version.pk))


@db_task()
@tarea_de_taller
def convertir_zicar(version_id):
    resultado = ResultadoZicar.objects.select_related('version__proyecto').get(version_id=version_id)
    if resultado.estado != ResultadoZicar.Estado.EN_COLA:
        return
    resultado.estado = ResultadoZicar.Estado.CONVIRTIENDO
    resultado.empezado = timezone.now()
    resultado.save(update_fields=['estado', 'empezado'])
    try:
        with tempfile.TemporaryDirectory(prefix='zicar-') as tmp:
            error = convertir_en(resultado, Path(tmp))
    except ZipInvalido as e:
        error = str(e)
    except Exception:
        log.exception('Falló la conversión Zicar de la versión %s', version_id)
        error = GENERICO
    if error:
        resultado.estado = ResultadoZicar.Estado.ERROR
        resultado.mensaje = error
        resultado.terminado = timezone.now()
        resultado.save(update_fields=['estado', 'mensaje', 'terminado'])


def convertir_en(resultado, tmp):
    """Hace la conversión en la carpeta temporal y deja el resultado listo. Devuelve un mensaje de error o None."""
    version = resultado.version
    original = version.originales.filter(tipo=Original.Tipo.POSTPROCESADOR).first()
    entrada, salida = tmp / 'entrada', tmp / 'salida'
    entrada.mkdir()
    bajar(original.archivo.name, tmp / 'carpeta.zip')
    raiz = extraer(tmp / 'carpeta.zip', entrada)

    datos = dict(entrada=str(entrada), salida=str(salida), resultado=str(tmp / 'resultado.json'))
    (tmp / 'entrada.json').write_text(json.dumps(datos, ensure_ascii=False), encoding='utf-8')
    entorno = {**os.environ, 'PYTHONIOENCODING': 'utf-8',
               'PYTHONPATH': os.pathsep.join([str(settings.BASE_DIR), os.environ.get('PYTHONPATH', '')])}
    try:
        p = subprocess.run([sys.executable, '-m', 'modulos.zicar.proceso', str(tmp / 'entrada.json')], cwd=tmp,
                           env=entorno, capture_output=True, timeout=settings.CONVERSION_SEGUNDOS)
    except subprocess.TimeoutExpired:
        log.warning('Conversión Zicar cortada por tiempo (%s s)', settings.CONVERSION_SEGUNDOS)
        return TARDO
    errores = p.stderr.decode('utf-8', 'replace')[-4000:]
    if p.returncode != 0 or not (tmp / 'resultado.json').exists():
        log.error('El proceso Zicar terminó con código %s:\n%s', p.returncode, errores)
        return GENERICO
    if errores.strip():
        log.warning('Piezas con error en la conversión Zicar de la versión %s:\n%s', version.pk, errores)
    res = json.loads((tmp / 'resultado.json').read_text(encoding='utf-8'))
    if not res['piezas']:
        return NINGUNA

    base = nombre_local(raiz or version.proyecto.nombre)
    nombre = f'{base}_zicar.zip'
    comprimir(salida, tmp / 'zicar.zip', f'{base}_zicar')
    with open(tmp / 'zicar.zip', 'rb') as f:
        guardado = default_storage.save(f'{version.carpeta()}zicar/{get_valid_filename(nombre)}', File(f))

    resultado.estado = ResultadoZicar.Estado.LISTO
    resultado.piezas = res['piezas']
    resultado.avisos = res['avisos']
    resultado.archivo = guardado
    resultado.nombre = nombre
    resultado.mensaje = ''
    resultado.terminado = timezone.now()
    resultado.save()
    return None


def revisar_si_se_corto(resultado):
    """Como Version.revisar_si_se_corto: si el consumidor se cayó a mitad, pasado el límite queda en error."""
    limite = timedelta(seconds=settings.CONVERSION_SEGUNDOS + 300)
    if (resultado.estado == ResultadoZicar.Estado.CONVIRTIENDO and resultado.empezado
            and timezone.now() - resultado.empezado > limite):
        resultado.estado = ResultadoZicar.Estado.ERROR
        resultado.mensaje = 'Se cortó la conversión para la Zicar. Probá "Volver a convertir".'
        resultado.terminado = timezone.now()
        resultado.save(update_fields=['estado', 'mensaje', 'terminado'])

