"""Estado del pedido para el cliente final. Todavía no se muestra (ficha 13: "dejar listos los datos"): cuando se
sume al link del cliente, sale de acá y nunca con nombres de gente del taller ni números de mecanizado."""
from .calculo import avance
from .models import Bulto, Carga, Instalacion

EN_FABRICACION, LISTO, EN_CAMINO, ENTREGADO, INSTALADO = ('en_fabricacion', 'listo_para_entregar', 'en_camino',
                                                         'entregado', 'instalado')


def estado_del_pedido(proyecto):
    a = avance(proyecto)
    muebles = a['muebles']
    bultos = list(Bulto.objects.filter(proyecto=proyecto, fin__anulado_en__isnull=True))
    entregados = [b for b in bultos if b.estado == Bulto.Estado.ENTREGADO]
    todos_terminados = bool(muebles) and all(m['fin'] for m in muebles.values())
    instalados = set(Instalacion.objects.filter(proyecto=proyecto, anulado_en__isnull=True)
                     .values_list('mueble', flat=True))
    if muebles and all(n in instalados for n in muebles):
        etapa = INSTALADO
    elif todos_terminados and bultos and len(entregados) == len(bultos):
        etapa = ENTREGADO
    elif Carga.objects.filter(proyecto=proyecto, estado=Carga.Estado.SALIO).exists():
        etapa = EN_CAMINO
    elif todos_terminados:
        etapa = LISTO
    else:
        etapa = EN_FABRICACION
    return {
        'estado': etapa, 'avance': a['total']['pct'],
        'muebles': [{'nombre': n, 'avance': m['pct'], 'terminado': bool(m['fin']),
                     'bultos': len([b for b in bultos if b.mueble == n]),
                     'entregados': len([b for b in entregados if b.mueble == n]), 'instalado': n in instalados}
                    for n, m in sorted(muebles.items(), key=lambda kv: kv[0].lower())],
    }
