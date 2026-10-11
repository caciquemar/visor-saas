"""Usuarios del servicio. Entran con mail y contraseña; los armadores e instaladores pueden no tener mail y
entrar con su usuario y PIN, en la misma pantalla (ver talleres/cuentas.py y talleres/pin.py). Un usuario puede
estar en varios talleres: la relación con cada taller y el rol están en talleres.Membresia."""
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.utils.text import slugify


def normalizar_email(email):
    email = (email or '').strip().lower()
    return email or None


def normalizar_usuario(usuario):
    usuario = (usuario or '').strip().lower()
    return usuario or None


validar_usuario = RegexValidator(
    r'^[a-z0-9][a-z0-9._-]{1,39}$',
    'De 2 a 40 letras sin acentos, números, punto, guion o guion bajo (sin espacios ni @).')


def usuario_libre(nombre, excluir=None):
    """Un usuario para entrar armado con el nombre ('Ramón Pérez' -> 'ramon-perez'), que nadie tenga todavía
    (si está tomado, le suma un número: 'ramon-perez2')."""
    base = slugify(nombre or '')[:36].strip('-_.') or 'usuario'
    if len(base) < 2:
        base = f'{base}0'
    candidato, n = base, 2
    while Usuario.objects.filter(usuario=candidato).exclude(pk=excluir).exists():
        candidato, n = f'{base}{n}', n + 1
    return candidato


class UsuarioManager(BaseUserManager):
    use_in_migrations = True

    def _crear(self, email, password, **campos):
        usuario = self.model(email=normalizar_email(email), **campos)
        usuario.set_password(password)          # sin contraseña: queda inutilizable (solo PIN)
        usuario.save(using=self._db)
        return usuario

    def create_user(self, email=None, password=None, **campos):
        campos.setdefault('is_staff', False)
        campos.setdefault('is_superuser', False)
        return self._crear(email, password, **campos)

    def create_superuser(self, email, password=None, **campos):
        if not normalizar_email(email):
            raise ValueError('El superusuario necesita un mail')
        campos.update(is_staff=True, is_superuser=True)
        return self._crear(email, password, **campos)

    def get_by_natural_key(self, email):
        return self.get(email=normalizar_email(email))


class Usuario(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField('mail', unique=True, null=True, blank=True,
                              help_text='Vacío para armadores e instaladores que entran solo con PIN.')
    nombre = models.CharField('nombre', max_length=80, blank=True)
    usuario = models.CharField('usuario', max_length=40, unique=True, null=True, blank=True,
                               validators=[validar_usuario],
                               help_text='Para entrar con PIN (armadores e instaladores sin mail). '
                                         'Si no tiene mail y se deja vacío, se arma con el nombre.')
    is_active = models.BooleanField('activo', default=True)
    is_staff = models.BooleanField('administración del servicio', default=False,
                                   help_text='Puede entrar a la administración (solo el equipo del servicio, '
                                             'no los dueños de los talleres).')
    creado = models.DateTimeField('creado', auto_now_add=True)

    objects = UsuarioManager()

    USERNAME_FIELD = 'email'
    EMAIL_FIELD = 'email'
    REQUIRED_FIELDS = ['nombre']

    class Meta:
        verbose_name = 'usuario'
        verbose_name_plural = 'usuarios'
        ordering = ['nombre', 'email']

    def __str__(self):
        return self.nombre or self.email or f'usuario {self.pk}'

    def save(self, *args, **kwargs):
        self.email = normalizar_email(self.email)
        self.usuario = normalizar_usuario(self.usuario)
        if self.email is None and self.usuario is None:
            self.usuario = usuario_libre(self.nombre, excluir=self.pk)
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        self.email = normalizar_email(self.email)
        self.usuario = normalizar_usuario(self.usuario)

    def get_full_name(self):
        return str(self)

    def get_short_name(self):
        return str(self)
