"""Etiquetas con QR (ficha 12).

    /<taller>/e/<código>[/<bulto>]           lo que abre el QR: el visor en esa pieza o ese mueble
    /<taller>/visor/api/etiqueta/<código>    lo mismo para el escáner del visor (JSON)
    /<taller>/proyectos/<id>/etiquetas/      elegir qué imprimir y en qué formato; el POST devuelve el PDF

Como todo /<taller>/, el middleware ya filtró por taller: un código de otro taller no se encuentra (404).
"""
from urllib.parse import urlencode

from django.conf import settings
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET

from proyectos.models import Proyecto
from talleres.roles import miembro

from . import claves, pdf
from .datos import proyecto_de, resolver, version_actual
from .formularios import FormFormato
from .models import Etiqueta, FormatoEtiquetas

YA_NO_ESTA = {'pieza': 'Esta pieza ya no está en la versión actual del proyecto.',
              'mueble': 'Este mueble ya no está en la versión actual del proyecto.'}
MAX_BULTOS = 20


def de_codigo(codigo):
    return Etiqueta.objects.select_related('proyecto__version_actual').filter(codigo=codigo.upper()).first()


def url_de(request, etiqueta, bulto=None):
    """Lo que va en el QR. Con URL_APP y no con el Host del pedido: la etiqueta impresa dura más que cualquier
    cambio de proxy."""
    return f'{settings.URL_APP}/{request.taller.slug}/e/{etiqueta.codigo}' + (f'/{bulto}' if bulto else '')


@miembro
@require_GET
def abrir(request, taller, codigo, bulto=None):
    e = de_codigo(codigo)
    if e is None:
        raise Http404('No existe la etiqueta')
    r = resolver(e)
    if r is None:
        return render(request, 'etiquetas/ya_no_esta.html', {'etiqueta': e, 'texto': YA_NO_ESTA[e.tipo]},
                      status=410)
    q = {'p': e.proyecto_id, **({'pz': r['panel']} if e.tipo == Etiqueta.Tipo.PIEZA else {'m': r['mueble']})}
    return redirect(reverse('taller:proyectos:visor', kwargs={'taller': request.taller.slug}) + '?' + urlencode(q))


@miembro
@require_GET
def api(request, taller, codigo):
    e = de_codigo(codigo)
    if e is None:
        return JsonResponse({'error': 'Esta etiqueta no es de este taller.'}, status=404)
    r = resolver(e)
    if r is None:
        return JsonResponse({'error': YA_NO_ESTA[e.tipo], 'proyecto': e.proyecto_id}, status=410)
    return JsonResponse({'proyecto': e.proyecto_id, 'tipo': e.tipo, **r}, json_dumps_params={'ensure_ascii': False})


def numero(texto, defecto, menos, mas):
    try:
        return min(max(int(texto), menos), mas)
    except (TypeError, ValueError):
        return defecto


def elegidos(request, campo, total):
    return sorted({int(i) for i in request.POST.getlist(campo) if i.isdigit() and int(i) < total})


@miembro
def imprimir(request, taller, id):
    """Cualquiera del taller imprime (el armador repone una etiqueta perdida). El formato elegido queda guardado
    para el taller."""
    proyecto = get_object_or_404(Proyecto.objects.select_related('version_actual'), pk=id)
    v = version_actual(proyecto)
    if v is None:
        return render(request, 'etiquetas/imprimir.html', {'proyecto': proyecto, 'sin_version': True})
    d = proyecto_de(v)
    piezas = claves.piezas(d)
    cuenta = claves.muebles(d)
    muebles = list(cuenta)
    form = FormFormato(request.POST or None, instance=FormatoEtiquetas.objects.first() or FormatoEtiquetas())
    error = None
    if request.method == 'POST':
        sel_piezas, sel_muebles = elegidos(request, 'pieza', len(piezas)), elegidos(request, 'mueble', len(muebles))
        if request.POST.get('version') != str(v.pk):
            error = 'Mientras elegías se pasó a otra versión del proyecto. Volvé a elegir qué imprimir.'
        elif not sel_piezas and not sel_muebles:
            error = 'Elegí al menos una pieza o un mueble.'
        elif form.is_valid():
            formato = form.save().para_pdf()
            etiquetas = []
            for i in sel_piezas:
                x = piezas[i]
                e = Etiqueta.para(proyecto, Etiqueta.Tipo.PIEZA, x['clave'])
                etiquetas.append(pdf.etiqueta_de_pieza(x['panel'], proyecto.nombre, url_de(request, e),
                                                       x['copia'], x['de']))
            for i in sel_muebles:
                nombre = muebles[i]
                e = Etiqueta.para(proyecto, Etiqueta.Tipo.MUEBLE, {'mueble': nombre})
                bultos = numero(request.POST.get(f'bultos-{i}'), 1, 1, MAX_BULTOS)
                for b in range(1, bultos + 1):
                    etiquetas.append(pdf.etiqueta_de_mueble(nombre, proyecto.nombre, url_de(request, e, b),
                                                            cuenta[nombre], b, bultos, proyecto.cliente,
                                                            proyecto.direccion))
            desde = numero(request.POST.get('desde'), 1, 1, formato.por_hoja)
            r = HttpResponse(pdf.generar(etiquetas, formato, desde=desde), content_type='application/pdf')
            r['Content-Disposition'] = f'inline; filename="etiquetas-{proyecto.pk}.pdf"'
            return r
    indice = {nombre: j for j, nombre in enumerate(muebles)}
    grupos = {}
    for i, x in enumerate(piezas):
        grupos.setdefault(x['panel']['mueble'], []).append((str(i), x))
    return render(request, 'etiquetas/imprimir.html', {
        'proyecto': proyecto, 'version': v, 'form': form, 'error': error,
        'grupos': [{'indice': str(indice[nombre]), 'nombre': nombre, 'piezas': lista}
                   for nombre, lista in grupos.items()],
        'medida_hoja': FormatoEtiquetas.MEDIDA_HOJA, 'medida_rollo': FormatoEtiquetas.MEDIDA_ROLLO,
        'elegidas': request.POST.getlist('pieza'), 'elegidos': request.POST.getlist('mueble'),
        'max_bultos': MAX_BULTOS,
    }, status=400 if request.method == 'POST' else 200)
