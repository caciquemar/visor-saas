"""Lo que pasa en el puesto, sin HTTP: marcar piezas, terminar muebles, cargar y entregar bultos. Cada función
devuelve un dict para el puesto o lanza `Rechazo` (el mismo de la API de trabajos).

`resultado`: 'ok' (se hizo), 'ya' (ya estaba hecho: no cambia nada) o 'error' (no se hizo). Con 'ok' u 'ya',
`otro_proyecto` avisa que la pieza no es del proyecto elegido en el puesto (se marca igual en el suyo: decisión de
Martín, 2026-10-11)."""
from django.db import IntegrityError, transaction
from django.utils import timezone

from etiquetas import claves
from etiquetas.datos import proyecto_de, version_actual
from etiquetas.vistas import MAX_BULTOS
from proyectos.models import Proyecto
from trabajos.api import Rechazo, hora, nombre

from .calculo import (avance, etiqueta_de, faltan_en, leer, marcas_vigentes, numero, piezas_de)
from .models import Bulto, Carga, FinDeMueble, Marca, Movimiento, etapas_activas

MAX_MOTIVO = 1000


def error(texto, **extra):
    return {'resultado': 'error', 'error': texto, **extra}


def pieza_a_dic(x):
    p = x['panel']
    return {'num': p.get('num', ''), 'nombre': p.get('nombre', ''), 'mueble': p.get('mueble', ''),
            'copia': x['copia'], 'de': x['de'], 'panel': p.get('id', '')}


def proyecto_a_dic(p):
    return {'id': p.pk, 'nombre': p.nombre}


def proyecto_o_rechazo(proyecto_id):
    p = Proyecto.objects.select_related('version_actual').filter(pk=proyecto_id).first() \
        if isinstance(proyecto_id, int) and not isinstance(proyecto_id, bool) else None
    if p is None:
        raise Rechazo(404, 'Ese proyecto no existe.')
    return p


def motivo_de(texto):
    if texto is None:
        return ''
    if not isinstance(texto, str) or len(texto) > MAX_MOTIVO:
        raise Rechazo(400, 'motivo no válido')
    return texto.strip()


# ---------------------------------------------------------------- piezas por etapa

def etapa_o_rechazo(etapa_id):
    e = next((e for e in etapas_activas() if e.pk == etapa_id), None)
    if e is None:
        raise Rechazo(400, 'Esa etapa no existe o está apagada. Elegí otra.')
    return e


def cuenta(proyecto, etapa, piezas, mueble=None):
    """Cuántas piezas (del mueble o del proyecto) ya pasaron por la etapa."""
    huellas = {x['huella'] for x in piezas if mueble is None or x['panel']['mueble'] == mueble}
    hechas = set(marcas_vigentes(proyecto, [etapa]).values_list('huella', flat=True))
    return {'hechas': len(huellas & hechas), 'piezas': len(huellas)}


def ya_marcada(marca):
    return {'por': nombre(marca.por), 'cuando': hora(marca.cuando)}


def pieza_leida(texto, slug, proyecto_puesto, etapa):
    """(proyecto, pieza, piezas del proyecto) de lo que se leyó, o un dict de error."""
    lectura = leer(texto, slug)
    if lectura is None:
        return error(f'No se reconoció un código en "{str(texto)[:40]}". Probá de nuevo o escribilo.')
    if lectura.get('ajena'):
        return error('Esta etiqueta es de otro taller.')
    if 'codigo' in lectura:
        e = etiqueta_de(lectura['codigo'])
        if e is None:
            return error('Esta etiqueta no es de este taller.')
        if e.tipo == e.Tipo.MUEBLE:
            return error('Es la etiqueta de un mueble. Acá se escanean piezas.', mueble=e.clave.get('mueble'))
        piezas = piezas_de(e.proyecto)
        x = next((x for x in piezas if x['clave'] == e.clave), None)
        if x is None:
            return error(f'Esta pieza ya no está en la versión actual de {e.proyecto.nombre}.')
        return e.proyecto, x, piezas
    # número de mecanizado (código de barras de OptiCut): la siguiente copia sin marcar, en el proyecto del puesto
    if proyecto_puesto is None:
        return error('Para leer números de mecanizado, elegí primero el proyecto.')
    piezas = piezas_de(proyecto_puesto)
    iguales = [x for x in piezas if x['panel'].get('num') and numero(x['panel']['num']) == lectura['numero']]
    if not iguales:
        return error(f'El mecanizado {lectura["numero"]} no está en {proyecto_puesto.nombre}.')
    hechas = set(marcas_vigentes(proyecto_puesto, [etapa]).values_list('huella', flat=True))
    x = next((x for x in iguales if x['huella'] not in hechas), iguales[0])
    return proyecto_puesto, x, piezas


