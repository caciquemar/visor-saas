"""Los errores llegan como ErrorConversion con un mensaje para el taller, nunca como SystemExit."""
import bz2
from pathlib import Path

import ezdxf
import pytest

from conversor import ErrorConversion, convertir
from conversor.polyboard_a_app import main

MUESTRA = Path(__file__).resolve().parents[2] / 'muestras' / 'Kogan'
OCP = MUESTRA / 'Kogan.ocp'


def dxf_vacio(ruta):
    ezdxf.new().saveas(ruta)
    return ruta


def test_ocp_inexistente(tmp_path):
    with pytest.raises(ErrorConversion, match='No se encontró el archivo de OptiCut falta.ocp'):
        convertir(tmp_path / 'x.dxf', tmp_path / 'falta.ocp', tmp_path)


def test_ocp_que_no_es_de_opticut(tmp_path):
    ocp = tmp_path / 'roto.ocp'
    ocp.write_bytes(b'esto no es un ocp')
    with pytest.raises(ErrorConversion, match='no parece una lista de OptiCut'):
        convertir(tmp_path / 'x.dxf', ocp, tmp_path)


def test_ocp_con_bloque_comprimido_danado(tmp_path):
    ocp = tmp_path / 'danado.ocp'
    ocp.write_bytes(OCP.read_bytes()[:300])
    with pytest.raises(ErrorConversion, match='no parece una lista de OptiCut'):
        convertir(tmp_path / 'x.dxf', ocp, tmp_path)


def test_ocp_sin_piezas(tmp_path):
    ocp = tmp_path / 'vacio.ocp'
    ocp.write_bytes(b'bo:oc:document:panel' + bz2.compress(b'\0' * 200))
    with pytest.raises(ErrorConversion, match='no tiene piezas'):
        convertir(tmp_path / 'x.dxf', ocp, tmp_path)


def test_sin_ocp(tmp_path):
    with pytest.raises(ErrorConversion, match='Falta la lista de OptiCut'):
        convertir(tmp_path / 'x.dxf', [], tmp_path)


def test_dxf_inexistente(tmp_path):
    with pytest.raises(ErrorConversion, match='No se encontró el archivo 3D falta.dxf'):
        convertir(tmp_path / 'falta.dxf', OCP, tmp_path)


def test_dxf_que_no_es_dxf(tmp_path):
    dxf = tmp_path / 'roto.dxf'
    dxf.write_text('hola, no soy un DXF', encoding='utf-8')
    with pytest.raises(ErrorConversion) as error:
        convertir(dxf, OCP, tmp_path)
    # claro para cualquiera: sin el texto técnico de ezdxf
    assert str(error.value) == ('No se pudo abrir roto.dxf: el archivo está dañado o no es un DXF. '
                                'Exportá de nuevo el proyecto desde Polyboard como DXF 3D.')


def test_dxf_sin_muebles(tmp_path):
    with pytest.raises(ErrorConversion, match='no tiene muebles'):
        convertir(dxf_vacio(tmp_path / 'plano.dxf'), OCP, tmp_path)


def test_linea_de_comandos_sale_con_1_y_mensaje(tmp_path, capsys):
    assert main([str(dxf_vacio(tmp_path / 'plano.dxf')), str(OCP), '-o', str(tmp_path)]) == 1
    assert 'ERROR: plano.dxf no tiene muebles' in capsys.readouterr().err
