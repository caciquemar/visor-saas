"""Ficha 06: módulos por taller y módulo Zicar.

Con el módulo apagado (o en otro taller) no se ve nada y las direcciones del módulo dan 404 aunque se arme el pedido a
mano. La conversión Zicar de verdad necesita el paquete `pb2zicar` (repo privado aparte, ver docs/decisiones.md): sin
él, esas pruebas se saltean. La conversión del visor se reemplaza con CorrerFalso (acá no importa)."""
import io
import zipfile

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from modulos import registro
from modulos.models import Modulo, TallerModulo
from modulos.zicar.models import ResultadoZicar
from modulos.zicar.modulo import Zicar
from proyectos import tareas
from proyectos.models import Original, Proyecto, Version
from talleres.separacion import OtroTaller, con_taller
from tests.app.ayudas import MUESTRAS, CorrerFalso, archivos

CARPETA = MUESTRAS / 'zicar' / 'Rack florencia v2'
hay_pb2zicar = pytest.mark.skipif(not Zicar().disponible(), reason='falta pb2zicar (pip install -e ..\\polyboard\\'
                                                                   'Polyboard_to_zicar)')


@pytest.fixture
def falso(monkeypatch):
    f = CorrerFalso()
    monkeypatch.setattr(tareas, 'correr', f)
    return f


@pytest.fixture
def con_post_que_encola(django_capture_on_commit_callbacks):
    """Envuelve client.post para que lo que se encola al confirmar se ejecute (Huey inmediato)."""
    def envolver(c):
        original = c.post

        def post(*args, **kwargs):
            with django_capture_on_commit_callbacks(execute=True):
                return original(*args, **kwargs)
        c.post = post
        return c
    return envolver


@pytest.fixture
def dueno_a(cliente_de, t, con_post_que_encola):
    return con_post_que_encola(cliente_de(t.dueno_a))


@pytest.fixture
def disponible(monkeypatch):
    """El módulo se puede prender aunque en esta PC no esté pb2zicar (las pruebas que convierten de verdad usan
    `hay_pb2zicar`)."""
    monkeypatch.setattr(Zicar, 'disponible', lambda self: True)


def prender(taller, prendido=True):
    with con_taller(taller):
        TallerModulo.objects.update_or_create(modulo=Modulo.objects.get(clave='zicar'),
                                              defaults={'prendido': prendido})


