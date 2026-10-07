import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator, validate_slug
from django.db import models
from django.utils import timezone

from conversor.polyboard_a_app import SIN_CANTO

from .archivos import ruta_de_logo
from .separacion import DatoDeTaller

# Primeras partes de la dirección que no son talleres (app.<dominio>/<esto>/...).
RESERVADOS = {
    'admin', 'entrar', 'salir', 'cuenta', 'c', 'static', 'archivos', 'api', 'app', 'www', 'ayuda',
    'precios', 'planes', 'favicon.ico', 'robots.txt',
}


def validar_slug_de_taller(valor):
    validate_slug(valor)
    if valor != valor.lower():
        raise ValidationError('Solo minúsculas, números y guiones.')
    if valor in RESERVADOS:
        raise ValidationError(f'"{valor}" está reservado; elegí otro.')


class Taller(models.Model):
    nombre = models.CharField('nombre', max_length=120)
    slug = models.SlugField('dirección', max_length=40, unique=True, validators=[validar_slug_de_taller],
                            help_text='Va en la dirección del taller: app.dominio/esta-direccion/. Minúsculas y guiones.')
    activo = models.BooleanField('activo', default=True)
    creado = models.DateTimeField('creado', auto_now_add=True)
    # Marca del taller en el link del cliente (ficha 04): la elige el dueño en /<taller>/marca/.
    logo = models.ImageField('logo', upload_to=ruta_de_logo, blank=True, max_length=300)
    color = models.CharField('color', max_length=7, blank=True,
                             validators=[RegexValidator(r'^#[0-9A-F]{6}$', 'El color tiene que ser como #1D5FE0.')])
    # Lados de las piezas sin canto, en el visor y en la realidad aumentada (se elige en Materiales).
    color_sin_canto = models.CharField('color de los lados sin canto', max_length=7, default=SIN_CANTO,
                                       validators=[RegexValidator(r'^#[0-9A-F]{6}$',
                                                                  'El color tiene que ser como #B58F63.')])

    class Meta:
        verbose_name = 'taller'
        verbose_name_plural = 'talleres'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Membresia(DatoDeTaller):
    class Rol(models.TextChoices):
        DUENO = 'dueno', 'Dueño'
        OFICINA = 'oficina', 'Oficina'
        ARMADOR = 'armador', 'Armador'
        INSTALADOR = 'instalador', 'Instalador'

    ROLES_CON_PIN = (Rol.ARMADOR, Rol.INSTALADOR)

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='membresias')
    rol = models.CharField('rol', max_length=12, choices=Rol.choices)
    activa = models.BooleanField('activa', default=True)
    pin = models.CharField('PIN (cifrado)', max_length=128, blank=True)
    pin_fallos = models.PositiveSmallIntegerField('intentos fallidos de PIN', default=0)
    pin_bloqueado_hasta = models.DateTimeField('PIN bloqueado hasta', null=True, blank=True)
    creada = models.DateTimeField('creada', auto_now_add=True)

    class Meta:
        verbose_name = 'miembro'
        verbose_name_plural = 'miembros'
        ordering = ['usuario__nombre', 'usuario__email']
        constraints = [models.UniqueConstraint(fields=['taller', 'usuario'], name='una_membresia_por_taller')]

    def __str__(self):
        return f'{self.usuario} ({self.get_rol_display()})'

    @property
    def usa_pin(self):
        return self.rol in self.ROLES_CON_PIN


class Invitacion(DatoDeTaller):
    DIAS = 7

    email = models.EmailField('mail')
    rol = models.CharField('rol', max_length=12, choices=Membresia.Rol.choices)
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    vence = models.DateTimeField('vence')
    creada = models.DateTimeField('creada', auto_now_add=True)
    invitado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='+')
    usada = models.DateTimeField('usada', null=True, blank=True)
    usada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='+')

    class Meta:
        verbose_name = 'invitación'
        verbose_name_plural = 'invitaciones'
        ordering = ['-creada']

    def __str__(self):
        return f'{self.email} ({self.get_rol_display()})'

    @staticmethod
    def cifrar(token):
        return hashlib.sha256(token.encode()).hexdigest()

    @classmethod
    def nueva(cls, email, rol, invitado_por=None):
        """Crea la invitación en el taller actual. Devuelve (invitación, token): el token solo existe en el
        mail; en la base queda su hash."""
        token = secrets.token_urlsafe(32)
        inv = cls.objects.create(email=email.strip().lower(), rol=rol, token_hash=cls.cifrar(token),
                                 vence=timezone.now() + timedelta(days=cls.DIAS), invitado_por=invitado_por)
        return inv, token

    @property
    def vigente(self):
        return self.usada is None and timezone.now() < self.vence
