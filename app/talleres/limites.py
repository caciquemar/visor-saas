"""Qué puede usar cada taller según su plan. La ficha 08 (planes y Mercado Pago) completa `permite`; hasta entonces
todo taller tiene todo. Las vistas y el visor ya preguntan acá, así activar un límite es cambiar solo este archivo.

Funciones:
- 'trabajos'            anotar y cambiar trabajos a realizar (sin esto, se ven pero no se cambian)
- 'fotos_de_trabajos'   subir fotos a los trabajos (en docs/plan.md, desde el plan Pro)
"""
FUNCIONES = ('trabajos', 'fotos_de_trabajos')

MENSAJES = {
    'trabajos': 'Tu plan no incluye anotar trabajos.',
    'fotos_de_trabajos': 'Tu plan no incluye fotos en los trabajos.',
}


def permite(taller, funcion):
    if funcion not in FUNCIONES:
        raise ValueError(f'Función desconocida: {funcion}')
    return True