def zip_de(carpeta=CARPETA, raiz=True):
    """La carpeta del postprocesador comprimida (con la carpeta del proyecto adentro, o solo los materiales)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        for f in sorted(carpeta.rglob('*')):
            if f.is_file():
                relativo = f.relative_to(carpeta.parent if raiz else carpeta).as_posix()
                zf.writestr(relativo, f.read_bytes())
    return buf.getvalue()


def zip_con(nombres):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        for nombre, datos in nombres.items():
            zf.writestr(zipfile.ZipInfo(nombre), datos)
    return buf.getvalue()


def subir(cliente, slug='taller-a', zicar=None, nombre='rack'):
    datos = {'nombre': nombre, 'archivos': archivos()}
    if zicar is not None:
        datos['zicar'] = SimpleUploadedFile('Rack florencia v2.zip', zicar)
    return cliente.post(f'/{slug}/proyectos/nuevo/', datos)


def en(taller, funcion):
    with con_taller(taller):
        return funcion()


def proyecto_de(t):
    return en(t.A, lambda: Proyecto.objects.get())


def descarga(proyecto, numero=1, slug='taller-a'):
    return f'/{slug}/proyectos/{proyecto.pk}/versiones/{numero}/zicar/'


def contenido(respuesta):
    return b''.join(respuesta.streaming_content)


# ---------------------------------------------------------------- sin el módulo no se ve nada y todo da 404

def test_sin_modulo_la_subida_no_muestra_la_carpeta(dueno_a, t, disponible):
    r = dueno_a.get('/taller-a/proyectos/nuevo/')
    assert r.status_code == 200
    assert b'postprocesador' not in r.content and b'zicar' not in r.content.lower()


def test_sin_modulo_un_zip_armado_a_mano_se_ignora(dueno_a, t, falso, disponible):
    r = subir(dueno_a, zicar=zip_de())
    assert r.status_code == 302
    with con_taller(t.A):
        assert not Original.objects.filter(tipo=Original.Tipo.POSTPROCESADOR).exists()
        assert not ResultadoZicar.objects.exists()
    r = dueno_a.get(f'/taller-a/proyectos/{proyecto_de(t).pk}/')
    assert b'Zicar' not in r.content


def test_sin_modulo_la_descarga_da_404_aunque_exista_el_resultado(dueno_a, t, falso, disponible):
    prender(t.A)
    subir(dueno_a, zicar=zip_con({'Rack/mat/0001.dxf': b'0'}))
    p = proyecto_de(t)
    with con_taller(t.A):                       # el resultado existe y está listo...
        ResultadoZicar.objects.filter(version__proyecto=p).update(estado='listo', archivo='talleres/x.zip')
        zip_original = Original.objects.get(tipo=Original.Tipo.POSTPROCESADOR)
    prender(t.A, prendido=False)                # ...pero se apagó el módulo
    assert dueno_a.get(descarga(p)).status_code == 404
    pagina = dueno_a.get(f'/taller-a/proyectos/{p.pk}/').content
    assert b'Zicar' not in pagina and zip_original.nombre.encode() not in pagina
    original = f'/taller-a/proyectos/{p.pk}/versiones/1/originales/{zip_original.pk}/'
    assert dueno_a.get(original).status_code == 404


def test_modulo_de_otro_taller_no_vale(dueno_a, cliente_de, t, falso, disponible):
    prender(t.B)
    r = dueno_a.get('/taller-a/proyectos/nuevo/')
    assert b'postprocesador' not in r.content
    subir(dueno_a)
    assert dueno_a.get(descarga(proyecto_de(t))).status_code == 404


def test_modulo_no_disponible_en_el_servidor_no_aparece(dueno_a, t, monkeypatch):
    prender(t.A)
    monkeypatch.setattr(Zicar, 'disponible', lambda self: False)
    assert b'postprocesador' not in dueno_a.get('/taller-a/proyectos/nuevo/').content
    with con_taller(t.A):
        assert registro.activos() == []


def test_sin_taller_no_hay_modulos(db):
    assert registro.claves_prendidas() == set()


# ---------------------------------------------------------------- con el módulo prendido

def test_con_modulo_la_subida_muestra_la_carpeta(dueno_a, t, disponible):
    prender(t.A)
    r = dueno_a.get('/taller-a/proyectos/nuevo/')
    assert b'Carpeta del postprocesador' in r.content and b'webkitdirectory' in r.content


def test_la_carpeta_es_opcional(dueno_a, t, falso, disponible):
    prender(t.A)
    assert subir(dueno_a).status_code == 302
    with con_taller(t.A):
        assert not ResultadoZicar.objects.exists()


@pytest.mark.parametrize('datos,error', [
    (zip_con({'../afuera.dxf': b'0'}), 'rutas raras'),
    (zip_con({'/raiz/0001.dxf': b'0'}), 'rutas raras'),
    (zip_con({'C:/x/0001.dxf': b'0'}), 'rutas raras'),
    (zip_con({'Rack/PP_Report.txt': b'hola'}), 'No hay ningún DXF'),
    (b'esto no es un zip', 'no es un ZIP'),
])
def test_carpeta_rechazada_con_mensaje(dueno_a, t, falso, disponible, datos, error):
    prender(t.A)
    r = subir(dueno_a, zicar=datos)
    assert r.status_code == 400
    assert error in r.content.decode()
    with con_taller(t.A):
        assert not Proyecto.objects.exists()


def test_carpeta_demasiado_grande(dueno_a, t, falso, disponible, settings):
    prender(t.A)
    settings.MAX_ZICAR_MB = 0
    r = subir(dueno_a, zicar=zip_de())
    assert r.status_code == 400 and 'el máximo es 0 MB' in r.content.decode()


def test_armador_no_descarga(cliente_de, t, dueno_a, falso, disponible):
    prender(t.A)
    subir(dueno_a, zicar=zip_con({'Rack/mat/0001.dxf': b'0'}))
    p = proyecto_de(t)
    armador = cliente_de(t.armador_a)
    assert armador.get(descarga(p)).status_code == 403
    assert b'Zicar' not in armador.get(f'/taller-a/proyectos/{p.pk}/').content
    prender(t.A, prendido=False)
    assert armador.get(descarga(p)).status_code == 404       # apagado: 404 antes que el rol


@hay_pb2zicar
def test_carpeta_que_no_convierte_ninguna_pieza_queda_en_error(dueno_a, t, falso):
    prender(t.A)
    subir(dueno_a, zicar=zip_con({'Rack/mat/0001.dxf': b'  0\nEOF\n'}))
    with con_taller(t.A):
        r = ResultadoZicar.objects.get()
    assert r.estado == 'error' and 'ninguna pieza' in r.mensaje
    assert 'no se pudo convertir' in dueno_a.get(f'/taller-a/proyectos/{proyecto_de(t).pk}/').content.decode()


# ---------------------------------------------------------------- conversión de verdad (pb2zicar)

def esperado(carpeta, tmp_path):
    """Lo que genera hoy "Convertir proyecto" en la PC: pb2zicar sobre la carpeta -> {ruta: bytes}."""
    from pb2zicar.cli import process_folder
    salida = tmp_path / 'esperado'
    process_folder(carpeta, salida)
    return {f.relative_to(salida).as_posix(): f.read_bytes() for f in salida.rglob('*') if f.is_file()}


@hay_pb2zicar
@pytest.mark.parametrize('raiz', [True, False], ids=['con carpeta del proyecto', 'solo materiales'])
def test_zip_descargado_igual_a_pb2zicar(dueno_a, t, falso, tmp_path, raiz):
    prender(t.A)
    assert subir(dueno_a, zicar=zip_de(raiz=raiz), nombre='Rack florencia').status_code == 302
    p = proyecto_de(t)
    with con_taller(t.A):
        r = ResultadoZicar.objects.get()
    assert r.estado == 'listo', r.mensaje
    base = 'Rack florencia v2_zicar' if raiz else 'Rack florencia_zicar'
    assert r.nombre == f'{base}.zip'

    pagina = dueno_a.get(f'/taller-a/proyectos/{p.pk}/').content.decode()
    assert 'Descargar Zicar' in pagina and f'{r.piezas} piezas convertidas' in pagina

    respuesta = dueno_a.get(descarga(p))
    assert respuesta.status_code == 200
    assert f'filename="{base}.zip"' in respuesta['Content-Disposition']
    with zipfile.ZipFile(io.BytesIO(contenido(respuesta))) as zf:
        bajado = {n: zf.read(n) for n in zf.namelist()}
    quiere = esperado(CARPETA, tmp_path)
    assert len(quiere) == r.piezas == len(list(CARPETA.rglob('*.dxf')))
    assert bajado == {f'{base}/{n}': datos for n, datos in quiere.items()}


@hay_pb2zicar
def test_volver_a_convertir_genera_zicar_de_nuevo(dueno_a, t, falso):
    prender(t.A)
    subir(dueno_a, zicar=zip_de())
    p = proyecto_de(t)
    dueno_a.post(f'/taller-a/proyectos/{p.pk}/versiones/1/reconvertir/')
    with con_taller(t.A):
        v2 = Version.objects.get(numero=2)
        assert v2.originales.filter(tipo=Original.Tipo.POSTPROCESADOR).exists()
        assert ResultadoZicar.objects.get(version=v2).estado == 'listo'
    assert dueno_a.get(descarga(p, numero=2)).status_code == 200


@hay_pb2zicar
def test_la_carpeta_no_va_al_conversor_del_visor(dueno_a, t, falso):
    prender(t.A)
    subir(dueno_a, zicar=zip_de())
    assert falso.llamadas[0]['originales'] == ['cocina prueba.dxf', 'cocina prueba.ocp']


# ---------------------------------------------------------------- separación entre talleres

def test_modulos_de_un_taller_no_se_ven_ni_se_tocan_desde_otro(t):
    prender(t.B)
    with con_taller(t.A):
        assert not TallerModulo.objects.exists()
        assert registro.claves_prendidas() == set()
    with con_taller(t.B):
        tm = TallerModulo.objects.get()
    with con_taller(t.A), pytest.raises(OtroTaller):
        tm.prendido = False
        tm.save()


@hay_pb2zicar
def test_resultado_zicar_de_otro_taller_da_404(dueno_a, cliente_de, t, falso, con_post_que_encola):
    prender(t.A)
    prender(t.B)
    subir(dueno_a, zicar=zip_de())
    p = proyecto_de(t)
    beto = con_post_que_encola(cliente_de(t.dueno_b))
    assert beto.get(descarga(p)).status_code == 404                      # taller ajeno
    assert beto.get(descarga(p, slug='taller-b')).status_code == 404     # su taller, id de A
    with con_taller(t.B):
        assert not ResultadoZicar.objects.exists()


# ---------------------------------------------------------------- administración

def campos_del_formulario(html):
    """name -> value de los input y select del formulario de la administración (lo que mandaría el navegador)."""
    import re
    campos = {}
    for m in re.finditer(r'<input[^>]*>', html):
        tag = m.group(0)
        nombre, valor = re.search(r'name="([^"]+)"', tag), re.search(r'value="([^"]*)"', tag)
        tipo = re.search(r'type="([^"]+)"', tag)
        if not nombre or (tipo and tipo.group(1) in ('checkbox', 'submit', 'file')):
            if nombre and tipo and tipo.group(1) == 'checkbox' and 'checked' in tag:
                campos[nombre.group(1)] = 'on'
            continue
        campos[nombre.group(1)] = valor.group(1) if valor else ''
    for m in re.finditer(r'<select[^>]*name="([^"]+)"[^>]*>(.*?)</select>', html, re.S):
        elegida = re.search(r'<option value="([^"]*)"[^>]*selected', m.group(2))
        campos[m.group(1)] = elegida.group(1) if elegida else ''
    return campos


def test_prender_zicar_desde_la_ficha_del_taller(client, t, django_user_model):
    admin = django_user_model.objects.create_superuser('admin@servicio.com', 'una-clave-larga-de-prueba')
    client.force_login(admin)
    url = f'/admin/talleres/taller/{t.A.pk}/change/'
    html = client.get(url).content.decode()
    assert 'Módulos' in html or 'módulos' in html
    campos = campos_del_formulario(html)
    prefijo = next(k.removesuffix('-TOTAL_FORMS') for k in campos           # el del inline de módulos
                   if k.endswith('-TOTAL_FORMS') and f"{k.removesuffix('-TOTAL_FORMS')}-__prefix__-modulo" in campos)
    campos[f'{prefijo}-TOTAL_FORMS'] = '1'
    campos[f'{prefijo}-0-modulo'] = str(Modulo.objects.get(clave='zicar').pk)
    campos[f'{prefijo}-0-prendido'] = 'on'
    campos[f'{prefijo}-0-configuracion'] = '{}'
    campos = {k: v for k, v in campos.items() if '__prefix__' not in k}
    r = client.post(url, campos)
    assert r.status_code == 302, r.content.decode()[:3000]
    with con_taller(t.A):
        assert TallerModulo.objects.get().prendido
    with con_taller(t.B):
        assert not TallerModulo.objects.exists()
