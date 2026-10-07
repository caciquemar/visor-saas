import time

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.views.decorators.cache import never_cache

from talleres.models import Taller

from .tareas import LATIDO

MINUTOS_SIN_LATIDO = 10


@never_cache
def salud(request):
    """Pública y sin datos: la consulta UptimeRobot. 200 si andan la base, Redis y la cola; si no, 503 con qué falla
    (la cola deja un latido cada minuto: si hace más de 10 que no hay, el consumidor está caído)."""
    fallas = []
    try:
        Taller.objects.exists()
    except Exception:
        fallas.append('base')
    try:
        cache.set('salud', 1, timeout=30)
        if cache.get('salud') != 1:
            fallas.append('cache')
    except Exception:
        fallas.append('cache')
    if not settings.HUEY.get('immediate') and 'cache' not in fallas:
        latido = cache.get(LATIDO)
        if latido is None or time.time() - latido > MINUTOS_SIN_LATIDO * 60:
            fallas.append('cola')
    if fallas:
        return HttpResponse('falla: ' + ', '.join(fallas), status=503, content_type='text/plain; charset=utf-8')
    return HttpResponse('ok', content_type='text/plain; charset=utf-8')
