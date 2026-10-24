"""Lo que una etiqueta necesita del proyecto convertido: leer proyecto.json de la versión actual y encontrar ahí la
pieza o el mueble de una etiqueta."""
import json
from functools import lru_cache

from django.core.files.storage import default_storage

from talleres.archivos import ruta_valida
from talleres.separacion import taller_o_error

from . import claves

# lo que hace falta para etiquetas y para encontrar la pieza (sin la geometría, que es lo pesado)
CAMPOS = ('id', 'num', 'pieza', 'nombre', 'mueble', 'cant', 'med', 'mat', 'vt')


@lru_cache(maxsize=8)
def _leer(ruta, marca):
    with default_storage.open(ruta, 'rb') as f:
        d = json.load(f)
    paneles = []
    for p in d.get('paneles', []):
        q = {k: p[k] for k in CAMPOS if k in p}
        q['cantos'] = [{k: c[k] for k in ('mat', 'lado', 'pos', 'largo') if k in c} for c in p.get('cantos', [])]
        t = p.get('t') or []
        if len(t) >= 9:                  # la caja de la pieza (lo único de la geometría que usa el esquema del mueble)
            q['caja'] = [min(t[0::3]), min(t[1::3]), min(t[2::3]), max(t[0::3]), max(t[1::3]), max(t[2::3])]
        paneles.append(q)
    return {'proyecto': d.get('proyecto', ''), 'paneles': paneles}


def proyecto_de(version):
    """proyecto.json (liviano) de una versión lista del taller actual. `marca`: si la versión se vuelve a convertir
    en el mismo lugar, cambia `terminada` y no se usa lo leído antes."""
    ruta = ruta_valida(taller_o_error(), version.archivo_proyecto)
    if ruta is None:
        raise FileNotFoundError(version.archivo_proyecto)
    return _leer(ruta, (version.pk, version.terminada.isoformat() if version.terminada else ''))


def version_actual(proyecto):
    v = proyecto.version_actual
    if v is None or v.estado != v.Estado.LISTO or not v.archivo_proyecto:
        return None
    return v


def resolver(etiqueta):
    """Qué abre la etiqueta en la versión actual: {'panel': id del panel} para una pieza, {'mueble': nombre} para un
    mueble, o None si ya no está (o el proyecto no tiene versión lista)."""
    v = version_actual(etiqueta.proyecto)
    if v is None:
        return None
    d = proyecto_de(v)
    if etiqueta.tipo == 'pieza':
        x = claves.buscar_pieza(d, etiqueta.clave)
        return {'panel': x['panel']['id'], 'copia': x['copia'], 'de': x['de']} if x else None
    nombre = etiqueta.clave.get('mueble')
    return {'mueble': nombre} if nombre in claves.muebles(d) else None
