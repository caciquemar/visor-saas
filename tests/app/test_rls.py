"""Segunda barrera entre talleres en PostgreSQL (talleres/rls.py). Solo corren con PostgreSQL y un usuario que no es
superusuario, como en el servidor (en GitHub Actions: PRUEBAS_DATABASE_URL). Con SQLite se saltean.

Las consultas van en SQL directo a propósito: se saltean la primera barrera (el manager) para ver que la base sola
tampoco deja cruzar."""
import pytest
from django.db import connection, transaction
from django.db.utils import DatabaseError

from talleres.rls import POLITICA, tablas_de_taller
from talleres.separacion import con_taller
from tests.app.taller_prueba.models import Nota

pytestmark = [pytest.mark.postgres, pytest.mark.skipif(connection.vendor != 'postgresql',
                                                       reason='necesita PostgreSQL (PRUEBAS_DATABASE_URL)')]


def sql(consulta, *params):
    with connection.cursor() as c:
        c.execute(consulta, params)
        return c.fetchall() if c.description else c.rowcount


def test_la_app_no_entra_como_superusuario(db):
    assert sql('select rolsuper, rolbypassrls from pg_roles where rolname = current_user') == [(False, False)], (
        'Con un superusuario (o BYPASSRLS) PostgreSQL no aplica las políticas: la app tiene que usar un usuario común')


def test_toda_tabla_de_taller_tiene_politica_forzada(db):
    tablas = tablas_de_taller()
    assert 'taller_prueba_nota' in tablas and 'proyectos_proyecto' in tablas and 'trabajos_trabajo' in tablas
    con_politica = {t for (t,) in sql('select tablename from pg_policies where policyname = %s', POLITICA)}
    forzadas = {t for (t,) in sql('select relname from pg_class where relrowsecurity and relforcerowsecurity')}
    assert set(tablas) - con_politica == set()
    assert set(tablas) - forzadas == set()


def test_con_taller_la_base_solo_devuelve_ese_taller(t):
    with con_taller(t.A):
        assert sql('select texto from taller_prueba_nota') == [('nota de A',)]
        assert sql('select count(*) from talleres_membresia where taller_id = %s', t.B.pk) == [(0,)]
    with con_taller(t.B):
        assert sorted(sql('select texto from taller_prueba_nota')) == [('nota de B',), ('respuesta en B',)]


def test_con_taller_la_base_no_deja_cambiar_ni_borrar_de_otro(t):
    with con_taller(t.A):
        assert sql('update taller_prueba_nota set texto = %s where id = %s', 'pisada', t.nota_b.pk) == 0
        assert sql('delete from taller_prueba_nota where id = %s', t.nota_b.pk) == 0
    with con_taller(t.B):
        assert sql('select texto from taller_prueba_nota where id = %s', t.nota_b.pk) == [('nota de B',)]


def test_con_taller_la_base_no_deja_escribir_en_otro(t):
    with con_taller(t.A):
        with pytest.raises(DatabaseError, match='row-level security'), transaction.atomic():
            sql('insert into taller_prueba_nota (taller_id, texto) values (%s, %s)', t.B.pk, 'colada')
        with pytest.raises(DatabaseError, match='row-level security'), transaction.atomic():
            sql('update taller_prueba_nota set taller_id = %s where id = %s', t.B.pk, t.nota_a.pk)


def test_el_taller_cambia_en_la_misma_conexion(t):
    """La variable sigue al contexto aunque la conexión se reuse, dentro y fuera de transacciones."""
    for _ in range(2):
        with con_taller(t.A):
            assert sql('select count(*) from taller_prueba_nota') == [(1,)]
            with transaction.atomic():
                assert sql('select count(*) from taller_prueba_nota') == [(1,)]
        with con_taller(t.B):
            assert sql('select count(*) from taller_prueba_nota') == [(2,)]
        assert sql('select count(*) from taller_prueba_nota') == [(3,)]      # sin taller: manda la primera barrera


def test_el_orm_sigue_andando_con_las_politicas(t):
    with con_taller(t.A):
        Nota.objects.create(texto='otra de A')
        assert Nota.objects.count() == 2
    with con_taller(t.B):
        assert Nota.objects.count() == 2
