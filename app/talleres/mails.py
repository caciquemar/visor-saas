import logging

from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone

from .models import Invitacion

log = logging.getLogger('visor.mails')
NO_SALIO = ('No se pudo mandar el mail (revisá la configuración del correo del servidor). La invitación quedó '
            'creada: cuando el correo ande, usá Reenviar.')


def link_absoluto(ruta):
    return settings.URL_APP.rstrip('/') + ruta


def invitar(taller, email, rol, invitado_por=None):
    """Crea la invitación (en el taller actual) y manda el mail. Devuelve la invitación, con mail_enviado en
    False si el mail no salió (la invitación queda igual, para reenviarla; el error va al log y a Sentry)."""
    inv, token = Invitacion.nueva(email, rol, invitado_por)
    link = link_absoluto(reverse('invitacion', args=[token]))
    quien = f'{invitado_por} te invitó' if invitado_por and not invitado_por.is_staff else 'Te invitaron'
    try:
        send_mail(
            f'Invitación a {taller.nombre}',
            f'{quien} a sumarte a {taller.nombre} como {inv.get_rol_display().lower()}.\n\n'
            f'Para aceptar, abrí este link (vale {Invitacion.DIAS} días):\n{link}\n\n'
            f'Si no esperabas este mail, ignoralo.\n',
            None, [inv.email],
        )
        inv.mail_enviado = True
    except Exception:
        log.exception('No salió el mail de invitación a %s', inv.email)
        inv.mail_enviado = False
    return inv


def reenviar(taller, invitacion, invitado_por=None):
    """Manda de nuevo una invitación sin usar (vigente o vencida). El link viejo no se puede volver a mandar (en la
    base solo está su hash): se anula y sale una invitación nueva al mismo mail, con el mismo rol y 7 días más."""
    if invitacion.usada is not None:
        raise ValueError('La invitación ya se usó')
    ahora = timezone.now()
    if invitacion.vence > ahora:
        invitacion.vence = ahora
        invitacion.save(update_fields=['vence'])
    return invitar(taller, invitacion.email, invitacion.rol, invitado_por)
