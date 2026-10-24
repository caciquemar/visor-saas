"""Lo que pasa en Mi puesto del armado a la instalación (ficha 18), sin HTTP: armar un mueble entero, el control de
calidad y la instalación en obra. Como acciones.py: devuelve un dict para el puesto o lanza `Rechazo`."""
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.utils import timezone

from talleres.limites import permite
from trabajos.api import Rechazo

from .acciones import (etapa_de_armado, motivo_de, proyecto_a_dic, proyecto_o_rechazo, que_se_leyo, tareas_abiertas,
                       ubicacion_o_rechazo, ubicar)
from .calculo import marcas_vigentes, piezas_de
from .models import Bulto, Control, FotoDeInstalacion, Instalacion, Marca, puntos_de_control
from .pasos import control_a_dic, pasos

MAX_NOTA = 1000


def nota_de(texto):
    if texto is None:
        return ''
    if not isinstance(texto, str) or len(texto) > MAX_NOTA:
        raise Rechazo(400, 'nota no válida')
    return texto.strip()


def mueble_de(proyecto, mueble, piezas=None):
    piezas = piezas_de(proyecto) if piezas is None else piezas
    if not isinstance(mueble, str) or not any(x['panel']['mueble'] == mueble for x in piezas):
        raise Rechazo(404, f'Ese mueble no está en la versión actual de {proyecto.nombre}.')
    return piezas


# ---------------------------------------------------------------- armado del mueble entero

def armar_mueble(usuario, slug, texto, proyecto_id=None, ubicacion_id=None):
    """La etiqueta de cualquier pieza del mueble (o la del mueble) deja todas sus piezas en la etapa de armado. Las
    que ya estaban no cambian. Con ubicación, todas quedan ahí."""
    ubicacion = ubicacion_o_rechazo(ubicacion_id)
    armado = etapa_de_armado()
    if armado is None:
        raise Rechazo(400, 'No hay etapas prendidas. Prendé alguna en Procesos.')
    leido = que_se_leyo(slug, texto, proyecto_id)
    if isinstance(leido, dict):
        return leido
    proyecto, piezas, mueble, _ = leido
    del_mueble = [x for x in piezas if x['panel']['mueble'] == mueble]
    hechas = set(marcas_vigentes(proyecto, [armado]).filter(mueble=mueble).values_list('huella', flat=True))
    ahora, nuevas = timezone.now(), []
    for x in del_mueble:
        marca = None
        if x['huella'] not in hechas:
            try:
                with transaction.atomic():
                    marca = Marca.objects.create(proyecto=proyecto, etapa=armado, clave=x['clave'], huella=x['huella'],
                                                 mueble=mueble, por=usuario, cuando=ahora)
                nuevas.append(marca.pk)
            except IntegrityError:          # la marcó otro puesto en el mismo momento
                pass
        if ubicacion is not None:
            ubicar(proyecto, ubicacion, usuario, ahora, pieza=x, marca=marca)
    return {'resultado': 'ok' if nuevas else 'ya', 'proyecto': proyecto_a_dic(proyecto), 'mueble': mueble,
            'etapa': armado.nombre, 'piezas': len(del_mueble), 'nuevas': len(nuevas), 'marcas': nuevas,
            'ubicacion': ubicacion.nombre if ubicacion else None}


# ---------------------------------------------------------------- control de calidad

def puntos_activos():
    return [p for p in puntos_de_control() if p.activa]


def control_leido(slug, texto, proyecto_id=None):
    leido = que_se_leyo(slug, texto, proyecto_id)
    if isinstance(leido, dict):
        return leido
    proyecto, piezas, mueble, _ = leido
    m = pasos(proyecto, piezas)['muebles'][mueble]
    ultimo = Control.objects.filter(proyecto=proyecto, mueble=mueble).select_related('por').last()
    return {'resultado': 'ok', 'proyecto': proyecto_a_dic(proyecto), 'mueble': mueble,
            'armado': m['armado'], 'piezas': m['piezas'], 'armadas': m['armadas'],
            'puntos': [{'id': p.pk, 'nombre': p.nombre} for p in puntos_activos()],
            'ultimo': control_a_dic(ultimo)}


