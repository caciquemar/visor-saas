from talleres.models import Membresia
from talleres.pin import asignar_pin
from talleres.separacion import con_taller

CLAVE = 'una-clave-larga-de-prueba'


def sumar(usuario, taller, rol, pin=None):
    """Suma al usuario al taller con ese rol (y PIN, si se da)."""
    with con_taller(taller):
        m = Membresia.objects.create(usuario=usuario, rol=rol)
        if pin:
            asignar_pin(m, pin)
    return m


# ---------------------------------------------------------------- proyectos

import json  # noqa: E402
from pathlib import Path  # noqa: E402

from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402

MUESTRAS = Path(__file__).resolve().parents[2] / 'muestras'
DXF_SIN_MUEBLES = b'  0\r\nSECTION\r\n  2\r\nHEADER\r\n  0\r\nENDSEC\r\n  0\r\nEOF\r\n'
DXF_ROTO = b'  0\r\nSECTION\r\n  2\r\nENTITIES\r\n esto no es un DXF \x00\xff\x00'


def ocp_real():
    return (MUESTRAS / 'Kogan' / 'Kogan.ocp').read_bytes()


def archivos(dxf=DXF_SIN_MUEBLES, ocp=None, nombre='cocina prueba'):
    """Lo que manda el navegador: un DXF y un .ocp."""
    return [SimpleUploadedFile(f'{nombre}.dxf', dxf), SimpleUploadedFile(f'{nombre}.ocp', ocp or ocp_real())]


def subir(cliente, slug, nombre='', lista=None):
    return cliente.post(f'/{slug}/proyectos/nuevo/', {'nombre': nombre, 'archivos': lista or archivos()})


class CorrerFalso:
    """Reemplaza proyectos.tareas.correr: no lanza el conversor, deja un resultado mínimo y guarda lo que recibió
    (la entrada, el materiales.json y las imágenes de Textures) para revisarlo."""

    def __init__(self, con_imagen=None, avisos=None):
        self.con_imagen = con_imagen or {}
        self.avisos = avisos or []
        self.llamadas = []

    def __call__(self, entrada, tmp):
        destino = Path(entrada['destino'])
        mj = destino / 'materiales.json'
        self.llamadas.append(dict(
            entrada=entrada,
            materiales=json.loads(mj.read_text(encoding='utf-8')) if mj.exists() else {},
            texturas=sorted(f.name for f in Path(entrada['texturas'][0]).iterdir()),
            originales=sorted(f.name for f in (tmp / 'originales').iterdir()),
        ))
        (destino / 'Falso.json').write_text('{"proyecto": "Falso"}', encoding='utf-8')
        (destino / 'clientes').mkdir(exist_ok=True)
        (destino / 'clientes' / f"{entrada['codigo']}.json").write_text('{}', encoding='utf-8')
        resumen = dict(piezas_ocp=2, paneles=3, con_mecanizado=2, piezas_con_numero=2, vinculados=2, taladros=0,
                       herrajes=0, muros=0)
        return dict(proyecto='Falso', archivo='Falso.json', avisos=list(self.avisos), resumen=resumen,
                    con_imagen=self.con_imagen)
