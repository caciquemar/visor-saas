"""Conversión de una versión en la cola. La tarea baja los originales y las texturas del taller a una carpeta
temporal, corre el conversor en un proceso aparte (proyectos/proceso.py) con límite de tiempo y de memoria, y sube
el resultado a la carpeta de la versión. Los errores quedan en la versión con un mensaje para el taller; el detalle
técnico va al log."""
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from functools import partial
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.core.files import File
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.utils import timezone
from huey.contrib.djhuey import db_task

from conversor.polyboard_a_app import clave
from talleres.separacion import tarea_de_taller

from .archivos import nombre_local
from .models import Material, Version

log = logging.getLogger('visor.conversion')

TARDO = ('El proyecto tardó demasiado en convertirse y se cortó. Revisá que el DXF sea el 3D exportado de '
         'Polyboard (sin piezas de más). Si es un proyecto muy grande, avisanos.')
MEMORIA = ('El proyecto es demasiado grande para convertirlo. Probá exportarlo dividido en partes y, si sigue '
           'pasando, avisanos.')
GENERICO = ('No pudimos convertir el proyecto. Revisá que el DXF sea el 3D exportado de Polyboard y que la lista '
            'sea el .ocp de OptiCut del mismo proyecto. Si está todo bien, avisanos.')
NOMBRE_PROYECTO = 'proyecto.json'     # el JSON principal queda siempre con este nombre en resultado/
GRUPO = {Material.Tipo.TABLERO: 'tableros', Material.Tipo.CANTO: 'cantos'}    # como los separa el conversor


def encolar(version):
    """Manda la versión a la cola cuando se confirma la transacción en curso (si no, el consumidor podría
    buscarla antes de que exista)."""
    transaction.on_commit(partial(convertir_version, version.taller_id, version.pk))


@db_task()
@tarea_de_taller
def convertir_version(version_id):
    version = Version.objects.select_related('proyecto').get(pk=version_id)
    if version.estado != Version.Estado.EN_COLA:
        return
    version.estado = Version.Estado.CONVIRTIENDO
    version.empezada = timezone.now()
    version.save(update_fields=['estado', 'empezada'])
    try:
        with tempfile.TemporaryDirectory(prefix='visor-') as tmp:
            res = correr(preparar(version, Path(tmp)), Path(tmp))
            if 'error' not in res:
                guardar_resultado(version, Path(tmp) / 'resultado', res)
                return
    except Exception:
        log.exception('Falló la conversión de la versión %s', version_id)
        res = {'error': GENERICO}
    version.estado = Version.Estado.ERROR
    version.mensaje = res['error']
    version.terminada = timezone.now()
    version.save(update_fields=['estado', 'mensaje', 'terminada'])


def bajar(nombre_en_almacenamiento, destino):
    with default_storage.open(nombre_en_almacenamiento, 'rb') as origen, open(destino, 'wb') as f:
        shutil.copyfileobj(origen, f, 1024 * 1024)


def preparar(version, tmp):
    """Arma la carpeta temporal: originales, texturas del taller y materiales.json. Devuelve la entrada del
    proceso."""
    originales, texturas, resultado = tmp / 'originales', tmp / 'Textures', tmp / 'resultado'
    for carpeta in (originales, texturas, tmp / 'Materials', resultado):
        carpeta.mkdir()
    dxf, ocps = None, []
    for o in version.originales.all():
        local = originales / nombre_local(o.nombre)
        n = 1
        while local.exists():                 # dos .ocp con el mismo nombre: no pisar
            n += 1
            local = originales / f'{Path(nombre_local(o.nombre)).stem} ({n}){Path(o.nombre).suffix}'
        bajar(o.archivo.name, local)
        if o.tipo == o.Tipo.DXF:
            dxf = str(local)
        else:
            ocps.append(str(local))

    # Biblioteca del taller -> materiales.json del conversor (tiene prioridad sobre lo que diga el .ocp), con
    # tableros y cantos por separado.
    forzados = {'tableros': {}, 'cantos': {}}
    for m in Material.objects.all():
        info = {}
        if m.textura:
            archivo = f'{m.pk}{Path(m.textura.name).suffix.lower()}'
            bajar(m.textura.name, texturas / archivo)
            info['textura'] = archivo
            if m.ancho_mm:
                info['ancho'] = m.ancho_mm
        if m.color:
            info['color'] = m.color
        if info:
            forzados[GRUPO[m.tipo]][m.nombre] = info
    if forzados['tableros'] or forzados['cantos']:
        (resultado / 'materiales.json').write_text(json.dumps(forzados, ensure_ascii=False), encoding='utf-8')

    return dict(dxf=dxf, ocps=ocps, destino=str(resultado), texturas=[str(texturas)],
                biblioteca=str(tmp / 'Materials'),       # vacía: en el servidor no están las de Polyboard
                codigo=version.proyecto.codigo_cliente, memoria_mb=settings.CONVERSION_MEMORIA_MB,
                sin_canto=version.taller.color_sin_canto,
                salida=str(tmp / 'salida.json'))


