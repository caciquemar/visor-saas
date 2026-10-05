from django import forms
from django.contrib.auth import password_validation

from .models import Membresia
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
