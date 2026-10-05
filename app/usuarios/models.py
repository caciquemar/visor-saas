"""Usuarios del servicio. Entran con mail y contraseña; los armadores e instaladores pueden no tener mail
y entrar solo con PIN en el taller (ver talleres/pin.py). Un usuario puede estar en varios talleres: la
relación con cada taller y el rol están en talleres.Membresia."""
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models


def normalizar_email(email):
    email = (email or '').strip().lower()
    return email or None


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
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        self.email = normalizar_email(self.email)

    def get_full_name(self):
        return str(self)

    def get_short_name(self):
        return str(self)
