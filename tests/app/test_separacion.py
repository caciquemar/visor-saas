"""Regla 1: un taller no puede ver ni tocar nada de otro. Cada prueba intenta cruzar de A a B y tiene que fallar."""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from huey.contrib.djhuey import task

from talleres.archivos import abrir_de_taller, ruta_valida
from talleres.separacion import OtroTaller, SinTaller, con_taller, taller_actual, tarea_de_taller
from tests.app.ayudas import sumar
from tests.app.taller_prueba.models import Nota
from tests.app.taller_prueba.vistas import FormNota


# ---------------------------------------------------------------- lectura

def test_cada_taller_ve_solo_lo_suyo(t):
    with con_taller(t.A):
        assert list(Nota.objects.values_list('texto', flat=True)) == ['nota de A']
        assert Nota.objects.count() == 1
        with pytest.raises(Nota.DoesNotExist):
            Nota.objects.get(pk=t.nota_b.pk)
        assert not Nota.objects.filter(texto__contains='B').exists()


def test_sin_taller_la_consulta_falla_en_vez_de_traer_todo(t):
    with pytest.raises(SinTaller):
        list(Nota.objects.all())
    with pytest.raises(SinTaller):
        Nota.objects.count()
    with pytest.raises(SinTaller):
        Nota.objects.filter(pk=t.nota_b.pk).update(texto='x')
    with pytest.raises(SinTaller):
        Nota.objects.create(texto='sin taller')


def test_relaciones_inversas_filtradas(t):
    with con_taller(t.A):
        nota_b = Nota.sin_filtro.get(pk=t.nota_b.pk)      # aunque alguien consiga el objeto de B...
        assert list(nota_b.respuestas.all()) == []        # ...sus respuestas no se ven desde A


def test_queryset_armado_antes_usa_el_taller_del_momento(t):
    """El queryset de un ModelForm se arma al importar el módulo: tiene que filtrar por el taller del pedido."""
    with con_taller(t.A):
        opciones_a = {n.pk for n in FormNota().fields['padre'].queryset}
    with con_taller(t.B):
        opciones_b = {n.pk for n in FormNota().fields['padre'].queryset}
    assert opciones_a == {t.nota_a.pk}
    assert opciones_b == {t.nota_b.pk, t.respuesta_b.pk}


def test_subconsultas_filtradas(t):
    with con_taller(t.A):
        assert not Nota.objects.filter(pk__in=Nota.objects.filter(texto='nota de B').values('pk')).exists()


def test_raw_no_se_puede_usar(t):
    with con_taller(t.A), pytest.raises(OtroTaller):
        Nota.objects.raw('select * from taller_prueba_nota')


def test_sin_sesion_va_a_entrar_sin_decir_si_el_taller_existe(client, t):
    for direccion in ('/taller-a/', '/taller-a/notas/', '/no-existe/'):
        r = client.get(direccion)
        assert r.status_code == 302 and r['Location'].startswith('/entrar/?next=')


def test_usuario_de_a_no_entra_a_b(cliente_de, t):
    c = cliente_de(t.dueno_a)
    assert c.get('/taller-a/').status_code == 200
    assert c.get('/taller-b/').status_code == 404
    assert c.get('/taller-b/notas/').status_code == 404
    assert c.get(f'/taller-b/notas/{t.nota_b.pk}/').status_code == 404
    assert c.get('/no-existe/').status_code == 404        # igual que un taller ajeno


def test_id_de_b_por_la_direccion_de_a(cliente_de, t):
    c = cliente_de(t.dueno_a)
    assert c.get(f'/taller-a/notas/{t.nota_a.pk}/').content == b'nota de A'
    assert c.get(f'/taller-a/notas/{t.nota_b.pk}/').status_code == 404
    assert c.get('/taller-a/notas/').content == b'nota de A'


def test_miembro_de_dos_talleres_ve_cada_uno_en_su_direccion(cliente_de, t):
    sumar(t.dueno_a, t.B, 'oficina')
    c = cliente_de(t.dueno_a)
    assert c.get('/taller-a/notas/').content == b'nota de A'
    assert c.get('/taller-b/notas/').content == b'nota de B\nrespuesta en B'