def marcar(usuario, slug, texto, etapa_id, proyecto_id=None):
    etapa = etapa_o_rechazo(etapa_id)
    puesto = proyecto_o_rechazo(proyecto_id) if proyecto_id is not None else None
    leido = pieza_leida(texto, slug, puesto, etapa)
    if isinstance(leido, dict):
        return leido
    proyecto, x, piezas = leido
    salida = {'pieza': pieza_a_dic(x), 'proyecto': proyecto_a_dic(proyecto), 'etapa': etapa.nombre,
              'otro_proyecto': puesto is not None and proyecto.pk != puesto.pk}
    previa = marcas_vigentes(proyecto, [etapa]).filter(huella=x['huella']).select_related('por').first()
    if previa is None:
        try:
            with transaction.atomic():
                previa = Marca.objects.create(proyecto=proyecto, etapa=etapa, clave=x['clave'], huella=x['huella'],
                                              mueble=x['panel']['mueble'], por=usuario, cuando=timezone.now())
            salida.update(resultado='ok', marca=previa.pk)
        except IntegrityError:          # la marcó otro puesto en el mismo momento
            previa = marcas_vigentes(proyecto, [etapa]).filter(huella=x['huella']).select_related('por').first()
            salida.update(resultado='ya', ya=ya_marcada(previa), marca=previa.pk)
    else:
        salida.update(resultado='ya', ya=ya_marcada(previa), marca=previa.pk)
    salida['mueble'] = cuenta(proyecto, etapa, piezas, x['panel']['mueble'])
    salida['total'] = cuenta(proyecto, etapa, piezas)
    return salida


def deshacer(usuario, marca_id):
    m = Marca.objects.select_related('proyecto', 'etapa').filter(pk=marca_id, deshecha_en__isnull=True).first() \
        if isinstance(marca_id, int) else None
    if m is None:
        raise Rechazo(404, 'Esa marca no existe o ya se deshizo.')
    m.deshecha_por, m.deshecha_en = usuario, timezone.now()
    m.save(update_fields=['deshecha_por', 'deshecha_en'])
    return {'resultado': 'ok', 'marca': m.pk, 'etapa': m.etapa.nombre, 'pieza': m.clave,
            'proyecto': proyecto_a_dic(m.proyecto)}


# ---------------------------------------------------------------- fin de fabricación

def etapa_de_armado():
    activas = etapas_activas()
    return activas[-1] if activas else None


def fin_a_dic(f):
    if f is None:
        return None
    bultos = list(f.lista_de_bultos.order_by('numero'))
    return {'id': f.pk, 'por': nombre(f.por), 'cuando': hora(f.cuando), 'bultos': f.bultos, 'motivo': f.motivo,
            'faltantes': f.faltantes,
            'lista': [{'numero': b.numero, 'estado': b.estado, 'estado_texto': b.get_estado_display()}
                      for b in bultos]}


def estado_del_mueble(proyecto, mueble, piezas=None):
    piezas = piezas_de(proyecto) if piezas is None else piezas
    if not any(x['panel']['mueble'] == mueble for x in piezas):
        raise Rechazo(404, f'El mueble {mueble} no está en la versión actual de {proyecto.nombre}.')
    a = avance(proyecto, piezas)
    m = a['muebles'][mueble]
    armado = etapa_de_armado()
    faltan = faltan_en(proyecto, mueble, armado, piezas) if armado else []
    return {'resultado': 'ok', 'proyecto': proyecto_a_dic(proyecto), 'mueble': mueble, 'pct': m['pct'],
            'piezas': m['piezas'], 'etapa': armado.nombre if armado else '',
            'por_etapa': [{'nombre': e.nombre, 'hechas': m['por_etapa'][e.pk]} for e in a['etapas']],
            'faltan': [pieza_a_dic(x) for x in faltan], 'fin': fin_a_dic(m['fin']), 'max_bultos': MAX_BULTOS}