def controlar(usuario, taller, proyecto_id, mueble, resultados):
    """Guarda el control: cada punto prendido con ok (sí o no) y una nota. Cada punto mal crea una tarea del mueble
    (si el plan del taller tiene tareas); igual se puede seguir con el embalaje."""
    from trabajos.models import Trabajo
    proyecto = proyecto_o_rechazo(proyecto_id)
    mueble_de(proyecto, mueble)
    if not isinstance(resultados, list):
        raise Rechazo(400, 'resultados no válidos')
    por_punto = {}
    for r in resultados:
        if not isinstance(r, dict) or not isinstance(r.get('ok'), bool) or isinstance(r.get('punto'), bool) \
                or not isinstance(r.get('punto'), int):
            raise Rechazo(400, 'resultados no válidos')
        por_punto[r['punto']] = (r['ok'], nota_de(r.get('nota')))
    puntos = puntos_activos()
    faltan = [p.nombre for p in puntos if p.pk not in por_punto]
    if faltan:
        raise Rechazo(400, f'Falta revisar: {", ".join(faltan)}.')
    con_tareas = permite(taller, 'trabajos')
    salida = []
    with transaction.atomic():
        for p in puntos:
            ok, nota = por_punto[p.pk]
            tarea = None
            if not ok and con_tareas:
                texto = f'Control de calidad · {p.nombre}' + (f': {nota}' if nota else '')
                tarea = Trabajo.objects.create(proyecto=proyecto, texto=texto, muebles=[mueble], autor=usuario).pk
            salida.append({'punto': p.pk, 'nombre': p.nombre, 'ok': ok, 'nota': nota, 'tarea': tarea})
        c = Control.objects.create(proyecto=proyecto, mueble=mueble, resultados=salida,
                                   ok=all(r['ok'] for r in salida), por=usuario, cuando=timezone.now())
    return {'resultado': 'ok', 'proyecto': proyecto_a_dic(proyecto), 'mueble': mueble, 'control': control_a_dic(c),
            'tareas': [r['tarea'] for r in salida if r['tarea']]}


# ---------------------------------------------------------------- instalación en obra

def faltantes_de(proyecto, piezas, mueble):
    """Lo que falta para instalar: bultos sin entregar (o el mueble sin embalar) y tareas sin instalar."""
    bultos = list(Bulto.objects.filter(proyecto=proyecto, mueble=mueble, fin__anulado_en__isnull=True)
                  .order_by('numero'))
    faltan = [f'Bulto {b.numero} de {len(bultos)} sin entregar' for b in bultos if b.estado != Bulto.Estado.ENTREGADO]
    if not bultos:
        faltan.append('Sin embalar')
    abiertas = tareas_abiertas(proyecto, piezas, mueble)
    faltan += [f'Tarea: {t.texto[:80]}' for t in abiertas]
    return faltan, abiertas


def estado_instalacion(proyecto, mueble, piezas=None):
    """(la tarjeta de "Instalar en obra", las tareas abiertas del mueble): las tareas las arma la API con su formato."""
    piezas = mueble_de(proyecto, mueble, piezas)
    faltan, abiertas = faltantes_de(proyecto, piezas, mueble)
    m = pasos(proyecto, piezas)['muebles'][mueble]
    return {'resultado': 'ok', 'proyecto': proyecto_a_dic(proyecto), 'mueble': mueble,
            'bultos': m['bultos'], 'control': m['control'], 'instalacion': m['instalacion'],
            'faltan': faltan}, abiertas


def instalacion_leida(slug, texto, proyecto_id=None):
    leido = que_se_leyo(slug, texto, proyecto_id)
    if isinstance(leido, dict):
        return leido, []
    proyecto, piezas, mueble, _ = leido
    return estado_instalacion(proyecto, mueble, piezas)


def instalar(usuario, proyecto_id, mueble, nota, motivo):
    proyecto = proyecto_o_rechazo(proyecto_id)
    piezas = mueble_de(proyecto, mueble)
    nota, motivo = nota_de(nota), motivo_de(motivo)
    faltan, _ = faltantes_de(proyecto, piezas, mueble)
    if faltan and not motivo:
        raise Rechazo(400, f'Faltan {len(faltan)}: escribí el motivo para marcarlo instalado igual.')
    try:
        with transaction.atomic():
            i = Instalacion.objects.create(proyecto=proyecto, mueble=mueble, nota=nota,
                                           motivo=motivo if faltan else '', faltantes=faltan, por=usuario,
                                           cuando=timezone.now())
    except IntegrityError:
        raise Rechazo(409, f'{mueble} ya está instalado.')
    return proyecto, i


def desinstalar(usuario, proyecto_id, mueble):
    """Deshacer la instalación (dueño u oficina): queda con quién y cuándo."""
    proyecto = proyecto_o_rechazo(proyecto_id)
    i = Instalacion.objects.filter(proyecto=proyecto, mueble=mueble, anulado_en__isnull=True).first()
    if i is None:
        raise Rechazo(404, 'Ese mueble no está marcado instalado.')
    i.anulado_por, i.anulado_en = usuario, timezone.now()
    i.save(update_fields=['anulado_por', 'anulado_en'])
    return {'resultado': 'ok', 'mueble': mueble}


def instalacion_o_rechazo(instalacion_id):
    i = Instalacion.objects.select_related('proyecto').filter(pk=instalacion_id, anulado_en__isnull=True).first() \
        if isinstance(instalacion_id, int) else None
    if i is None:
        raise Rechazo(404, 'Esa instalación no existe o se deshizo.')
    return i


def guardar_foto(usuario, taller, instalacion, datos, extension):
    foto = FotoDeInstalacion(instalacion=instalacion, tamano=len(datos), subida_por=usuario)
    foto.taller = taller
    foto.archivo.save(f'instalacion-{instalacion.pk}.{extension}', ContentFile(datos), save=False)
    try:
        foto.save()
    except BaseException:
        default_storage.delete(foto.archivo.name)
        raise
    return foto