def test_membresia_inactiva_no_entra(cliente_de, t):
    t.m_oficina_a.activa = False
    with con_taller(t.A):
        t.m_oficina_a.save()
    assert cliente_de(t.oficina_a).get('/taller-a/').status_code == 404


def test_taller_inactivo_no_entra(cliente_de, t):
    t.A.activo = False
    t.A.save()
    assert cliente_de(t.dueno_a).get('/taller-a/').status_code == 404


def test_el_contexto_no_queda_pegado_despues_del_pedido(cliente_de, t):
    cliente_de(t.dueno_a).get('/taller-a/notas/')
    assert taller_actual.get() is None


# ---------------------------------------------------------------- escritura

def test_no_se_crea_en_otro_taller(t):
    with con_taller(t.A), pytest.raises(OtroTaller):
        Nota.objects.create(texto='intruso', taller=t.B)
    with con_taller(t.A):
        assert Nota.objects.create(texto='nueva').taller_id == t.A.pk


def test_no_se_cambia_el_taller_de_un_dato(t):
    with con_taller(t.A):
        nota = Nota.objects.get(pk=t.nota_a.pk)
        nota.taller = t.B
        with pytest.raises(OtroTaller):
            nota.save()
        with pytest.raises(OtroTaller):
            Nota.objects.update(taller=t.B)
        with pytest.raises(OtroTaller):
            Nota.objects.bulk_update([nota], ['taller'])


def test_no_se_pisa_una_fila_de_b_armando_el_objeto_a_mano(t):
    with con_taller(t.A), pytest.raises(OtroTaller):
        Nota(pk=t.nota_b.pk, texto='pisada').save()
    assert Nota.sin_filtro.get(pk=t.nota_b.pk).texto == 'nota de B'


def test_update_y_delete_masivos_no_tocan_b(t):
    with con_taller(t.A):
        assert Nota.objects.filter(pk=t.nota_b.pk).update(texto='pisada') == 0
        assert Nota.objects.filter(pk=t.nota_b.pk).delete()[0] == 0
        Nota.objects.all().delete()                       # borra todo... lo de A
    assert Nota.sin_filtro.get(pk=t.nota_b.pk).texto == 'nota de B'
    assert not Nota.sin_filtro.filter(pk=t.nota_a.pk).exists()


def test_borrar_un_objeto_de_b_desde_a(t):
    with con_taller(t.A), pytest.raises(OtroTaller):
        Nota.sin_filtro.get(pk=t.nota_b.pk).delete()
    assert Nota.sin_filtro.filter(pk=t.nota_b.pk).exists()


def test_no_se_enlaza_con_un_dato_de_b(t):
    with con_taller(t.A):
        nota_b = Nota.sin_filtro.get(pk=t.nota_b.pk)
        with pytest.raises(OtroTaller):
            Nota.objects.create(texto='hija', padre=nota_b)
        with pytest.raises(OtroTaller):
            Nota.objects.create(texto='hija', padre_id=t.nota_b.pk)


def test_bulk_create_con_una_fila_de_b(t):
    with con_taller(t.A), pytest.raises(OtroTaller):
        Nota.objects.bulk_create([Nota(texto='bien'), Nota(texto='mal', taller=t.B)])
    with con_taller(t.A):
        assert Nota.objects.count() == 1


def test_editar_y_borrar_lo_de_b_por_la_direccion_de_a(cliente_de, t):
    c = cliente_de(t.dueno_a)
    assert c.post(f'/taller-a/notas/{t.nota_b.pk}/editar/', {'texto': 'pisada'}).status_code == 404
    assert c.post(f'/taller-a/notas/{t.nota_b.pk}/borrar/').status_code == 404
    assert c.post(f'/taller-b/notas/{t.nota_b.pk}/borrar/').status_code == 404
    assert Nota.sin_filtro.get(pk=t.nota_b.pk).texto == 'nota de B'