def correr(entrada, tmp):
    """Corre proyectos/proceso.py con límite de tiempo. Devuelve lo que dejó en salida.json, o {error: ...}."""
    ruta_entrada = tmp / 'entrada.json'
    ruta_entrada.write_text(json.dumps(entrada, ensure_ascii=False), encoding='utf-8')
    entorno = {**os.environ, 'PYTHONIOENCODING': 'utf-8',
               'PYTHONPATH': os.pathsep.join([str(settings.RAIZ), str(settings.BASE_DIR)])}
    try:
        p = subprocess.run([sys.executable, '-m', 'proyectos.proceso', str(ruta_entrada)], cwd=tmp, env=entorno,
                           capture_output=True, timeout=settings.CONVERSION_SEGUNDOS)
    except subprocess.TimeoutExpired:
        log.warning('Conversión cortada por tiempo (%s s)', settings.CONVERSION_SEGUNDOS)
        return {'error': TARDO}
    salida = Path(entrada['salida'])
    errores = p.stderr.decode('utf-8', 'replace')[-4000:]
    if p.returncode != 0 or not salida.exists():
        log.error('El proceso de conversión terminó con código %s:\n%s', p.returncode, errores)
        return {'error': MEMORIA if 'MemoryError' in errores else GENERICO}
    res = json.loads(salida.read_text(encoding='utf-8'))
    if res.get('memoria'):
        return {'error': MEMORIA}
    return res


def guardar_resultado(version, resultado, res):
    """Sube el resultado, anota los materiales que no tienen textura y deja la versión lista."""
    (resultado / 'materiales.json').unlink(missing_ok=True)     # es entrada, no resultado
    base = f'{version.carpeta()}resultado/'
    archivo_proyecto = ''
    for f in sorted(resultado.rglob('*')):
        if not f.is_file():
            continue
        relativo = PurePosixPath(f.relative_to(resultado).as_posix())
        es_principal = str(relativo) == res['archivo']
        with open(f, 'rb') as contenido:
            guardado = default_storage.save(base + (NOMBRE_PROYECTO if es_principal else str(relativo)),
                                            File(contenido))
        if es_principal:
            archivo_proyecto = guardado

    faltan = anotar_materiales(res.get('con_imagen', {}))
    # Las imágenes que faltan se muestran aparte, con el botón para subirlas: no se repiten como avisos (el
    # conversor los escribe "tablero X: no se encontró la imagen …" o "canto X: …").
    sin_imagen = {(f['tipo'], clave(f['nombre'])) for f in faltan}

    def repetido(aviso):
        cabeza, separador, _ = aviso.partition(': no se encontró la imagen ')
        tipo, _, nombre = cabeza.partition(' ')
        return bool(separador) and (tipo, clave(nombre)) in sin_imagen
    avisos = [a for a in res['avisos'] if not repetido(a)]

    version.estado = Version.Estado.LISTO
    version.avisos = avisos
    version.resumen = {**res['resumen'], 'proyecto_polyboard': res['proyecto']}
    version.faltan_texturas = faltan
    version.archivo_proyecto = archivo_proyecto
    version.terminada = timezone.now()
    version.mensaje = ''
    with transaction.atomic():
        version.save()
        proyecto = version.proyecto
        actual = proyecto.version_actual
        if actual is None or actual.numero < version.numero:
            proyecto.version_actual = version
            proyecto.save(update_fields=['version_actual', 'actualizado'])


def anotar_materiales(con_imagen):
    """Suma a la biblioteca los tableros y cantos que en Polyboard tienen imagen (cada tipo por su lado).
    Devuelve los que no tienen textura subida todavía: [{nombre, tipo}]."""
    faltan = []
    for tipo, grupo in GRUPO.items():
        for nombre, (ruta, ancho) in sorted(con_imagen.get(grupo, {}).items(), key=lambda x: clave(x[0])):
            m = Material.objects.filter(tipo=tipo, clave=clave(nombre)).first()
            if m is None:
                try:
                    with transaction.atomic():
                        m = Material.objects.create(tipo=tipo, nombre=nombre, ruta_polyboard=ruta,
                                                    ancho_mm=round(ancho) if ancho else None)
                except IntegrityError:            # otra conversión lo creó recién
                    m = Material.objects.get(tipo=tipo, clave=clave(nombre))
            elif not m.ruta_polyboard:
                m.ruta_polyboard = ruta
                if not m.ancho_mm and ancho:
                    m.ancho_mm = round(ancho)
                m.save(update_fields=['ruta_polyboard', 'ancho_mm', 'actualizado'])
            if not m.textura:
                faltan.append({'nombre': nombre, 'tipo': str(tipo)})   # como figura en este proyecto
    return faltan
