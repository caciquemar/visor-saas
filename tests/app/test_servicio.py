"""Lo que necesita el servicio en el servidor (ficha 07a): /salud/, IP detrás de Cloudflare, copias de la base."""
import time
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import RequestFactory

from proyectos.proceso import memoria_usada
from servicio import copias
from servicio.tareas import latido
from talleres.vistas import ip_de


# ---------------------------------------------------------------- /salud/

def test_salud_sin_sesion_con_la_cola_inmediata(client, db):
    r = client.get('/salud/')
    assert r.status_code == 200 and r.content == b'ok'


def test_salud_avisa_si_la_cola_no_late(client, db, settings):
    settings.HUEY = {**settings.HUEY, 'immediate': False}
    r = client.get('/salud/')
    assert r.status_code == 503 and b'cola' in r.content
    latido.call_local()
    assert client.get('/salud/').status_code == 200


def test_salud_avisa_si_el_latido_es_viejo(client, db, settings):
    from django.core.cache import cache
    settings.HUEY = {**settings.HUEY, 'immediate': False}
    cache.set('latido-cola', time.time() - 11 * 60)
    assert client.get('/salud/').status_code == 503


def test_salud_avisa_si_no_anda_la_base(client, db, monkeypatch):
    from talleres.models import Taller

    def rota(*a, **k):
        raise RuntimeError('sin base')
    monkeypatch.setattr(Taller.objects, 'exists', rota)
    r = client.get('/salud/')
    assert r.status_code == 503 and b'base' in r.content


def test_salud_no_es_un_taller(db):
    from django.core.exceptions import ValidationError

    from talleres.models import validar_slug_de_taller
    with pytest.raises(ValidationError):
        validar_slug_de_taller('salud')


# ---------------------------------------------------------------- IP detrás de Cloudflare

def test_ip_de_cloudflare_solo_si_esta_detras(settings):
    pedido = RequestFactory().get('/', REMOTE_ADDR='172.18.0.5', HTTP_CF_CONNECTING_IP='200.1.2.3')
    settings.DETRAS_DE_CLOUDFLARE = False
    assert ip_de(pedido) == '172.18.0.5'          # sin Cloudflare adelante el encabezado se puede inventar
    settings.DETRAS_DE_CLOUDFLARE = True
    assert ip_de(pedido) == '200.1.2.3'
    assert ip_de(RequestFactory().get('/', REMOTE_ADDR='172.18.0.5')) == '172.18.0.5'


# ---------------------------------------------------------------- copias

@pytest.fixture
def copias_en_carpeta(settings, tmp_path, monkeypatch):
    """Copias en una carpeta temporal y pg_dump de mentira (escribe un archivo con el nombre de la base)."""
    settings.STORAGES = {**settings.STORAGES, 'copias': {      # Django rehace los almacenamientos al cambiarlo
        'BACKEND': 'django.core.files.storage.FileSystemStorage', 'OPTIONS': {'location': tmp_path / 'copias'}}}
    llamadas = []

    def correr(comando, entorno):
        llamadas.append(comando)
        if comando[0] == 'pg_dump':
            Path(comando[comando.index('--file') + 1]).write_bytes(b'copia de visor')
        return ''
    monkeypatch.setattr(copias, 'conexion', lambda: ('visor', {}))
    monkeypatch.setattr(copias, 'correr', correr)
    return llamadas


def fecha(texto):
    from datetime import datetime

    from django.utils import timezone
    return timezone.make_aware(datetime.fromisoformat(texto))


def test_copia_diaria_y_la_primera_del_mes(copias_en_carpeta):
    assert copias.hacer_copia(fecha('2026-10-08 04:00')) == ['diarias/visor-2026-10-08-0400.dump',
                                                              'mensuales/visor-2026-10-08-0400.dump']
    assert copias.hacer_copia(fecha('2026-10-09 04:00')) == ['diarias/visor-2026-10-09-0400.dump']
    assert copias.listar('diarias') == ['visor-2026-10-08-0400.dump', 'visor-2026-10-09-0400.dump']
    dump = copias_en_carpeta[0]
    assert dump[0] == 'pg_dump' and '--enable-row-security' in dump and '--inserts' in dump
    assert copias.almacen().open('diarias/visor-2026-10-09-0400.dump').read() == b'copia de visor'


def test_copias_viejas_se_borran(copias_en_carpeta, settings):
    settings.COPIAS_DIARIAS, settings.COPIAS_MENSUALES = 3, 2
    for dia in range(1, 6):
        copias.hacer_copia(fecha(f'2026-10-0{dia} 04:00'))
    copias.hacer_copia(fecha('2026-11-01 04:00'))
    copias.hacer_copia(fecha('2026-12-01 04:00'))
    assert copias.listar('diarias') == ['visor-2026-10-05-0400.dump', 'visor-2026-11-01-0400.dump',
                                        'visor-2026-12-01-0400.dump']
    assert copias.listar('mensuales') == ['visor-2026-11-01-0400.dump', 'visor-2026-12-01-0400.dump']


