import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator, validate_slug
from django.db import models
from django.utils import timezone

from conversor.polyboard_a_app import SIN_CANTO

from . import permisos as permisos_
from .archivos import ruta_de_logo
from .separacion import DatoDeTaller

# Primeras partes de la dirección que no son talleres (app.<dominio>/<esto>/...).
RESERVADOS = {
    'admin', 'entrar', 'salir', 'cuenta', 'c', 'static', 'archivos', 'api', 'app', 'www', 'ayuda',
    'precios', 'planes', 'favicon.ico', 'robots.txt', 'salud',
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
    # Marca del taller en el link del cliente (ficha 04): la elige el administrador en /<taller>/marca/.
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


class Rol(DatoDeTaller):
    """Un rol del taller (ficha 23): qué puede hacer quien lo tiene (claves de talleres/permisos.py) y si entra con
    usuario y PIN. Los cuatro de BASES se crean con el taller; `base` los encuentra. El de Administrador tiene todos
    los permisos y no se edita ni se borra (solo se renombra)."""
    nombre = models.CharField('nombre', max_length=40)
    permisos = models.JSONField('permisos', default=list, blank=True)
    con_pin = models.BooleanField('entra con usuario y PIN', default=False)
    base = models.CharField('rol inicial', max_length=12, blank=True, editable=False)
    orden = models.PositiveSmallIntegerField('orden', default=0)

    class Meta:
        verbose_name = 'rol'
        verbose_name_plural = 'roles'
        ordering = ['orden', 'pk']
        constraints = [
            models.UniqueConstraint(fields=['taller', 'base'], condition=~models.Q(base=''), name='un_rol_inicial'),
            models.UniqueConstraint(fields=['taller', 'nombre'], name='un_nombre_de_rol_por_taller'),
        ]

    def __str__(self):
        return self.nombre

    @property
    def es_admin(self):
        return self.base == permisos_.ADMIN

    def puede(self, permiso):
        return self.es_admin or permiso in self.permisos


def rol_inicial(base):
    """El rol inicial del taller actual con esa base ('admin', 'oficina', 'armador', 'instalador'; 'dueno' es el
    nombre viejo de 'admin')."""
    return Rol.objects.get(base=permisos_.ADMIN if base == 'dueno' else base)


def crear_roles_iniciales(taller):
    """Los cuatro roles con que arranca un taller (talleres/permisos.py, BASES). No repite los que ya tiene."""
    from .separacion import con_taller
    with con_taller(taller):
        for orden, (base, nombre, con_pin, permisos) in enumerate(permisos_.BASES):
            if not Rol.objects.filter(base=base).exists():
                Rol.objects.create(base=base, nombre=nombre, con_pin=con_pin, permisos=list(permisos), orden=orden)


class Membresia(DatoDeTaller):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='membresias')
    rol = models.ForeignKey(Rol, on_delete=models.PROTECT, related_name='membresias', verbose_name='rol')
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
        return f'{self.usuario} ({self.rol})'

    def get_rol_display(self):
        return self.rol.nombre

    @property
    def usa_pin(self):
        return self.rol.con_pin

    @property
    def es_admin(self):
        return self.rol.es_admin

    def puede(self, permiso):
        return self.rol.puede(permiso)


class Invitacion(DatoDeTaller):
    DIAS = 7

    email = models.EmailField('mail')
    rol = models.ForeignKey(Rol, on_delete=models.PROTECT, related_name='invitaciones', verbose_name='rol')
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
        return f'{self.email} ({self.rol})'

    def get_rol_display(self):
        return self.rol.nombre

    @staticmethod
    def cifrar(token):
        return hashlib.sha256(token.encode()).hexdigest()

    @classmethod
    def nueva(cls, email, rol, invitado_por=None):
        """Crea la invitación en el taller actual. Devuelve (invitación, token): el token solo existe en el
        mail; en la base queda su hash."""
        if isinstance(rol, str):
            rol = rol_inicial(rol)
        token = secrets.token_urlsafe(32)
        inv = cls.objects.create(email=email.strip().lower(), rol=rol, token_hash=cls.cifrar(token),
                                 vence=timezone.now() + timedelta(days=cls.DIAS), invitado_por=invitado_por)
        return inv, token

    @property
    def vigente(self):
        return self.usada is None and timezone.now() < self.vence


class LinkDeEntrada(DatoDeTaller):
    """Link personal para que un armador o instalador entre desde su celular sin escribir nada (se manda por
    WhatsApp desde Equipo). Vale 24 horas y una sola vez; uno nuevo anula el anterior. El token solo está en el
    link; en la base, su hash."""
    HORAS = 24

    membresia = models.ForeignKey(Membresia, on_delete=models.CASCADE, related_name='+')
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    vence = models.DateTimeField('vence')
    creado = models.DateTimeField('creado', auto_now_add=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='+')
    usado = models.DateTimeField('usado', null=True, blank=True)

    class Meta:
        verbose_name = 'link de entrada'
        verbose_name_plural = 'links de entrada'
        ordering = ['-creado']

    @classmethod
    def nuevo(cls, membresia, creado_por=None):
        """En el taller actual. Anula los anteriores sin usar de esa persona. Devuelve (link, token)."""
        ahora = timezone.now()
        cls.objects.filter(membresia=membresia, usado__isnull=True, vence__gt=ahora).update(vence=ahora)
        token = secrets.token_urlsafe(32)
        link = cls.objects.create(membresia=membresia, token_hash=Invitacion.cifrar(token), creado_por=creado_por,
                                  vence=ahora + timedelta(hours=cls.HORAS))
        return link, token

    @property
    def vigente(self):
        return self.usado is None and timezone.now() < self.vence
