"""Lo que pasa en el puesto, sin HTTP: marcar piezas, terminar muebles, cargar y entregar bultos. Cada función
devuelve un dict para el puesto o lanza `Rechazo` (el mismo de la API de trabajos).

`resultado`: 'ok' (se hizo), 'ya' (ya estaba hecho: no cambia nada) o 'error' (no se hizo). Con 'ok' u 'ya',
`otro_proyecto` avisa que la pieza no es del proyecto elegido en el puesto (se marca igual en el suyo: decisión de
Martín, 2026-10-11).

Ficha 17: el puesto ya no elige proyecto (lo dice la etiqueta). Para los números de mecanizado manda el de la última
pieza leída; sin ninguno, el error trae `falta_proyecto`. Con una ubicación elegida, cada pieza o bulto leído queda
ahí (`Ubicado`)."""
from django.db import IntegrityError, transaction
from django.utils import timezone

from etiquetas import claves
from etiquetas.datos import proyecto_de, version_actual
from etiquetas.vistas import MAX_BULTOS
from proyectos.models import Proyecto
from trabajos.api import Rechazo, hora, nombre

from .calculo import (avance, etiqueta_de, faltan_en, leer, marcas_vigentes, numero, piezas_de)
from .models import (Bulto, Carga, Control, Etapa, FinDeMueble, Marca, Movimiento, Ubicacion, Ubicado, etapas_activas,
                     fijo)
from .pasos import control_a_dic

MAX_MOTIVO = 1000


def error(texto, **extra):
    return {'resultado': 'error', 'error': texto, **extra}


def pieza_a_dic(x):
    p = x['panel']
    return {'num': p.get('num', ''), 'nombre': p.get('nombre', ''), 'mueble': p.get('mueble', ''),
            'copia': x['copia'], 'de': x['de'], 'panel': p.get('id', '')}


def proyecto_a_dic(p):
    return {'id': p.pk, 'nombre': p.nombre}


FUERA_DE_PRODUCCION = {
    'desarrollo': 'Este proyecto está en desarrollo: habilitalo para producción en la pantalla del proyecto.',
    'archivado': 'Este proyecto está archivado: desarchivalo en la pantalla del proyecto.',
}


def fuera_de_produccion(p):
    """El aviso si el proyecto no se ve en producción (ficha 22), o None."""
    return FUERA_DE_PRODUCCION.get(p.estado)


def proyecto_o_rechazo(proyecto_id, solo_leer=False):
    """El proyecto del pedido. Para registrar algo tiene que estar en producción; `solo_leer`: el visor de un
    proyecto en desarrollo (abierto desde su pantalla) igual muestra su avance."""
    p = Proyecto.objects.select_related('version_actual').filter(pk=proyecto_id).first() \
        if isinstance(proyecto_id, int) and not isinstance(proyecto_id, bool) else None
    if p is None:
        raise Rechazo(404, 'Ese proyecto no existe.')
    if not solo_leer and fuera_de_produccion(p):
        raise Rechazo(409, fuera_de_produccion(p))
    return p


def motivo_de(texto):
    if texto is None:
        return ''
    if not isinstance(texto, str) or len(texto) > MAX_MOTIVO:
        raise Rechazo(400, 'motivo no válido')
    return texto.strip()


def sin_proyecto():
    return error('Escaneá primero una etiqueta QR o elegí el proyecto para leer números de mecanizado.', falta_proyecto=True)


def ubicacion_o_rechazo(ubicacion_id):
    """La ubicación prendida elegida en el puesto, o None si no se eligió."""
    if ubicacion_id is None:
        return None
    u = Ubicacion.objects.filter(pk=ubicacion_id, activa=True).first() \
        if isinstance(ubicacion_id, int) and not isinstance(ubicacion_id, bool) else None
    if u is None:
        raise Rechazo(400, 'Esa ubicación no existe o está apagada. Elegí otra.')
    return u


def ubicar(proyecto, ubicacion, usuario, ahora, pieza=None, bulto=None, marca=None):
    """La pieza (dict de piezas_de) o el bulto queda en la ubicación (None = salió del taller)."""
    return Ubicado.objects.create(proyecto=proyecto, huella=pieza['huella'] if pieza else '',
                                  clave=pieza['clave'] if pieza else None, bulto=bulto, ubicacion=ubicacion,
                                  marca=marca, por=usuario, cuando=ahora)


# ---------------------------------------------------------------- piezas por etapa

