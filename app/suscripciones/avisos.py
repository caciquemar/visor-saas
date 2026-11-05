"""Mails de la suscripción: antes de que venza, al vencer, al pasar a solo lectura, al suspenderse y antes del
borrado. Cada uno se manda una sola vez (la clave queda en `Suscripcion.avisos`). Van a quien maneja la suscripción
(permiso 'suscripcion') y tiene mail."""
import logging
from datetime import timedelta

from django.core.mail import send_mail
from django.urls import reverse

from talleres.mails import link_absoluto
from talleres.models import Membresia

from . import estados

log = logging.getLogger('visor.suscripciones')


def destinatarios():
    return sorted({m.usuario.email for m in Membresia.objects.filter(activa=True).select_related('usuario', 'rol')
                   if m.usuario.email and m.puede('suscripcion')})


def texto(clave, s, taller):
    tipo = clave.split(':')[0]
    hasta = estados.cubierto_hasta(s)
    fecha = f'{hasta:%d/%m/%Y}'
    que = 'la prueba' if estados.estado(s, hasta) == estados.PRUEBA else 'tu plan'
    borrado = f'{hasta + timedelta(days=estados.BORRAR):%d/%m/%Y}'
    if tipo.startswith('vence-'):
        return (f'{taller.nombre}: {que} vence el {fecha}',
                f'El {fecha} vence {que} de {taller.nombre}. Para seguir sin cortes, pagá el próximo período '
                f'(mensual, semestral o anual) desde Mi suscripción.')
    if tipo == estados.VENCIDA:
        return (f'{taller.nombre}: venció tu plan',
                f'Tu plan venció el {fecha}. Durante {estados.GRACIA} días todo sigue andando; después la cuenta queda '
                f'en solo lectura (se ve todo, pero no se puede subir ni cambiar nada) hasta que pagues.')
    if tipo == estados.SOLO_LECTURA:
        return (f'{taller.nombre}: la cuenta quedó en solo lectura',
                f'La cuenta de {taller.nombre} quedó en solo lectura: se ve todo, pero no se puede subir ni cambiar '
                f'nada. Al pagar vuelve a andar al instante, con todos tus datos.')
    if tipo == estados.SUSPENDIDA:
        return (f'{taller.nombre}: la cuenta está suspendida',
                f'La cuenta de {taller.nombre} está suspendida: nadie del taller puede entrar y los links de los '
                f'clientes no andan. Tus datos siguen guardados hasta el {borrado}. Al pagar vuelve todo.')
    if tipo.startswith('borrado-'):
        return (f'{taller.nombre}: los datos se borran el {borrado}',
                f'Los datos de {taller.nombre} (proyectos, tareas, fotos) se van a borrar después del {borrado}. '
                f'Si querés conservarlos, pagá cualquier período desde Mi suscripción y vuelve todo.')
    return None


def mandar_avisos(s, hoy):
    taller = s.taller
    pendientes = [c for c in estados.avisos_del_dia(s, hoy) if c not in (s.avisos or [])]
    if not pendientes:
        return []
    para = destinatarios()
    link = link_absoluto(reverse('taller:suscripcion:pantalla', kwargs={'taller': taller.slug}))
    mandados = []
    for clave in pendientes:
        t = texto(clave, s, taller)
        if t is None or not para:
            mandados.append(clave)              # no hay a quién: no se vuelve a intentar
            continue
        asunto, cuerpo = t
        try:
            send_mail(asunto, f'{cuerpo}\n\nMi suscripción: {link}\n', None, para)
            mandados.append(clave)
        except Exception:
            log.exception('No salió el aviso %s de %s', clave, taller)
    if mandados:
        s.avisos = [*(s.avisos or []), *mandados][-50:]
        s.save(update_fields=['avisos'])
    return mandados