def test_formulario_no_acepta_enlazar_con_b(cliente_de, t):
    c = cliente_de(t.dueno_a)
    r = c.post('/taller-a/notas/nueva/', {'texto': 'hija', 'padre': t.nota_b.pk})
    assert r.status_code == 400 and 'padre' in r.text
    r = c.post('/taller-a/notas/nueva/', {'texto': 'hija', 'padre': t.nota_a.pk})
    assert r.status_code == 200


# ---------------------------------------------------------------- archivos

def subir(c, slug, texto, contenido=b'datos'):
    r = c.post(f'/{slug}/notas/nueva/', {'texto': texto, 'archivo': SimpleUploadedFile('plano.txt', contenido)})
    assert r.status_code == 200, r.text
    return Nota.sin_filtro.get(pk=int(r.text))


def test_archivos_quedan_en_la_carpeta_del_taller(cliente_de, t):
    nota = subir(cliente_de(t.dueno_a), 'taller-a', 'con archivo')
    assert nota.archivo.name.startswith(f'talleres/{t.A.pk}/nota/')
    assert nota.archivo.name.endswith('_plano.txt')


def test_archivo_de_b_por_la_direccion_de_a(client, t):
    client.force_login(t.dueno_b)
    nota_b = subir(client, 'taller-b', 'secreta', b'secreto de B')
    ruta_b = nota_b.archivo.name
    assert b''.join(client.get(f'/taller-b/notas/{nota_b.pk}/archivo/').streaming_content) == b'secreto de B'

    client.force_login(t.dueno_a)
    assert client.get(f'/taller-a/notas/{nota_b.pk}/archivo/').status_code == 404
    assert client.get(f'/taller-b/notas/{nota_b.pk}/archivo/').status_code == 404
    assert client.get(f'/taller-a/notas/archivos/{ruta_b}').status_code == 404
    resto = ruta_b.split('/', 2)[2]
    for intento in (f'talleres/{t.A.pk}/../{t.B.pk}/{resto}', f'talleres/{t.A.pk}/%2e%2e/{t.B.pk}/{resto}',
                    f'talleres\\{t.B.pk}\\{resto}', f'/talleres/{t.B.pk}/{resto}'):
        assert client.get(f'/taller-a/notas/archivos/{intento}').status_code == 404, intento


def test_archivo_propio_por_ruta(cliente_de, t):
    c = cliente_de(t.dueno_a)
    nota = subir(c, 'taller-a', 'propia', b'de A')
    assert b''.join(c.get(f'/taller-a/notas/archivos/{nota.archivo.name}').streaming_content) == b'de A'


@pytest.mark.parametrize('ruta', [
    'talleres/2/nota/x.txt', 'talleres/1/../2/nota/x.txt', 'talleres/1/./nota/x.txt', 'talleres/1//x.txt',
    '/talleres/1/nota/x.txt', 'talleres\\1\\nota\\x.txt', 'C:/talleres/1/x.txt', 'talleres/1', 'talleres/1/',
    'talleres/10/nota/x.txt', 'otra/1/nota/x.txt', '', 'talleres/1/nota/x.txt\x00',
])
def test_rutas_rechazadas(ruta):
    class T:
        pk = 1
    assert ruta_valida(T, ruta) is None


def test_abrir_sin_taller_en_el_pedido():
    from django.http import Http404
    from django.test import RequestFactory
    with pytest.raises(Http404):
        abrir_de_taller(RequestFactory().get('/'), 'talleres/1/nota/x.txt')


# ---------------------------------------------------------------- tareas de la cola

@task()
@tarea_de_taller
def textos_de_notas():
    return sorted(Nota.objects.values_list('texto', flat=True))


def test_tarea_ve_solo_su_taller_y_no_deja_contexto(t):
    assert textos_de_notas(t.A.pk)() == ['nota de A']
    assert textos_de_notas(t.B.pk)() == ['nota de B', 'respuesta en B']
    assert taller_actual.get() is None