def mueble_leido(slug, texto, proyecto_id=None):
    """En "Fin de fabricación": la etiqueta del mueble (o de un bulto, o de una de sus piezas)."""
    puesto = proyecto_o_rechazo(proyecto_id) if proyecto_id is not None else None
    lectura = leer(texto, slug)
    if lectura is None:
        return error('No se reconoció un código. Probá de nuevo o escribilo.')
    if lectura.get('ajena'):
        return error('Esta etiqueta es de otro taller.')
    if 'numero' in lectura:
        if puesto is None:
            return error('Para leer números de mecanizado, elegí primero el proyecto.')
        x = next((x for x in piezas_de(puesto) if x['panel'].get('num')
                  and numero(x['panel']['num']) == lectura['numero']), None)
        if x is None:
            return error(f'El mecanizado {lectura["numero"]} no está en {puesto.nombre}.')
        return estado_del_mueble(puesto, x['panel']['mueble'])
    e = etiqueta_de(lectura['codigo'])
    if e is None:
        return error('Esta etiqueta no es de este taller.')
    mueble = e.clave.get('mueble')
    piezas = piezas_de(e.proyecto)
    if not any(x['panel']['mueble'] == mueble for x in piezas):
        return error(f'El mueble {mueble} ya no está en la versión actual de {e.proyecto.nombre}.')
    return estado_del_mueble(e.proyecto, mueble, piezas)


def terminar(usuario, proyecto_id, mueble, bultos, motivo):
    proyecto = proyecto_o_rechazo(proyecto_id)
    if not isinstance(mueble, str):
        raise Rechazo(400, 'mueble no válido')
    if isinstance(bultos, bool) or not isinstance(bultos, int) or not 1 <= bultos <= MAX_BULTOS:
        raise Rechazo(400, f'Los bultos van de 1 a {MAX_BULTOS}.')
    motivo = motivo_de(motivo)
    piezas = piezas_de(proyecto)
    estado = estado_del_mueble(proyecto, mueble, piezas)
    if estado['fin']:
        raise Rechazo(409, f'{mueble} ya tiene la fabricación terminada.')
    if estado['faltan'] and not motivo:
        raise Rechazo(400, f'Faltan {len(estado["faltan"])} piezas sin marcar en {estado["etapa"]}: '
                           'escribí el motivo para terminar igual.')
    ahora = timezone.now()
    faltantes = [f'{p["num"] or "s/n"} {p["nombre"]}'.strip() for p in estado['faltan']]
    try:
        with transaction.atomic():
            fin = FinDeMueble.objects.create(proyecto=proyecto, mueble=mueble, bultos=bultos, motivo=motivo,
                                             faltantes=faltantes, por=usuario, cuando=ahora)
            for n in range(1, bultos + 1):
                b = Bulto.objects.create(fin=fin, proyecto=proyecto, mueble=mueble, numero=n,
                                         embalado_por=usuario, embalado_en=ahora)
                Movimiento.objects.create(bulto=b, a=Bulto.Estado.EMBALADO, usuario=usuario, cuando=ahora)
    except IntegrityError:
        raise Rechazo(409, f'{mueble} ya tiene la fabricación terminada.')
    return estado_del_mueble(proyecto, mueble, piezas)


def reabrir(usuario, proyecto_id, mueble):
    proyecto = proyecto_o_rechazo(proyecto_id)
    fin = FinDeMueble.objects.filter(proyecto=proyecto, mueble=mueble, anulado_en__isnull=True).first()
    if fin is None:
        raise Rechazo(404, 'Ese mueble no tiene la fabricación terminada.')
    if fin.lista_de_bultos.exclude(estado=Bulto.Estado.EMBALADO).exists():
        raise Rechazo(409, 'Hay bultos de este mueble cargados o entregados: no se puede reabrir.')
    fin.anulado_por, fin.anulado_en = usuario, timezone.now()
    fin.save(update_fields=['anulado_por', 'anulado_en'])
    return {'resultado': 'ok', 'mueble': mueble}


# ---------------------------------------------------------------- cargas

def muebles_del_proyecto(proyecto):
    v = version_actual(proyecto)
    return list(claves.muebles(proyecto_de(v))) if v else []


def crear_carga(usuario, proyecto, muebles):
    todos = muebles_del_proyecto(proyecto)
    if not todos:
        raise Rechazo(400, 'El proyecto no tiene una versión lista.')
    if any(m not in todos for m in muebles):
        raise Rechazo(400, 'Algún mueble ya no está en la versión actual. Volvé a elegir.')
    if set(muebles) == set(todos):
        muebles = []
    return Carga.objects.create(proyecto=proyecto, muebles=muebles, creada_por=usuario, creada_en=timezone.now())


def muebles_de(carga):
    return carga.muebles or muebles_del_proyecto(carga.proyecto)


