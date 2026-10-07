"""El visor (visor/index.html) servido por la app, para el taller y para el link del cliente.

El visor pide sus datos con rutas relativas (`data/…`); acá se atienden esas mismas rutas debajo de donde se sirve la
página, así index.html cambia lo mínimo:

    /<taller>/visor/                      la página (con login, como todo /<taller>/)
    /<taller>/visor/data/index.json       proyectos con versión lista
    /<taller>/visor/data/<id>/<ruta>      resultado/ de la versión actual del proyecto <id>
    /c/<código>/                          la página en modo cliente (sin login; el middleware pone el taller del link)
    /c/<código>/data/cliente.json         la versión cliente (sin números de mecanizado)
    /c/<código>/data/clientes/<cc>/x.glb  modelos para realidad aumentada
    /c/<código>/data/texturas/<archivo>   texturas

Por /c/ nunca sale proyecto.json: solo lo que está en la lista blanca de `dato_cliente`.
"""
import json
import mimetypes
import re
from functools import lru_cache

from django.conf import settings
from django.db.models import F, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.templatetags.static import static
from django.utils import timezone
from django.views.decorators.http import require_GET

from talleres.archivos import abrir_de_taller
from talleres.models import Membresia
from talleres.roles import miembro

from .models import LinkCliente, Proyecto, Version

mimetypes.add_type('model/gltf-binary', '.glb')
INDEX = settings.RAIZ / 'visor' / 'index.html'
MARCA_CONFIG = '/*__VISOR__*/null'
UNA_SEMANA = 7 * 24 * 3600


@lru_cache(maxsize=4)
def _plantilla(modificado):
    texto = INDEX.read_text(encoding='utf-8')
    if MARCA_CONFIG not in texto:
        raise RuntimeError(f'visor/index.html no tiene la marca {MARCA_CONFIG}')
    return texto


def pagina(config):
    """index.html con la configuración de la app en `window.VISOR`."""
    texto = json.dumps(config, ensure_ascii=False).replace('<', '\\u003c')    # nada de </script> adentro
    r = HttpResponse(_plantilla(INDEX.stat().st_mtime_ns).replace(MARCA_CONFIG, texto, 1),
                     content_type='text/html; charset=utf-8')
    r['Cache-Control'] = 'no-cache'
    r['Referrer-Policy'] = 'no-referrer'          # el código del link no viaja a los CDN ni a otros sitios
    return r


def servir(request, ruta):
    """Un archivo del taller del pedido (abrir_de_taller da 404 si no es suyo), con la caché del nginx actual:
    JSON y GLB se revalidan; las texturas de una versión no cambian."""
    r = abrir_de_taller(request, ruta)
    if ruta.endswith(('.json', '.glb')):
        r['Cache-Control'] = 'no-cache'
    elif '/texturas/' in ruta:
        r['Cache-Control'] = f'private, max-age={UNA_SEMANA}'
    return r


def version_lista(proyecto_id):
    p = get_object_or_404(Proyecto.objects.select_related('version_actual'), pk=proyecto_id)
    v = p.version_actual
    if v is None or v.estado != Version.Estado.LISTO or not v.archivo_proyecto:
        raise Http404('El proyecto no tiene una versión lista')
    return p, v


def vigentes():
    return (LinkCliente.objects.filter(anulado__isnull=True)
            .filter(Q(vence__isnull=True) | Q(vence__gt=timezone.now())).order_by('-creado'))


def url_de_link(request, link):
    return request.build_absolute_uri(f'/c/{link.codigo}/')


# ---------------------------------------------------------------- taller

@miembro
def visor(request, taller):
    return pagina({'trabajos': False, 'sinCanto': request.taller.color_sin_canto,
                   'marca': {'nombre': request.taller.nombre}})


