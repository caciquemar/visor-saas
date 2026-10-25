"""Lo que pasa en Mi puesto del armado a la instalación (fichas 18 y 19), sin HTTP: marcar un mueble entero (Armado y
los procesos del taller por mueble), el control de calidad, el embalaje y la instalación en obra. Como acciones.py:
devuelve un dict para el puesto o lanza `Rechazo`.

Ficha 19: escanear ya es el registro (sin confirmar), con chequeo de duplicado ('ya', con quién y cuándo), y sin
correlatividad: ningún proceso exige el anterior. Cada proceso fijo apagado en Procesos se rechaza."""
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.utils import timezone

from etiquetas.vistas import MAX_BULTOS
from talleres.limites import permite
from trabajos.api import Rechazo, hora, nombre

from .acciones import (estado_del_mueble, mover, proceso_prendido, proyecto_a_dic, proyecto_o_rechazo, que_se_leyo,
                       tareas_abiertas, terminar, ubicacion_o_rechazo, ubicar)
from .calculo import marcas_vigentes, piezas_de
from .models import (Anotacion, Bulto, Carga, Control, Etapa, FinDeMueble, FotoDeAnotacion, FotoDeInstalacion,
                     Instalacion, Marca, Movimiento, etapas_activas, procesos as procesos_del_taller, puntos_de_control)
from .pasos import anotacion_a_dic, control_a_dic, pasos

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

def proceso_por_mueble(etapa_id):
    """Armado (si no se dice otro) o un proceso del taller que se marca por mueble, prendido."""
    if etapa_id is None:
        return proceso_prendido(Etapa.Tipo.ARMADO)
    e = next((e for e in etapas_activas() if e.pk == etapa_id and e.por_mueble), None)
    if e is None:
        raise Rechazo(400, 'Ese proceso no existe, está apagado o no se marca por mueble.')
    return e


def armar_mueble(usuario, slug, texto, proyecto_id=None, ubicacion_id=None, etapa_id=None):
    """La etiqueta de cualquier pieza del mueble (o la del mueble) deja todas sus piezas en ese proceso (Armado, o uno
    del taller por mueble). Las que ya estaban no cambian; si estaban todas, 'ya' con quién y cuándo. Con ubicación,
    todas quedan ahí."""
    ubicacion = ubicacion_o_rechazo(ubicacion_id)
    armado = proceso_por_mueble(etapa_id)
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
    salida = {'resultado': 'ok' if nuevas else 'ya', 'proyecto': proyecto_a_dic(proyecto), 'mueble': mueble,
              'etapa': armado.nombre, 'piezas': len(del_mueble), 'nuevas': len(nuevas), 'marcas': nuevas,
              'ubicacion': ubicacion.nombre if ubicacion else None}
    if not nuevas:
        ultima = marcas_vigentes(proyecto, [armado]).filter(mueble=mueble).select_related('por').last()
        salida['ya'] = {'por': nombre(ultima.por), 'cuando': hora(ultima.cuando)} if ultima else None
    return salida


# ---------------------------------------------------------------- control de calidad

def puntos_activos():
    return [p for p in puntos_de_control() if p.activa]


def control_leido(slug, texto, proyecto_id=None):
    proceso_prendido(Etapa.Tipo.CONTROL)
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
    proceso_prendido(Etapa.Tipo.CONTROL)
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


# ---------------------------------------------------------------- embalaje

def embalar(usuario, slug, texto, proyecto_id=None, ubicacion_id=None):
    """Escanear el mueble lo deja embalado con 1 bulto (se corrige con cambiar_bultos). Si ya estaba, 'ya'."""
    proceso_prendido(Etapa.Tipo.EMBALAJE)
    leido = que_se_leyo(slug, texto, proyecto_id)
    if isinstance(leido, dict):
        return leido
    proyecto, piezas, mueble, _ = leido
    if FinDeMueble.objects.filter(proyecto=proyecto, mueble=mueble, anulado_en__isnull=True).exists():
        return {**estado_del_mueble(proyecto, mueble, piezas), 'resultado': 'ya'}
    try:
        return {**terminar(usuario, proyecto.pk, mueble, 1, '', ubicacion_id), 'resultado': 'ok'}
    except Rechazo as e:
        if e.codigo != 409:          # lo embaló otro puesto en el mismo momento
            raise
        return {**estado_del_mueble(proyecto, mueble, piezas), 'resultado': 'ya'}