def test_copias_solo_con_postgres(settings):
    if settings.DATABASES['default']['ENGINE'].endswith('postgresql'):
        pytest.skip('con PostgreSQL sí hay copia')
    with pytest.raises(copias.ErrorCopia):
        copias.conexion()                       # en las pruebas rápidas la base es SQLite


def test_restaurar_pide_confirmacion(copias_en_carpeta):
    copias.hacer_copia(fecha('2026-10-08 04:00'))
    with pytest.raises(CommandError, match='--si'):
        call_command('restaurar_copia', 'diarias/visor-2026-10-08-0400.dump')
    assert [c[0] for c in copias_en_carpeta] == ['pg_dump']       # no se tocó la base


def test_restaurar_en_base_aparte_no_borra_nada(copias_en_carpeta, monkeypatch, capsys):
    monkeypatch.setattr(copias, 'contar', lambda base, entorno: {'talleres_taller': 2})
    copias.hacer_copia(fecha('2026-10-08 04:00'))
    call_command('restaurar_copia', 'diarias/visor-2026-10-08-0400.dump', '--base', 'prueba_copia')
    createdb, restore = copias_en_carpeta[1:]
    assert createdb[0] == 'createdb' and createdb[-1] == 'prueba_copia'
    assert restore[0] == 'pg_restore' and '--clean' not in restore
    assert restore[restore.index('--dbname') + 1] == 'prueba_copia'
    assert 'talleres_taller' in capsys.readouterr().out


def test_borrar_base_de_prueba_pero_nunca_la_de_la_app(copias_en_carpeta):
    call_command('restaurar_copia', '--borrar-base', 'prueba_copia')
    assert copias_en_carpeta[-1][0] == 'dropdb' and copias_en_carpeta[-1][-1] == 'prueba_copia'
    with pytest.raises(CommandError, match='no se borra'):
        call_command('restaurar_copia', '--borrar-base', 'visor')
    assert len(copias_en_carpeta) == 1


def test_restaurar_lista_las_copias(copias_en_carpeta, capsys):
    copias.hacer_copia(fecha('2026-10-08 04:00'))
    call_command('restaurar_copia')
    salida = capsys.readouterr().out.split()
    assert salida == ['diarias/visor-2026-10-08-0400.dump', 'mensuales/visor-2026-10-08-0400.dump']


# ---------------------------------------------------------------- memoria de la conversión

def test_memoria_usada_en_linux_o_nada():
    m = memoria_usada()
    if Path('/proc/self/status').exists():
        assert m['real'] > 0 and m['reservada'] >= m['real']
    else:
        assert m is None


# ---------------------------------------------------------------- copia de verdad (PostgreSQL)

@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
def test_copia_y_restauracion_de_verdad(settings, tmp_path, django_user_model):
    """pg_dump y pg_restore de verdad, con row-level security y el usuario común de la app."""
    import shutil
    import subprocess

    from talleres.models import Taller
    from talleres.separacion import con_taller
    from tests.app.taller_prueba.models import Nota
    if not settings.DATABASES['default']['ENGINE'].endswith('postgresql') or not shutil.which('pg_dump'):
        pytest.skip('necesita PostgreSQL y pg_dump')
    settings.STORAGES = {**settings.STORAGES, 'copias': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage', 'OPTIONS': {'location': tmp_path / 'copias'}}}
    taller = Taller.objects.create(nombre='Taller A', slug='taller-a')
    django_user_model.objects.create_user('dueno@a.com', 'una-clave-larga')
    with con_taller(taller):
        Nota.objects.bulk_create([Nota(texto=f'nota {i}') for i in range(700)])   # más de un INSERT por tabla

    guardadas = copias.hacer_copia()
    base, entorno = copias.conexion()
    nueva = f'{base}_restaurada'
    subprocess.run(['dropdb', '--if-exists', '--maintenance-db', base, nueva], env=entorno, check=True)
    try:
        assert copias.restaurar(guardadas[0], base_nueva=nueva) == nueva
        assert copias.contar(nueva, entorno) == copias.contar(base, entorno)
        notas = copias.correr(['psql', '-At', '--dbname', nueva, '-c',
                               'select count(*) from taller_prueba_nota'], entorno)
        assert notas.strip() == '700'
        politicas = copias.correr(['psql', '-At', '--dbname', nueva, '-c',
                                   "select count(*) from pg_policies where policyname = 'por_taller'"], entorno)
        assert int(politicas) > 5                     # la copia trae también la segunda barrera
        copias.restaurar(guardadas[0])                # sobre la base de la app: queda igual
        with con_taller(taller):
            assert Nota.objects.count() == 700
    finally:
        subprocess.run(['dropdb', '--if-exists', '--maintenance-db', base, nueva], env=entorno)
