"""Qué puede usar cada taller según su plan (ficha 08). Las funciones y los topes de cada plan se cambian en la
administración (suscripciones.Plan); acá están solo las claves y las preguntas que hacen las vistas.

Con el cobro apagado (administración → Configuración del cobro) todo taller tiene todo.

Funciones:
- 'trabajos'             anotar y cambiar tareas (sin esto, se ven pero no se cambian)
- 'fotos_de_trabajos'    subir fotos a las tareas
- 'avance'               Producción: Mi puesto, tablero, procesos, cargas (ficha 13 en adelante)
- 'realidad_aumentada'   "Ver en tu espacio" en el link del cliente
- 'probador'             probador de colores en el link del cliente
- 'logo_en_link'         logo y nombre del taller en el link del cliente
- 'colores_en_link'      color del taller en el link del cliente
"""
FUNCIONES = ('trabajos', 'fotos_de_trabajos', 'avance', 'realidad_aumentada', 'probador', 'logo_en_link',
             'colores_en_link')

NOMBRES = {
    'trabajos': 'Tareas',
    'fotos_de_trabajos': 'Fotos en las tareas',
    'avance': 'Producción (Mi puesto, tablero y cargas)',
    'realidad_aumentada': 'Realidad aumentada en el link del cliente',
    'probador': 'Probador de colores en el link del cliente',
    'logo_en_link': 'Logo del taller en el link del cliente',
    'colores_en_link': 'Color del taller en el link del cliente',
}

MENSAJES = {
    'trabajos': 'Tu plan no incluye anotar tareas.',
    'fotos_de_trabajos': 'Tu plan no incluye fotos en las tareas.',
    'avance': 'Tu plan no incluye Producción.',
    'realidad_aumentada': 'Tu plan no incluye la realidad aumentada.',
    'probador': 'Tu plan no incluye el probador de colores.',
    'logo_en_link': 'Tu plan no incluye el logo en el link del cliente.',
    'colores_en_link': 'Tu plan no incluye el color en el link del cliente.',
    'proyectos': 'Llegaste a los {max} proyectos activos de tu plan. Archivá uno terminado o pasá a un plan mayor.',
    'usuarios': 'Llegaste a las {max} personas de tu plan. Desactivá a alguien o pasá a un plan mayor.',
}


def activas():
    from suscripciones.config import cobro_activo
    return cobro_activo()


def plan_de(taller):
    """El plan que rige hoy para el taller del contexto."""
    from suscripciones.servicio import plan_vigente, suscripcion_de
    return plan_vigente(suscripcion_de(taller))


def permite(taller, funcion):
    if funcion not in FUNCIONES:
        raise ValueError(f'Función desconocida: {funcion}')
    if not activas():
        return True
    return funcion in (plan_de(taller).funciones or [])


def proyectos_usados():
    from proyectos.models import Proyecto
    return Proyecto.objects.filter(archivado_en__isnull=True).count()


def usuarios_usados():
    """Miembros activos (también los que entran con PIN) más invitaciones vigentes sin usar."""
    from django.utils import timezone

    from .models import Invitacion, Membresia
    invitaciones = (Invitacion.objects.filter(usada__isnull=True, vence__gt=timezone.now())   # anular = vencer
                    .values('email').distinct().count())
    return Membresia.objects.filter(activa=True).count() + invitaciones


def tope(taller, que):
    """(máximo, usados) de 'proyectos' o 'usuarios'; máximo None = sin límite."""
    if not activas():
        return None, 0
    plan = plan_de(taller)
    if que == 'proyectos':
        return plan.max_proyectos, proyectos_usados()
    return plan.max_usuarios, usuarios_usados()


def puede_sumar(taller, que, cuantos=1):
    maximo, usados = tope(taller, que)
    return maximo is None or usados + cuantos <= maximo


def mensaje_de_tope(taller, que):
    return MENSAJES[que].format(max=tope(taller, que)[0])