def contenido(carga):
    """{'bultos': bultos que van, 'sin_terminar': muebles sin fin de fabricación, 'faltantes': textos}."""
    muebles = muebles_de(carga)
    fines = {f.mueble: f for f in FinDeMueble.objects.filter(proyecto=carga.proyecto, mueble__in=muebles,
                                                              anulado_en__isnull=True)}
    bultos = list(Bulto.objects.filter(fin__in=fines.values()).select_related('fin', 'cargado_por', 'entregado_por',
                                                                              'carga'))
    bultos.sort(key=lambda b: (muebles.index(b.mueble), b.numero))
    sin_terminar = [m for m in muebles if m not in fines]
    faltan = [b for b in bultos if b.carga_id != carga.pk]
    faltantes = ([f'{b.mueble} · bulto {b.numero} de {b.fin.bultos}' for b in faltan]
                 + [f'{m} · sin terminar' for m in sin_terminar])
    return {'bultos': bultos, 'sin_terminar': sin_terminar, 'faltan': faltan, 'faltantes': faltantes}


def corto(dt):
    if not dt:
        return None
    dt = timezone.localtime(dt)
    return f'{dt.day}/{dt.month} {dt:%H:%M}'


def carga_a_dic(carga):
    c = contenido(carga)
    en_la_carga = [b for b in c['bultos'] if b.carga_id == carga.pk]
    entregados = [b for b in en_la_carga if b.estado == Bulto.Estado.ENTREGADO]
    return {
        'id': carga.pk, 'proyecto': proyecto_a_dic(carga.proyecto), 'estado': carga.estado,
        'estado_texto': carga.get_estado_display(), 'muebles': muebles_de(carga), 'completa': not carga.muebles,
        'bultos': [{'id': b.pk, 'mueble': b.mueble, 'numero': b.numero, 'de': b.fin.bultos, 'estado': b.estado,
                    'en_esta': b.carga_id == carga.pk,
                    'por': nombre(b.entregado_por if b.estado == b.Estado.ENTREGADO else b.cargado_por)
                    if b.carga_id == carga.pk else None,
                    'cuando': hora(b.entregado_en if b.estado == b.Estado.ENTREGADO else b.cargado_en)
                    if b.carga_id == carga.pk else None,
                    'cuando_corto': corto(b.entregado_en if b.estado == b.Estado.ENTREGADO else b.cargado_en)
                    if b.carga_id == carga.pk else None} for b in c['bultos']],
        'sin_terminar': c['sin_terminar'], 'faltantes': c['faltantes'],
        'cargados': len(en_la_carga), 'entregados': len(entregados),
        'total': len(c['bultos']) + len(c['sin_terminar']),
    }


def carga_o_rechazo(carga_id):
    c = Carga.objects.select_related('proyecto__version_actual').filter(pk=carga_id).first() \
        if isinstance(carga_id, int) else None
    if c is None:
        raise Rechazo(404, 'Esa carga no existe.')
    return c


def mover(bulto, a, usuario, carga, ahora):
    de = bulto.estado
    bulto.estado = a
    if a == Bulto.Estado.CARGADO and de == Bulto.Estado.EMBALADO:
        bulto.carga, bulto.cargado_por, bulto.cargado_en = carga, usuario, ahora
    elif a == Bulto.Estado.ENTREGADO:
        bulto.entregado_por, bulto.entregado_en = usuario, ahora
    elif a == Bulto.Estado.EMBALADO:
        bulto.carga, bulto.cargado_por, bulto.cargado_en = None, None, None
    elif a == Bulto.Estado.CARGADO:          # vuelve de entregado
        bulto.entregado_por, bulto.entregado_en = None, None
    bulto.save()
    Movimiento.objects.create(bulto=bulto, carga=carga, de=de, a=a, usuario=usuario, cuando=ahora)