def etapa_o_rechazo(etapa_id):
    e = next((e for e in etapas_activas() if e.pk == etapa_id), None)
    if e is None:
        raise Rechazo(400, 'Esa etapa no existe o está apagada. Elegí otra.')
    return e


def proceso_prendido(tipo):
    """El proceso fijo de ese tipo, o Rechazo si está apagado en Procesos."""
    e = fijo(tipo)
    if e is None:
        raise Rechazo(400, 'Ese proceso está apagado en Procesos.')
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
        if fuera_de_produccion(e.proyecto):
            return error(fuera_de_produccion(e.proyecto))
        if e.tipo == e.Tipo.MUEBLE:
            return error('Es la etiqueta de un mueble. Acá se escanean piezas.', mueble=e.clave.get('mueble'))
        piezas = piezas_de(e.proyecto)
        x = next((x for x in piezas if x['clave'] == e.clave), None)
        if x is None:
            return error(f'Esta pieza ya no está en la versión actual de {e.proyecto.nombre}.')
        return e.proyecto, x, piezas
    # número de mecanizado (código de barras de OptiCut): la siguiente copia sin marcar, en el proyecto del puesto
    if proyecto_puesto is None:
        return sin_proyecto()
    piezas = piezas_de(proyecto_puesto)
    iguales = [x for x in piezas if x['panel'].get('num') and numero(x['panel']['num']) == lectura['numero']]
    if not iguales:
        return error(f'El mecanizado {lectura["numero"]} no está en {proyecto_puesto.nombre}.')
    hechas = set(marcas_vigentes(proyecto_puesto, [etapa]).values_list('huella', flat=True))
    x = next((x for x in iguales if x['huella'] not in hechas), iguales[0])
    return proyecto_puesto, x, piezas


def marcar(usuario, slug, texto, etapa_id, proyecto_id=None, ubicacion_id=None):
    etapa = etapa_o_rechazo(etapa_id)
    ubicacion = ubicacion_o_rechazo(ubicacion_id)
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
    if ubicacion is not None:
        # con "ya" no se ata a la marca: deshacer esa marca vieja no tiene que mover la pieza
        ubicar(proyecto, ubicacion, usuario, timezone.now(), pieza=x,
               marca=previa if salida['resultado'] == 'ok' else None)
        salida['ubicacion'] = ubicacion.nombre
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
    m.ubicados.filter(deshecho_en__isnull=True).update(deshecho_en=m.deshecha_en)
    return {'resultado': 'ok', 'marca': m.pk, 'etapa': m.etapa.nombre, 'pieza': m.clave,
            'proyecto': proyecto_a_dic(m.proyecto)}


# ---------------------------------------------------------------- fin de fabricación

def etapa_de_armado():
    from .models import etapa_de_armado as armado
    return armado()


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
            'faltan': [pieza_a_dic(x) for x in faltan], 'fin': fin_a_dic(m['fin']), 'max_bultos': MAX_BULTOS,
            'control': control_a_dic(Control.objects.filter(proyecto=proyecto, mueble=mueble)
                                     .select_related('por').last())}


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
            return sin_proyecto()
        x = next((x for x in piezas_de(puesto) if x['panel'].get('num')
                  and numero(x['panel']['num']) == lectura['numero']), None)
        if x is None:
            return error(f'El mecanizado {lectura["numero"]} no está en {puesto.nombre}.')
        return estado_del_mueble(puesto, x['panel']['mueble'])
    e = etiqueta_de(lectura['codigo'])
    if e is None:
        return error('Esta etiqueta no es de este taller.')
    if fuera_de_produccion(e.proyecto):
        return error(fuera_de_produccion(e.proyecto))
    mueble = e.clave.get('mueble')
    piezas = piezas_de(e.proyecto)
    if not any(x['panel']['mueble'] == mueble for x in piezas):
        return error(f'El mueble {mueble} ya no está en la versión actual de {e.proyecto.nombre}.')
    return estado_del_mueble(e.proyecto, mueble, piezas)