def cambiar_bultos(usuario, proyecto_id, mueble, n):
    """Corrige la cantidad de bultos de un mueble embalado mientras ninguno se cargó: suma los que faltan (embalados
    ahora) o saca los de número más alto."""
    proyecto = proyecto_o_rechazo(proyecto_id)
    if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= MAX_BULTOS:
        raise Rechazo(400, f'Los bultos van de 1 a {MAX_BULTOS}.')
    fin = FinDeMueble.objects.filter(proyecto=proyecto, mueble=mueble, anulado_en__isnull=True).first()
    if fin is None:
        raise Rechazo(404, 'Ese mueble no está embalado.')
    bultos = list(fin.lista_de_bultos.order_by('numero'))
    if any(b.estado != Bulto.Estado.EMBALADO for b in bultos):
        raise Rechazo(409, 'Ya se cargó algún bulto de este mueble: no se puede cambiar la cantidad.')
    ahora = timezone.now()
    with transaction.atomic():
        for b in bultos[n:]:
            b.delete()
        for numero in range(len(bultos) + 1, n + 1):
            b = Bulto.objects.create(fin=fin, proyecto=proyecto, mueble=mueble, numero=numero,
                                     embalado_por=usuario, embalado_en=ahora)
            Movimiento.objects.create(bulto=b, a=Bulto.Estado.EMBALADO, usuario=usuario, cuando=ahora)
        fin.bultos = n
        fin.save(update_fields=['bultos'])
    return estado_del_mueble(proyecto, mueble)


# ---------------------------------------------------------------- instalación en obra

def estado_instalacion(proyecto, mueble, piezas=None):
    """(la tarjeta de "Instalar en obra", las tareas abiertas del mueble): las tareas las arma la API con su formato."""
    piezas = mueble_de(proyecto, mueble, piezas)
    m = pasos(proyecto, piezas)['muebles'][mueble]
    return {'resultado': 'ok', 'proyecto': proyecto_a_dic(proyecto), 'mueble': mueble,
            'bultos': m['bultos'], 'control': m['control'], 'instalacion': m['instalacion']}, \
        tareas_abiertas(proyecto, piezas, mueble)


def registrar_instalacion(usuario, proyecto, mueble, nota=''):
    """Instala el mueble y deja sus bultos entregados (ya no hay "Entregar en obra"); la carga que quedó sin nada por
    entregar pasa a entregada. None si ya estaba instalado."""
    ahora = timezone.now()
    try:
        with transaction.atomic():
            i = Instalacion.objects.create(proyecto=proyecto, mueble=mueble, nota=nota, por=usuario, cuando=ahora)
            cargas = set()
            for b in Bulto.objects.filter(proyecto=proyecto, mueble=mueble, fin__anulado_en__isnull=True) \
                    .exclude(estado=Bulto.Estado.ENTREGADO).select_related('carga'):
                mover(b, Bulto.Estado.ENTREGADO, usuario, b.carga, ahora)
                if b.carga_id:
                    cargas.add(b.carga_id)
            for c in Carga.objects.filter(pk__in=cargas, estado=Carga.Estado.SALIO):
                if not c.bultos.exclude(estado=Bulto.Estado.ENTREGADO).exists():
                    c.estado, c.entregada_por, c.entregada_en = Carga.Estado.ENTREGADA, usuario, ahora
                    c.save(update_fields=['estado', 'entregada_por', 'entregada_en'])
    except IntegrityError:
        return None
    return i


def instalar_leido(usuario, slug, texto, proyecto_id=None):
    """Escanear el mueble (o un bulto, o una pieza) lo deja instalado. Si ya estaba, 'ya' con quién y cuándo."""
    proceso_prendido(Etapa.Tipo.INSTALACION)
    leido = que_se_leyo(slug, texto, proyecto_id)
    if isinstance(leido, dict):
        return leido, []
    proyecto, piezas, mueble, _ = leido
    hecha = registrar_instalacion(usuario, proyecto, mueble)
    datos, abiertas = estado_instalacion(proyecto, mueble, piezas)
    return {**datos, 'resultado': 'ok' if hecha else 'ya'}, abiertas


