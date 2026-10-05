"""Convierte cada proyecto de muestras/ y lo compara con el resultado guardado en esperado/.

Si un cambio del conversor modifica el resultado a propósito:
    pytest -m muestras --actualizar-esperados
y revisar con git diff los resumen.json que cambiaron antes de hacer commit.
"""
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest

from conversor import convertir

MUESTRAS = Path(__file__).resolve().parents[2] / 'muestras'
CODIGO = 'muestra'      # código de cliente fijo: el resultado tiene que ser siempre el mismo


def carpetas():
    return sorted(c for c in MUESTRAS.iterdir() if c.is_dir() and any(c.glob('*.dxf')))


def resumen_de(r, destino):
    """Lo que se revisa a mano: cuentas, materiales, avisos y las huellas de los modelos de AR."""
    datos = json.loads(r.archivo.read_text(encoding='utf-8'))
    return dict(
        proyecto=r.proyecto,
        **r.resumen,
        paneles_por_mueble=dict(sorted(Counter(p['mueble'] for p in datos['paneles']).items())),
        materiales=sorted({p['mat'] for p in datos['paneles']} | {c['mat'] for p in datos['paneles']
                                                                   for c in p['cantos'] if c['mat']}),
        avisos=r.avisos,
        glb={f.name: hashlib.sha256(f.read_bytes()).hexdigest()
             for f in sorted((destino / 'clientes' / CODIGO).glob('*.glb'))},
    )


def guardar_gz(ruta, texto):
    # mtime=0: el mismo contenido da el mismo archivo y git no ve cambios
    with open(ruta, 'wb') as f, gzip.GzipFile(fileobj=f, mode='wb', mtime=0) as gz:
        gz.write(texto.encode('utf-8'))


@pytest.mark.muestras
@pytest.mark.parametrize('carpeta', carpetas(), ids=lambda c: c.name)
def test_muestra(carpeta, tmp_path, request):
    dxf = next(carpeta.glob('*.dxf'))
    ocps = sorted(carpeta.glob('*.ocp'))
    r = convertir(dxf, ocps, tmp_path, codigo=CODIGO)

    resumen = json.dumps(resumen_de(r, tmp_path), ensure_ascii=False, indent=1)
    proyecto = r.archivo.read_text(encoding='utf-8')
    cliente = (tmp_path / 'clientes' / f'{CODIGO}.json').read_text(encoding='utf-8')

    esperado = carpeta / 'esperado'
    if request.config.getoption('--actualizar-esperados'):
        esperado.mkdir(exist_ok=True)
        (esperado / 'resumen.json').write_text(resumen + '\n', encoding='utf-8')
        guardar_gz(esperado / 'proyecto.json.gz', proyecto)
        guardar_gz(esperado / 'cliente.json.gz', cliente)
        return
    if not (esperado / 'resumen.json').exists():
        pytest.fail(f'{carpeta.name} no tiene resultado guardado. Generarlo con: '
                    'pytest -m muestras --actualizar-esperados  (y revisar esperado/resumen.json)')

    # primero el resumen: si cambió, la diferencia se lee fácil
    assert json.loads(resumen) == json.loads((esperado / 'resumen.json').read_text(encoding='utf-8'))
    assert proyecto == gzip.decompress((esperado / 'proyecto.json.gz').read_bytes()).decode('utf-8'), \
        'cambió la versión del taller (proyecto.json) aunque el resumen sea igual'
    assert cliente == gzip.decompress((esperado / 'cliente.json.gz').read_bytes()).decode('utf-8'), \
        'cambió la versión del cliente (cliente.json) aunque el resumen sea igual'


def test_hay_muestras_de_los_dos_opticut():
    """La ficha pide al menos 3 muestras, con OptiCut viejo y nuevo."""
    from conversor.polyboard_a_app import descomprimir
    versiones = set()
    for c in carpetas():
        d = descomprimir(next(c.glob('*.ocp')))
        versiones.add('vieja' if d.count(b'\x06' + b'\x00' * 7) > d.count(b'\x07' + b'\x00' * 7) else 'nueva')
    assert len(carpetas()) >= 3
    assert versiones == {'vieja', 'nueva'}