def terminar(usuario, proyecto_id, mueble, bultos, motivo, ubicacion_id=None):
    """Embalar el mueble en `bultos` bultos. Sin correlatividad (ficha 19): las piezas que faltaban en el armado quedan
    anotadas, pero no frenan."""
    proyecto = proyecto_o_rechazo(proyecto_id)
    ubicacion = ubicacion_o_rechazo(ubicacion_id)
    if not isinstance(mueble, str):
        raise Rechazo(400, 'mueble no válido')
    if isinstance(bultos, bool) or not isinstance(bultos, int) or not 1 <= bultos <= MAX_BULTOS:
        raise Rechazo(400, f'Los bultos van de 1 a {MAX_BULTOS}.')
    motivo = motivo_de(motivo)
    piezas = piezas_de(proyecto)
    estado = estado_del_mueble(proyecto, mueble, piezas)
    if estado['fin']:
        raise Rechazo(409, f'{mueble} ya está embalado.')
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
                if ubicacion is not None:
                    ubicar(proyecto, ubicacion, usuario, ahora, bulto=b)
    except IntegrityError:
        raise Rechazo(409, f'{mueble} ya está embalado.')
    return estado_del_mueble(proyecto, mueble, piezas)


def reabrir(usuario, proyecto_id, mueble):
    proyecto = proyecto_o_rechazo(proyecto_id)
    fin = FinDeMueble.objects.filter(proyecto=proyecto, mueble=mueble, anulado_en__isnull=True).first()
    if fin is None:
        raise Rechazo(404, 'Ese mueble no está embalado.')
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
    """Los muebles que van: los elegidos, todo el proyecto (lista vacía) o, en una carga libre, los que se cargaron."""
    if carga.libre:
        return list(carga.muebles)
    return carga.muebles or muebles_del_proyecto(carga.proyecto)


def pendientes_de_envio(proyecto):
    """Los muebles que todavía no salieron enteros: sin embalar o con algún bulto sin cargar en ninguna carga. Son los
    que la próxima carga trae tildados (lo que faltó en un envío queda para el siguiente)."""
    embalados = set(FinDeMueble.objects.filter(proyecto=proyecto, anulado_en__isnull=True)
                    .values_list('mueble', flat=True))
    sin_cargar = set(Bulto.objects.filter(proyecto=proyecto, fin__anulado_en__isnull=True, carga__isnull=True)
                     .values_list('mueble', flat=True))
    return [m for m in muebles_del_proyecto(proyecto) if m not in embalados or m in sin_cargar]


def contenido(carga):
    """{'bultos': bultos de sus muebles, 'sin_terminar': muebles sin embalar, 'faltan': bultos que no se cargaron en
    ninguna carga, 'faltantes': textos}. Lo que ya salió en otra carga no es faltante de esta."""
    muebles = muebles_de(carga)
    fines = {f.mueble: f for f in FinDeMueble.objects.filter(proyecto=carga.proyecto, mueble__in=muebles,
                                                              anulado_en__isnull=True)}
    bultos = list(Bulto.objects.filter(fin__in=fines.values()).select_related('fin', 'cargado_por', 'entregado_por',
                                                                              'carga'))
    bultos.sort(key=lambda b: (muebles.index(b.mueble), b.numero))
    sin_terminar = [m for m in muebles if m not in fines]
    faltan = [b for b in bultos if b.carga_id is None]
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
        'cargados': len(en_la_carga), 'entregados': len(entregados), 'libre': carga.libre,
        'total': len(en_la_carga) + len(c['faltan']) + len(c['sin_terminar']),
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
    # al camión deja de estar en el taller; si vuelve atrás, vuelve a donde estaba
    if a == Bulto.Estado.CARGADO and de == Bulto.Estado.EMBALADO:
        ubicar(bulto.proyecto, None, usuario, ahora, bulto=bulto)
    elif a == Bulto.Estado.EMBALADO:
        bulto.ubicados.filter(ubicacion__isnull=True, deshecho_en__isnull=True).update(deshecho_en=ahora)


# ---------------------------------------------------------------- tareas (modo "Tareas" del puesto)