def bulto_leido(usuario, slug, carga_id, texto, entregar=False):
    """Cargar (o entregar, en obra) el bulto de la etiqueta leída."""
    carga = carga_o_rechazo(carga_id)
    if not entregar and carga.estado != Carga.Estado.ARMANDO:
        return error('Esta carga ya salió: no se le suman bultos.')
    if entregar and carga.estado != Carga.Estado.SALIO:
        return error('La carga todavía no salió a obra.' if carga.estado == Carga.Estado.ARMANDO
                     else 'Esta carga ya está entregada.')
    lectura = leer(texto, slug)
    if lectura is None or 'numero' in lectura:
        return error('Escaneá la etiqueta del bulto (la del mueble con "Bulto 1 de 3").')
    if lectura.get('ajena'):
        return error('Esta etiqueta es de otro taller.')
    e = etiqueta_de(lectura['codigo'])
    if e is None:
        return error('Esta etiqueta no es de este taller.')
    if e.tipo != e.Tipo.MUEBLE or not lectura['bulto']:
        return error('Es la etiqueta de una pieza. Escaneá la del bulto.')
    mueble, n = e.clave.get('mueble'), lectura['bulto']
    base = {'mueble': mueble, 'numero': n}
    if e.proyecto_id != carga.proyecto_id:
        return error(f'Este bulto es de otro proyecto: {e.proyecto.nombre}.', **base)
    if mueble not in muebles_de(carga):
        return error(f'{mueble} no va en esta carga.', **base)
    fin = FinDeMueble.objects.filter(proyecto=carga.proyecto, mueble=mueble, anulado_en__isnull=True).first()
    if fin is None:
        return error(f'{mueble} no tiene la fabricación terminada.', **base)
    b = fin.lista_de_bultos.select_related('carga', 'cargado_por', 'entregado_por').filter(numero=n).first()
    if b is None:
        return error(f'{mueble} tiene {fin.bultos} bultos: esta etiqueta (bulto {n}) es de una impresión vieja.',
                     **base)
    base['de'] = fin.bultos
    ahora = timezone.now()
    if entregar:
        if b.carga_id != carga.pk:
            return error('Este bulto no vino en esta carga.', **base)
        if b.estado == b.Estado.ENTREGADO:
            r = {'resultado': 'ya', 'ya': {'por': nombre(b.entregado_por), 'cuando': hora(b.entregado_en)}}
        else:
            mover(b, b.Estado.ENTREGADO, usuario, carga, ahora)
            r = {'resultado': 'ok'}
            if not carga.bultos.exclude(estado=Bulto.Estado.ENTREGADO).exists():
                carga.estado, carga.entregada_por, carga.entregada_en = Carga.Estado.ENTREGADA, usuario, ahora
                carga.save(update_fields=['estado', 'entregada_por', 'entregada_en'])
    else:
        if b.carga_id == carga.pk:
            r = {'resultado': 'ya', 'ya': {'por': nombre(b.cargado_por), 'cuando': hora(b.cargado_en)}}
        elif b.estado != b.Estado.EMBALADO:
            return error(f'Este bulto ya está en otra carga ({b.carga.get_estado_display().lower()}).', **base)
        else:
            mover(b, b.Estado.CARGADO, usuario, carga, ahora)
            r = {'resultado': 'ok'}
    return {**r, **base, 'bulto': b.pk, 'carga': carga_a_dic(carga)}


def deshacer_bulto(usuario, carga_id, bulto_id):
    carga = carga_o_rechazo(carga_id)
    b = carga.bultos.filter(pk=bulto_id).first() if isinstance(bulto_id, int) else None
    if b is None:
        raise Rechazo(404, 'Ese bulto no está en esta carga.')
    ahora = timezone.now()
    if b.estado == b.Estado.CARGADO and carga.estado == Carga.Estado.ARMANDO:
        mover(b, b.Estado.EMBALADO, usuario, carga, ahora)
    elif b.estado == b.Estado.ENTREGADO and carga.estado == Carga.Estado.SALIO:
        mover(b, b.Estado.CARGADO, usuario, carga, ahora)
    else:
        raise Rechazo(409, 'Ya no se puede deshacer: la carga cambió de estado.')
    return {'resultado': 'ok', 'carga': carga_a_dic(carga)}


def salir(usuario, carga, motivo):
    """"Salió a obra": con faltantes, solo confirmando con un motivo."""
    if carga.estado != Carga.Estado.ARMANDO:
        raise Rechazo(409, 'Esta carga ya salió.')
    motivo = motivo_de(motivo)
    c = contenido(carga)
    if not any(b.carga_id == carga.pk for b in c['bultos']):
        raise Rechazo(400, 'La carga está vacía: escaneá los bultos antes de salir.')
    if c['faltantes'] and not motivo:
        raise Rechazo(400, f'Faltan {len(c["faltantes"])}: escribí el motivo para salir igual.')
    carga.estado, carga.salio_por, carga.salio_en = Carga.Estado.SALIO, usuario, timezone.now()
    carga.faltantes, carga.motivo = c['faltantes'], motivo if c['faltantes'] else ''
    carga.save(update_fields=['estado', 'salio_por', 'salio_en', 'faltantes', 'motivo'])
    return carga

