"""Cuánto falta: avance por mueble y por proyecto, piezas nuevas de una versión, y qué pieza o bulto es lo que se
leyó en el puesto (QR propio o número de mecanizado de OptiCut).

Porcentaje (decisión de Martín, 2026-10-11): promedio de etapas. Cada pieza en cada etapa activa es un paso;
% = pasos hechos / pasos. Las marcas de piezas que ya no están en la versión actual no cuentan."""
import re
from collections import defaultdict
from urllib.parse import urlsplit

from etiquetas import claves
from etiquetas.datos import proyecto_de, version_actual
from etiquetas.models import Etiqueta, huella
from proyectos.models import Version

from .models import FinDeMueble, Marca, etapas_activas, Ubicado

CODIGO = re.compile(r'^[2-9A-HJ-NP-Z]{8}$', re.I)          # como etiquetas.models.ALFABETO, 8 caracteres


def pct(hechos, total):
    return hechos * 100 // total if total else 0       # para abajo: 100 % solo con todo hecho


def piezas_de(proyecto):
    """Las piezas con etiqueta de la versión actual, cada una con su huella; [] si no hay versión lista."""
    v = version_actual(proyecto)
    if v is None:
        return []
    salida = []
    for x in claves.piezas(proyecto_de(v)):
        salida.append({**x, 'huella': huella(x['clave'])})
    return salida


def marcas_vigentes(proyecto, etapas=None):
    q = Marca.objects.filter(proyecto=proyecto, deshecha_en__isnull=True)
    if etapas is not None:
        q = q.filter(etapa__in=etapas)
    return q


def avance(proyecto, piezas=None):
    """{etapas, total, muebles, paneles, sueltas}. `muebles[nombre]` = {piezas, pasos, hechos, pct, por_etapa,
    fin}; `paneles[id del panel]` = ids de las etapas hechas; `sueltas` = marcas de piezas que ya no están."""
    etapas = etapas_activas()
    piezas = piezas_de(proyecto) if piezas is None else piezas
    hechas = defaultdict(set)                            # huella -> ids de etapas
    for h, e in marcas_vigentes(proyecto, etapas).values_list('huella', 'etapa_id'):
        hechas[h].add(e)
    fines = {f.mueble: f for f in FinDeMueble.objects.filter(proyecto=proyecto, anulado_en__isnull=True)
             .select_related('por')}
    muebles, paneles = {}, {}
    total = {'piezas': 0, 'pasos': 0, 'hechos': 0, 'por_etapa': {e.pk: 0 for e in etapas}}
    presentes = set()
    for x in piezas:
        presentes.add(x['huella'])
        nombre = x['panel']['mueble']
        m = muebles.setdefault(nombre, {'piezas': 0, 'pasos': 0, 'hechos': 0,
                                        'por_etapa': {e.pk: 0 for e in etapas}})
        hechas_x = hechas.get(x['huella'], set())
        paneles[x['panel']['id']] = sorted(hechas_x)
        for d in (m, total):
            d['piezas'] += 1
            d['pasos'] += len(etapas)
            d['hechos'] += len(hechas_x)
            for e in hechas_x:
                d['por_etapa'][e] += 1
    for nombre, m in muebles.items():
        m['pct'] = pct(m['hechos'], m['pasos'])
        m['fin'] = fines.get(nombre)
    total['pct'] = pct(total['hechos'], total['pasos'])
    total['terminados'] = sum(1 for m in muebles.values() if m['fin'])
    return {'etapas': etapas, 'total': total, 'muebles': muebles, 'paneles': paneles,
            'sueltas': sum(1 for h in hechas if h not in presentes)}


def ubicaciones(proyecto):
    """Dónde está cada pieza (por huella) y cada bulto (por id): su último `Ubicado` vigente. Las piezas o bultos
    que salieron del taller (ubicación vacía) no aparecen."""
    piezas, bultos = {}, {}
    for u in (Ubicado.objects.filter(proyecto=proyecto, deshecho_en__isnull=True)
              .select_related('ubicacion', 'por').order_by('cuando', 'pk')):
        if u.bulto_id:
            bultos[u.bulto_id] = u
        elif u.huella:
            piezas[u.huella] = u
    return ({h: u for h, u in piezas.items() if u.ubicacion_id},
            {b: u for b, u in bultos.items() if u.ubicacion_id})


def faltan_en(proyecto, mueble, etapa, piezas=None):
    """Las piezas del mueble que todavía no pasaron por esa etapa."""
    piezas = piezas_de(proyecto) if piezas is None else piezas
    hechas = set(marcas_vigentes(proyecto, [etapa]).filter(mueble=mueble).values_list('huella', flat=True))
    return [x for x in piezas if x['panel']['mueble'] == mueble and x['huella'] not in hechas]


def anterior(proyecto):
    """La versión lista anterior a la actual (por número)."""
    v = version_actual(proyecto)
    if v is None:
        return None
    return (proyecto.versiones.filter(estado=Version.Estado.LISTO, numero__lt=v.numero)
            .exclude(archivo_proyecto='').order_by('-numero').first())


def piezas_nuevas(proyecto, piezas=None):
    """Piezas de la versión actual que no estaban en la anterior, solo si el proyecto ya tiene avance (si no, no
    hay nada que avisar)."""
    if not marcas_vigentes(proyecto).exists():
        return []
    previa = anterior(proyecto)
    if previa is None:
        return []
    antes = {huella(x['clave']) for x in claves.piezas(proyecto_de(previa))}
    piezas = piezas_de(proyecto) if piezas is None else piezas
    return [x for x in piezas if x['huella'] not in antes]


# ---------------------------------------------------------------- qué se leyó

def numero(texto):
    """El número de mecanizado como lo normaliza el visor: el último grupo de cifras, sin ceros adelante."""
    m = re.findall(r'\d+', str(texto))
    return str(int(m[-1])) if m else ''


def leer(texto, slug):
    """{'codigo', 'bulto'} si es una etiqueta propia (QR o código escrito), {'ajena': True} si es el QR de otro
    taller, {'numero'} si es un número de mecanizado, o None."""
    texto = str(texto).strip()
    if CODIGO.match(texto) and re.search(r'[a-z]', texto, re.I):
        return {'codigo': texto.upper(), 'bulto': None}
    partes = urlsplit(texto)
    if partes.scheme in ('http', 'https'):
        m = re.fullmatch(r'/([^/]+)/e/([^/]+?)(?:/(\d+))?/?', partes.path)
        if not m:
            return None
        if m[1] != slug:
            return {'ajena': True}
        return {'codigo': m[2].upper(), 'bulto': int(m[3]) if m[3] else None}
    n = numero(texto)
    return {'numero': n} if n else None


def etiqueta_de(codigo):
    return Etiqueta.objects.select_related('proyecto__version_actual').filter(codigo=codigo).first()