def que_se_leyo(slug, texto, proyecto_id=None):
    """(proyecto, piezas, mueble, pieza) de la etiqueta de una pieza, de un mueble o de un bulto, o del número de
    mecanizado en el proyecto del puesto; o un dict de error. `pieza` es None si se leyó el mueble o un bulto."""
    puesto = proyecto_o_rechazo(proyecto_id) if proyecto_id is not None else None
    lectura = leer(texto, slug)
    if lectura is None:
        return error(f'No se reconoció un código en "{str(texto)[:40]}". Probá de nuevo o escribilo.')
    if lectura.get('ajena'):
        return error('Esta etiqueta es de otro taller.')
    if 'codigo' in lectura:
        e = etiqueta_de(lectura['codigo'])
        if e is None:
            return error('Esta etiqueta no es de este taller.')
        if fuera_de_produccion(e.proyecto):
            return error(fuera_de_produccion(e.proyecto))
        proyecto, piezas = e.proyecto, piezas_de(e.proyecto)
        if e.tipo == e.Tipo.MUEBLE:
            mueble, pieza = e.clave.get('mueble'), None
            if not any(x['panel']['mueble'] == mueble for x in piezas):
                return error(f'El mueble {mueble} ya no está en la versión actual de {proyecto.nombre}.')
        else:
            pieza = next((x for x in piezas if x['clave'] == e.clave), None)
            if pieza is None:
                return error(f'Esta pieza ya no está en la versión actual de {proyecto.nombre}.')
            mueble = pieza['panel']['mueble']
        return proyecto, piezas, mueble, pieza
    if puesto is None:
        return sin_proyecto()
    piezas = piezas_de(puesto)
    pieza = next((x for x in piezas if x['panel'].get('num') and numero(x['panel']['num']) == lectura['numero']),
                 None)
    if pieza is None:
        return error(f'El mecanizado {lectura["numero"]} no está en {puesto.nombre}.')
    return puesto, piezas, pieza['panel']['mueble'], pieza


def tareas_abiertas(proyecto, piezas, mueble, pieza=None):
    """Las tareas sin instalar de la pieza (y su mueble) o del mueble (y cualquiera de sus piezas). Las piezas de una
    tarea van por id del panel o nº de mecanizado."""
    from trabajos.models import Trabajo
    del_mueble = [x for x in piezas if x['panel']['mueble'] == mueble] if pieza is None else [pieza]
    claves_ = {str(c) for x in del_mueble for c in (x['panel'].get('id'), x['panel'].get('num')) if c}
    return [t for t in Trabajo.objects.filter(proyecto=proyecto).exclude(estado=Trabajo.Estado.INSTALADO)
            if mueble in (t.muebles or []) or claves_ & {str(c) for c in (t.piezas or [])}]


def tareas_de_lo_leido(slug, texto, proyecto_id=None):
    """(proyecto, qué se leyó, tareas sin instalar) de la etiqueta de una pieza o de un mueble, o un dict de error.
    De una pieza: las suyas y las de su mueble (como "en esta pieza o su mueble" del visor). De un mueble: las del
    mueble y las de cualquiera de sus piezas."""
    leido = que_se_leyo(slug, texto, proyecto_id)
    if isinstance(leido, dict):
        return leido
    proyecto, piezas, mueble, pieza = leido
    return (proyecto, {'mueble': mueble, 'pieza': pieza_a_dic(pieza) if pieza else None},
            tareas_abiertas(proyecto, piezas, mueble, pieza))


