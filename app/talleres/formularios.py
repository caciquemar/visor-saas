import re

from django import forms
from django.contrib.auth import password_validation
from django.core.files.uploadedfile import UploadedFile

from .models import Membresia, Taller
from .pin import validar_pin

Rol = Membresia.Rol


def roles_que_puede_dar(membresia):
    if membresia.rol == Rol.DUENO:
        return list(Rol.choices)
    return [(v, n) for v, n in Rol.choices if v != Rol.DUENO]


class CampoPin(forms.CharField):
    def __init__(self, **kwargs):
        kwargs.setdefault('label', 'PIN (4 a 6 números)')
        kwargs.setdefault('min_length', 4)
        kwargs.setdefault('max_length', 6)
        kwargs.setdefault('validators', [validar_pin])
        kwargs.setdefault('widget', forms.TextInput(attrs={'inputmode': 'numeric', 'autocomplete': 'off',
                                                           'pattern': r'\d{4,6}'}))
        super().__init__(**kwargs)


class FormInvitar(forms.Form):
    email = forms.EmailField(label='Mail')
    rol = forms.ChoiceField(label='Rol')

    def __init__(self, *args, membresia, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['rol'].choices = roles_que_puede_dar(membresia)

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if Membresia.objects.filter(usuario__email=email, activa=True).exists():
            raise forms.ValidationError('Ya es miembro del taller.')
        return email


class FormAltaConPin(forms.Form):
    nombre = forms.CharField(label='Nombre', max_length=80)
    rol = forms.ChoiceField(label='Rol', choices=[(r.value, r.label) for r in Membresia.ROLES_CON_PIN])
    pin = CampoPin()


class FormMiembro(forms.Form):
    rol = forms.ChoiceField(label='Rol')
    activa = forms.BooleanField(label='Activo en el taller', required=False)

    def __init__(self, *args, membresia, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['rol'].choices = roles_que_puede_dar(membresia)


class FormPin(forms.Form):
    pin = CampoPin(label='PIN nuevo (4 a 6 números)')


class FormCuentaNueva(forms.Form):
    nombre = forms.CharField(label='Tu nombre', max_length=80)
    password1 = forms.CharField(label='Contraseña', strip=False,
                                widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
                                help_text=password_validation.password_validators_help_text_html())
    password2 = forms.CharField(label='Repetí la contraseña', strip=False,
                                widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}))

    def __init__(self, *args, usuario, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario
        if usuario.nombre:
            self.fields['nombre'].initial = usuario.nombre

    def clean(self):
        datos = super().clean()
        p1, p2 = datos.get('password1'), datos.get('password2')
        if p1 and p2 and p1 != p2:
            self.add_error('password2', 'Las contraseñas no coinciden.')
        elif p1:
            self.usuario.nombre = datos.get('nombre') or self.usuario.nombre
            try:
                password_validation.validate_password(p1, self.usuario)
            except forms.ValidationError as e:
                self.add_error('password1', e)
        return datos

    def save(self):
        self.usuario.nombre = self.cleaned_data['nombre']
        self.usuario.set_password(self.cleaned_data['password1'])
        self.usuario.save()
        return self.usuario


COLOR_DEL_VISOR = '#1D5FE0'      # --tiza de visor/index.html


class FormMarca(forms.ModelForm):
    """Logo y color del taller para el link del cliente."""
    MAX_LOGO_MB = 2

    class Meta:
        model = Taller
        fields = ('logo', 'color')
        widgets = {'logo': forms.FileInput(attrs={'accept': 'image/png,image/jpeg,image/webp'}),
                   'color': forms.TextInput(attrs={'type': 'color'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.color:
            self.initial['color'] = COLOR_DEL_VISOR      # si no, el selector arranca en negro

    def clean_logo(self):
        logo = self.cleaned_data.get('logo')
        if isinstance(logo, UploadedFile):                     # el que ya estaba no se revisa de nuevo
            if logo.size > self.MAX_LOGO_MB * 1024 * 1024:
                raise forms.ValidationError(f'El logo pesa más de {self.MAX_LOGO_MB} MB.')
            formato = getattr(getattr(logo, 'image', None), 'format', None)
            if formato not in ('JPEG', 'PNG', 'WEBP'):          # nada de SVG: puede traer código
                raise forms.ValidationError('Subí el logo en PNG, JPG o WEBP.')
        return logo

    def clean_color(self):
        color = (self.cleaned_data.get('color') or '').strip().upper()
        if not color:
            return ''
        if not re.fullmatch(r'#[0-9A-F]{6}', color):
            raise forms.ValidationError('El color tiene que ser como #1D5FE0.')
        if luminancia(color) > 0.4:
            raise forms.ValidationError('Ese color es muy claro: las letras blancas de los botones no se leerían. '
                                        'Elegí uno más oscuro.')
        return color


def luminancia(color):
    """Luminancia relativa (WCAG) de #RRGGBB: 0 negro, 1 blanco. Con más de 0.4 el blanco encima no se lee bien."""
    def canal(c):
        c = int(c, 16) / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (canal(color[i:i + 2]) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b