@miembro
def indice(request, taller):
    """Lo que en el visor de siempre es data/index.json, armado desde la base."""
    links = {}
    for link in vigentes():
        links.setdefault(link.proyecto_id, link)      # el más nuevo
    proyectos = (Proyecto.objects.filter(version_actual__estado=Version.Estado.LISTO)
                 .exclude(version_actual__archivo_proyecto='').order_by('nombre', 'pk'))
    lista = [{'id': p.pk, 'proyecto': p.nombre, 'archivo': f'{p.pk}/proyecto.json',
              'link': url_de_link(request, links[p.pk]) if p.pk in links else None} for p in proyectos]
    r = JsonResponse(lista, safe=False, json_dumps_params={'ensure_ascii': False})
    r['Cache-Control'] = 'no-cache'
    return r


@miembro
def dato(request, taller, id, ruta):
    _, v = version_lista(id)
    archivo = v.archivo_proyecto if ruta == 'proyecto.json' else f'{v.carpeta()}resultado/{ruta}'
    return servir(request, archivo)


def sin_colores(request, **kwargs):
    """data/materiales.json del visor de siempre: los colores del taller ya vienen dentro de cada proyecto."""
    return JsonResponse({})


miembro_sin_colores = miembro(sin_colores)


@miembro
def manifest(request, taller):
    inicio = f'/{request.taller.slug}/visor/'
    r = JsonResponse({
        'name': 'Visor', 'short_name': 'Visor', 'lang': 'es-AR',
        'start_url': inicio, 'scope': inicio, 'display': 'standalone',
        'background_color': '#DCE1E4', 'theme_color': '#DCE1E4',
        'icons': [{'src': static(f'visor/icono-{n}.png'), 'sizes': f'{n}x{n}',
                   'type': 'image/png', 'purpose': 'any maskable'} for n in (192, 512)],
    })
    r['Content-Type'] = 'application/manifest+json'
    return r


# ---------------------------------------------------------------- link del cliente

def link_o_404(request):
    link = getattr(request, 'link_cliente', None)
    if link is None:
        raise Http404('Este link no existe o ya no está disponible')
    return link


def no_disponible(request):
    return render(request, 'proyectos/link_no_disponible.html', status=404)


def es_del_taller(request):
    """El taller mirando su propio link ("Ver como cliente") no suma visitas."""
    return request.user.is_authenticated and Membresia.objects.filter(usuario=request.user, activa=True).exists()


@require_GET
def cliente(request, codigo):
    link = getattr(request, 'link_cliente', None)
    if link is None:
        return no_disponible(request)
    try:
        version_lista(link.proyecto_id)
    except Http404:
        return no_disponible(request)
    if not es_del_taller(request):
        LinkCliente.objects.filter(pk=link.pk).update(visitas=F('visitas') + 1, ultima_visita=timezone.now())
    taller = request.taller
    return pagina({
        'cliente': True, 'trabajos': False, 'sinCanto': taller.color_sin_canto,
        'marca': {'nombre': taller.nombre, 'color': taller.color or None, 'logo': 'logo' if taller.logo else None},
        'pie': {'nombre': settings.MARCA_SERVICIO, 'url': settings.MARCA_URL or None},
    })


@require_GET
def dato_cliente(request, codigo, ruta):
    link = link_o_404(request)
    p, v = version_lista(link.proyecto_id)
    if ruta == 'materiales.json':
        return sin_colores(request)
    if ruta == 'cliente.json':
        archivo = f'clientes/{p.codigo_cliente}.json'
    elif (re.fullmatch(rf'clientes/{re.escape(p.codigo_cliente)}/[\w.-]+\.glb', ruta)
          or re.fullmatch(r'texturas/[\w.-]+', ruta)):
        archivo = ruta
    else:
        raise Http404('No existe el archivo')
    return servir(request, f'{v.carpeta()}resultado/{archivo}')


@require_GET
def logo_cliente(request, codigo):
    link_o_404(request)
    if not request.taller.logo:
        raise Http404('El taller no tiene logo')
    r = abrir_de_taller(request, request.taller.logo.name)
    r['Cache-Control'] = 'no-cache'
    return r