def bulto_leido(usuario, slug, carga_id, texto):
    """Cargar el bulto de la etiqueta leída. Sin correlatividad (ficha 19): la etiqueta del mueble o de una de sus
    piezas sirve si el mueble tiene un solo bulto, y un mueble sin embalar se embala ahí con 1 bulto. Sin carga
    (`carga_id` None, ficha 21): se crea una libre en el proyecto de lo leído, que lleva solo lo que se escanee."""
    proceso_prendido(Etapa.Tipo.CARGA)
    carga = carga_o_rechazo(carga_id) if carga_id is not None else None
    if carga is not None and carga.estado != Carga.Estado.ARMANDO:
        return error('Esta carga ya salió o se anuló: no se le suman bultos.')
    leido = que_se_leyo(slug, texto, carga.proyecto_id if carga else None)
    if isinstance(leido, dict):
        return leido
    proyecto, _, mueble, _ = leido
    if carga is None:
        # se crea y se carga por el camino de siempre; si esa primera lectura no carga nada, no queda la carga vacía
        carga = Carga.objects.create(proyecto=proyecto, libre=True, muebles=[], creada_por=usuario,
                                     creada_en=timezone.now())
        r = bulto_leido(usuario, slug, carga.pk, texto)
        if r.get('resultado') == 'error':
            carga.delete()
        return r
    if carga.libre and proyecto.pk == carga.proyecto_id and mueble not in carga.muebles:
        carga.muebles = carga.muebles + [mueble]
        carga.save(update_fields=['muebles'])
    lectura = leer(texto, slug) or {}
    n = lectura.get('bulto')
    base = {'mueble': mueble, 'numero': n or 1}
    if proyecto.pk != carga.proyecto_id:
        return error(f'Esto es de otro proyecto: {proyecto.nombre}.', **base)
    if mueble not in muebles_de(carga):
        return error(f'{mueble} no va en esta carga.', **base)
    fin = FinDeMueble.objects.filter(proyecto=carga.proyecto, mueble=mueble, anulado_en__isnull=True).first()
    if fin is None:
        sin_embalaje = fijo(Etapa.Tipo.EMBALAJE) is None
        terminar(usuario, carga.proyecto_id, mueble, 1, 'Sin embalaje' if sin_embalaje else 'Embalado al cargar')
        fin = FinDeMueble.objects.get(proyecto=carga.proyecto, mueble=mueble, anulado_en__isnull=True)
    if not n:
        if fin.bultos > 1:
            return error(f'{mueble} tiene {fin.bultos} bultos: escaneá la etiqueta de cada bulto.', **base)
        n = 1
    b = fin.lista_de_bultos.select_related('carga', 'cargado_por', 'entregado_por').filter(numero=n).first()
    if b is None:
        return error(f'{mueble} tiene {fin.bultos} bultos: esta etiqueta (bulto {n}) es de una impresión vieja.',
                     **base)
    base['de'] = fin.bultos
    ahora = timezone.now()
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
    """"Salió a obra". Sin correlatividad (ficha 19): sale igual con faltantes y quedan anotados (con el motivo, si lo
    escribieron). Sin el proceso de instalación, la carga queda entregada."""
    if carga.estado != Carga.Estado.ARMANDO:
        raise Rechazo(409, 'Esta carga ya salió.')
    motivo = motivo_de(motivo)
    c = contenido(carga)
    if not any(b.carga_id == carga.pk for b in c['bultos']):
        raise Rechazo(400, 'La carga está vacía: escaneá los bultos antes de salir.')
    ahora = timezone.now()
    carga.estado, carga.salio_por, carga.salio_en = Carga.Estado.SALIO, usuario, ahora
    carga.faltantes, carga.motivo = c['faltantes'], motivo if c['faltantes'] else ''
    carga.save(update_fields=['estado', 'salio_por', 'salio_en', 'faltantes', 'motivo'])
    if fijo(Etapa.Tipo.INSTALACION) is None:
        # sin el proceso de instalación, salir a obra es entregar (ficha 19: ya no hay "Entregar en obra")
        for b in carga.bultos.filter(estado=Bulto.Estado.CARGADO):
            mover(b, Bulto.Estado.ENTREGADO, usuario, carga, ahora)
        carga.estado, carga.entregada_por, carga.entregada_en = Carga.Estado.ENTREGADA, usuario, ahora
        carga.save(update_fields=['estado', 'entregada_por', 'entregada_en'])
    return carga



# ---------------------------------------------------------------- ABM de cargas (ficha 21)

def modificar_carga(usuario, carga, muebles):
    """Cambiar los muebles de una carga que se está cargando. No se saca un mueble con bultos ya cargados acá."""
    if carga.estado != Carga.Estado.ARMANDO:
        raise Rechazo(409, 'Esta carga ya salió o se anuló: no se modifica.')
    todos = muebles_del_proyecto(carga.proyecto)
    if not muebles:
        raise Rechazo(400, 'Elegí al menos un mueble.')
    if any(m not in todos for m in muebles):
        raise Rechazo(400, 'Algún mueble ya no está en la versión actual. Volvé a elegir.')
    cargados = set(carga.bultos.values_list('mueble', flat=True))
    sacados = sorted(cargados - set(muebles))
    if sacados:
        raise Rechazo(409, f'{", ".join(sacados)} ya tiene bultos en esta carga: descargalos antes de sacarlo.')
    carga.muebles = [] if set(muebles) == set(todos) else [m for m in todos if m in muebles]
    carga.libre = False
    carga.save(update_fields=['muebles', 'libre'])
    return carga


def anular_carga(usuario, carga):
    """Baja de una carga que no salió: los bultos cargados vuelven a embalados (libres para otra carga) y queda
    anulada, con quién y cuándo."""
    if carga.estado != Carga.Estado.ARMANDO:
        raise Rechazo(409, 'Solo se anula una carga que todavía no salió.')
    ahora = timezone.now()
    with transaction.atomic():
        for b in carga.bultos.filter(estado=Bulto.Estado.CARGADO).select_related('proyecto'):
            mover(b, Bulto.Estado.EMBALADO, usuario, carga, ahora)
        carga.estado, carga.anulada_por, carga.anulada_en = Carga.Estado.ANULADA, usuario, ahora
        carga.save(update_fields=['estado', 'anulada_por', 'anulada_en'])
    return carga
