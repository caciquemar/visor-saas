"""La línea de comandos sigue funcionando como en el visor actual."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
MUESTRA = RAIZ / 'muestras' / 'Rack florencia'     # la más chica


@pytest.mark.muestras
def test_linea_de_comandos(tmp_path):
    args = [str(MUESTRA / 'Rack florencia.dxf'), str(MUESTRA / 'Rack florencia.ocp'), '-o', str(tmp_path)]
    for _ in range(2):      # la segunda vez el link del cliente tiene que ser el mismo
        p = subprocess.run([sys.executable, str(RAIZ / 'conversor' / 'polyboard_a_app.py'), *args,
                            '--url', 'https://visor.ejemplo'],
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
        assert p.returncode == 0, p.stderr
    mapa = json.loads((tmp_path / '.clientes.json').read_text(encoding='utf-8'))
    codigo = mapa['Rack florencia']
    assert f'Link para el cliente: https://visor.ejemplo/?c={codigo}' in p.stdout
    assert 'Proyecto: Rack florencia' in p.stdout
    indice = json.loads((tmp_path / 'index.json').read_text(encoding='utf-8'))
    assert [x['archivo'] for x in indice] == ['Rack florencia.json']
    assert (tmp_path / 'clientes' / f'{codigo}.json').exists()
    assert (tmp_path / 'clientes' / codigo / 'todo.glb').exists()


def test_como_modulo_muestra_la_ayuda():
    p = subprocess.run([sys.executable, '-m', 'conversor', '--help'], cwd=RAIZ,
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    assert p.returncode == 0 and 'ocp' in p.stdout