def instalar(usuario, proyecto_id, mueble, nota='', motivo=''):
    """Marcar instalado desde la Lista (permiso Corregir producción), con una nota."""
    proceso_prendido(Etapa.Tipo.INSTALACION)
    proyecto = proyecto_o_rechazo(proyecto_id)
    mueble_de(proyecto, mueble)
    i = registrar_instalacion(usuario, proyecto, mueble, nota_de(nota))
    if i is None:
        raise Rechazo(409, f'{mueble} ya está instalado.')
    return proyecto, i


def desinstalar(usuario, proyecto_id, mueble):
    """Deshacer la instalación (Corregir producción): queda con quién y cuándo. Los bultos siguen entregados."""
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


# ---------------------------------------------------------------- anotaciones (ficha 19)

def anotar(usuario, taller, proyecto_id, mueble, panel, proceso_id, texto, con_tarea):
    """Una anotación pegada a lo que se escaneó: el mueble y, si fue una pieza, la pieza (`panel`: el id del panel).
    `con_tarea` ("Hay que arreglarlo") crea además la tarea de la pieza o del mueble, si el plan del taller la
    permite."""
    from trabajos.models import Trabajo
    proyecto = proyecto_o_rechazo(proyecto_id)
    piezas = mueble_de(proyecto, mueble)
    texto = nota_de(texto)
    if not texto:
        raise Rechazo(400, 'Escribí la anotación.')
    pieza = None
    if panel:
        pieza = next((x for x in piezas if x['panel'].get('id') == panel and x['panel']['mueble'] == mueble), None)
        if pieza is None:
            raise Rechazo(404, 'Esa pieza no está en ese mueble.')
    proceso = next((e for e in procesos_del_taller() if e.pk == proceso_id), None) if proceso_id else None
    with transaction.atomic():
        tarea = None
        if con_tarea and permite(taller, 'trabajos'):
            tarea = Trabajo.objects.create(proyecto=proyecto, texto=texto, autor=usuario,
                                           piezas=[panel] if pieza else [], muebles=[] if pieza else [mueble])
        a = Anotacion.objects.create(
            proyecto=proyecto, mueble=mueble, panel=panel or '', proceso=proceso, texto=texto, tarea=tarea,
            pieza=f"{pieza['panel'].get('num') or 's/n'} {pieza['panel'].get('nombre', '')}".strip() if pieza else '',
            por=usuario, cuando=timezone.now())
    return {'resultado': 'ok', 'anotacion': anotacion_a_dic(a)}


def anotacion_o_rechazo(anotacion_id):
    a = Anotacion.objects.select_related('tarea').filter(pk=anotacion_id).first() \
        if isinstance(anotacion_id, int) else None
    if a is None:
        raise Rechazo(404, 'Esa anotación no existe.')
    return a


def guardar_foto_de_anotacion(usuario, taller, anotacion, datos, extension):
    """La foto queda en la anotación y, si creó una tarea, también en la tarea (la ven quienes la resuelven)."""
    from trabajos.models import Foto
    guardadas = []
    try:
        foto = FotoDeAnotacion(anotacion=anotacion, tamano=len(datos), subida_por=usuario)
        foto.taller = taller
        foto.archivo.save(f'anotacion-{anotacion.pk}.{extension}', ContentFile(datos), save=False)
        guardadas.append(foto.archivo.name)
        foto.save()
        if anotacion.tarea_id:
            f = Foto(trabajo=anotacion.tarea, tamano=len(datos), subida_por=usuario)
            f.taller = taller
            f.archivo.save(f'trabajo-{anotacion.tarea_id}.{extension}', ContentFile(datos), save=False)
            guardadas.append(f.archivo.name)
            f.save()
    except BaseException:
        for nombre_ in guardadas:
            default_storage.delete(nombre_)
        raise
    return foto
