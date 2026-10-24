"""Tablero de control de Producción (ficha 17, /<taller>/tablero/): cómo vienen los proyectos en curso, por etapa
y en general. Se arma en el servidor con `calculo.avance` de cada proyecto (las mismas cuentas que el visor y la
pantalla del proyecto).

En curso: tiene versión lista y le falta instalar algún mueble (instalar es el último paso). "Entrega" (ficha 18): cuántos muebles hay en cada paso, del armado a la instalación."""
from datetime import datetime, time, timedelta

from django.db.models import Count, Max
from django.utils import timezone

from proyectos.models import Proyecto, Version
from trabajos.models import Trabajo

from .calculo import avance, pct, piezas_de, ubicaciones
from .models import Bulto, Marca, Movimiento, Ubicacion, etapas_activas
from .pasos import ORDEN, PASOS, pasos


def proyectos_listos():
    return (Proyecto.objects.filter(version_actual__estado=Version.Estado.LISTO)
            .exclude(version_actual__archivo_proyecto='').order_by('nombre', 'pk'))


def de_un_proyecto(p, etapas, hay_ubicaciones):
    piezas = piezas_de(p)
    if not piezas:
        return None
    a = avance(p, piezas)
    bultos = dict(Bulto.objects.filter(proyecto=p, fin__anulado_en__isnull=True)
                  .values_list('estado').annotate(n=Count('pk')))
    muebles = len(a['muebles'])
    ultima = max(filter(None, [
        Marca.objects.filter(proyecto=p).aggregate(x=Max('cuando'))['x'],
        Movimiento.objects.filter(bulto__proyecto=p).aggregate(x=Max('cuando'))['x']]), default=None)
    t = a['total']
    entrega = pasos(p, piezas, a)['totales']
    instalados = entrega['instalado']
    return {
        'proyecto': p, 'pct': t['pct'], 'piezas': t['piezas'], 'pasos': t['pasos'], 'hechos': t['hechos'],
        'etapas': [{'nombre': e.nombre, 'hechas': t['por_etapa'][e.pk],
                    'pct': pct(t['por_etapa'][e.pk], t['piezas'])} for e in etapas],
        'muebles': muebles, 'terminados': t['terminados'],
        'embalados': bultos.get(Bulto.Estado.EMBALADO, 0), 'cargados': bultos.get(Bulto.Estado.CARGADO, 0),
        'entregados': bultos.get(Bulto.Estado.ENTREGADO, 0),
        'ubicadas': len(ubicaciones(p)[0]) if hay_ubicaciones else None,
        'ultima': ultima,
        # instalar es el último paso: con todo instalado está terminado aunque falten marcas de etapas
        'en_curso': instalados < muebles,
        'instalados': instalados, 'entrega': barra(entrega, muebles),
        'por_etapa': t['por_etapa'],
    }


def barra(totales, total):
    """Los pasos con cuántos muebles hay en cada uno, para una barra apilada (el ancho como texto con punto: CSS)."""
    return [{'clave': k, 'nombre': n, 'color': c, 'n': totales.get(k, 0),
             'pct': f'{totales.get(k, 0) * 100 / (total or 1):.2f}'} for k, n, c in PASOS]


def tablero(ver_terminados=False):
    etapas = etapas_activas()
    hay_ubicaciones = Ubicacion.objects.exists()
    todos = [x for x in (de_un_proyecto(p, etapas, hay_ubicaciones) for p in proyectos_listos()) if x]
    en_curso = [x for x in todos if x['en_curso']]
    # los que se movieron hace poco, arriba; los que nunca se tocaron, al final
    lista = sorted(todos if ver_terminados else en_curso,
                   key=lambda x: (x['ultima'] is None, -(x['ultima'].timestamp() if x['ultima'] else 0)))
    hoy = timezone.localdate()
    desde_hoy = timezone.make_aware(datetime.combine(hoy, time.min))
    marcas = Marca.objects.filter(deshecha_en__isnull=True, etapa__in=etapas)
    hoy_por_etapa = dict(marcas.filter(cuando__gte=desde_hoy).values_list('etapa').annotate(n=Count('pk')))
    semana_por_etapa = dict(marcas.filter(cuando__gte=desde_hoy - timedelta(days=6))
                            .values_list('etapa').annotate(n=Count('pk')))
    piezas_en_curso = sum(x['piezas'] for x in en_curso)
    # esperando: piezas que ya pasaron la etapa anterior y todavía no esta (donde se amontonan = cuello de botella)
    por_etapa, anterior = [], None
    for e in etapas:
        hechas = sum(x['por_etapa'][e.pk] for x in en_curso)
        por_etapa.append({'nombre': e.nombre, 'hechas': hechas, 'faltan': piezas_en_curso - hechas,
                          'esperando': max(0, anterior - hechas) if anterior is not None else 0,
                          'pct': pct(hechas, piezas_en_curso), 'hoy': hoy_por_etapa.get(e.pk, 0),
                          'semana': semana_por_etapa.get(e.pk, 0)})
        anterior = hechas
    vencidas = [t for t in Trabajo.objects.exclude(estado=Trabajo.Estado.INSTALADO).filter(limite__lt=hoy)
                if t.vencido(hoy)]
    return {
        'proyectos': lista, 'etapas': etapas, 'por_etapa': por_etapa,
        'en_curso': len(en_curso), 'terminados': len(todos) - len(en_curso),
        'pct': pct(sum(x['hechos'] for x in en_curso), sum(x['pasos'] for x in en_curso)),
        'piezas': piezas_en_curso, 'hoy': sum(hoy_por_etapa.values()), 'semana': sum(semana_por_etapa.values()),
        'vencidas': len(vencidas), 'hay_ubicaciones': hay_ubicaciones,
        'entrega': barra({k: sum(x['entrega'][ORDEN.index(k)]['n'] for x in en_curso) for k in ORDEN},
                         sum(x['muebles'] for x in en_curso)),
        'por_instalar': sum(x['muebles'] - x['instalados'] for x in en_curso),
        'cuello': max(por_etapa[1:], key=lambda e: e['esperando'], default=None) if piezas_en_curso else None,
    }
