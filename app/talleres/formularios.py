import re

from django import forms
from django.contrib.auth import password_validation
from django.core.files.uploadedfile import UploadedFile

from usuarios.models import Usuario, normalizar_usuario, validar_usuario

from .models import Membresia, Rol, Taller
from .permisos import CLAVES, NOMBRES, SENSIBLES, grupos
from .pin import validar_pin


def roles_que_puede_dar(membresia):
    """Los roles del taller que puede dar quien está en Equipo: Administrador solo lo da un administrador."""
    roles = Rol.objects.all()
    return roles if membresia.es_admin else roles.exclude(base='admin')


class CampoPin(forms.CharField):
    def __init__(self, **kwargs):
        kwargs.setdefault('label', 'PIN (4 a 6 números)')
        kwargs.setdefault('min_length', 4)
        kwargs.setdefault('max_length', 6)
        kwargs.setdefault('validators', [validar_pin])
        kwargs.setdefault('widget', forms.TextInput(attrs={'inputmode': 'numeric', 'autocomplete': 'off',
                                                           'pattern': r'\d{4,6}'}))
        super().__init__(**kwargs)


class CampoUsuario(forms.CharField):
    """Usuario para entrar con PIN: único en todo el servicio (no solo en el taller)."""

    def __init__(self, **kwargs):
        kwargs.setdefault('label', 'Usuario para entrar')
        kwargs.setdefault('max_length', 40)
        kwargs.setdefault('widget', forms.TextInput(attrs={'autocapitalize': 'off', 'autocorrect': 'off',
                                                           'spellcheck': 'false'}))
        super().__init__(**kwargs)

    def clean(self, valor):
        valor = normalizar_usuario(super().clean(valor))
        if valor:
            validar_usuario(valor)
        return valor


def usuario_tomado(valor, excluir=None):
    return Usuario.objects.filter(usuario=valor).exclude(pk=excluir).exists()


class CampoRol(forms.ModelChoiceField):
    def label_from_instance(self, rol):
        return f'{rol.nombre} (entra con usuario y PIN)' if rol.con_pin else rol.nombre


class FormPersona(forms.Form):
    """Agregar persona (Equipo, ficha 23): con su mail le llega la invitación; sin mail (solo en un rol que entra con
    PIN) se le arma la cuenta con usuario y PIN."""
    nombre = forms.CharField(label='Nombre y apellido', max_length=80)
    rol = CampoRol(label='Rol', queryset=Rol.objects.none(), empty_label=None)
    entra = forms.ChoiceField(label='Cómo entra', initial='mail', required=False, widget=forms.RadioSelect, choices=[
        ('mail', 'Con su mail (le llega una invitación)'), ('pin', 'Con usuario y PIN, sin mail')])
    email = forms.EmailField(label='Mail', required=False,
                             help_text='Le llega un mail para aceptar la invitación y poner su contraseña.')
    usuario = CampoUsuario(required=False, help_text='Con esto y el PIN entra. Si lo dejás vacío, se arma con '
                                                     'el nombre (Ramón Pérez → ramon-perez).')
    pin = CampoPin(required=False)

    def __init__(self, *args, membresia, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['rol'].queryset = roles_que_puede_dar(membresia)

    def clean(self):
        datos = super().clean()
        rol = datos.get('rol')
        datos['entra'] = datos.get('entra') or 'mail'
        if rol is None:
            return datos
        if datos.get('entra') == 'pin' and not rol.con_pin:
            self.add_error('entra', f'El rol {rol} no entra con PIN: invitalo por mail.')
        elif datos.get('entra') == 'pin':
            if not datos.get('pin'):
                self.add_error('pin', 'Poné el PIN con el que va a entrar.')
            valor = datos.get('usuario')
            if valor and usuario_tomado(valor):
                self.add_error('usuario', f'El usuario «{valor}» ya existe. Probá con otro (por ejemplo, con el '
                                          f'apellido o un número).')
        else:
            email = (datos.get('email') or '').strip().lower()
            if not email:
                self.add_error('email', 'Poné su mail: le llega la invitación.')
            elif Membresia.objects.filter(usuario__email=email, activa=True).exists():
                self.add_error('email', 'Ya es miembro del taller.')
            datos['email'] = email
        return datos


class FormDatosPin(forms.Form):
    """Datos de quien entra con PIN: el nombre (lo que se ve en Equipo, en los trabajos y en las marcas) y el
    usuario con el que entra."""
    nombre = forms.CharField(label='Nombre y apellido', max_length=80)
    usuario = CampoUsuario()

    def __init__(self, *args, usuario, **kwargs):
        kwargs.setdefault('initial', {'nombre': usuario.nombre, 'usuario': usuario.usuario})
        super().__init__(*args, **kwargs)
        self.usuario = usuario

    def clean_usuario(self):
        valor = self.cleaned_data['usuario']
        if usuario_tomado(valor, excluir=self.usuario.pk):
            raise forms.ValidationError(f'El usuario «{valor}» ya existe. Probá con otro.')
        return valor


class FormMiembro(forms.Form):
    rol = CampoRol(label='Rol', queryset=Rol.objects.none(), empty_label=None)

    def __init__(self, *args, membresia, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['rol'].queryset = roles_que_puede_dar(membresia)


class FormRol(forms.ModelForm):
    """Ficha de un rol (ficha 23): nombre, si entra con PIN y sus permisos. Los del Administrador no se tocan."""
    permisos = forms.MultipleChoiceField(label='Puede', required=False, widget=forms.CheckboxSelectMultiple,
                                         choices=[(c, NOMBRES[c]) for c in CLAVES])

    class Meta:
        model = Rol
        fields = ('nombre', 'con_pin', 'permisos')
        help_texts = {'con_pin': 'Para quien entra desde un celular del taller con su usuario y un PIN, sin mail.'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.es_admin:                  # solo se renombra
            del self.fields['con_pin'], self.fields['permisos']

    def grupos(self):
        """Las casillas de permisos agrupadas (Armado, Proyectos, Producción, Configuración)."""
        marcados = set(self['permisos'].value() or [])
        return [(g, [(c, n, c in marcados, c in SENSIBLES) for c, n in lista]) for g, lista in grupos()]

    def clean_nombre(self):
        nombre = self.cleaned_data['nombre'].strip()
        if Rol.objects.filter(nombre__iexact=nombre).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('Ya hay un rol con ese nombre.')
        return nombre

    def clean(self):
        datos = super().clean()
        if datos.get('con_pin') and set(datos.get('permisos') or []) & SENSIBLES:
            raise forms.ValidationError('Un rol que entra con PIN no puede manejar ' + ', '.join(
                NOMBRES[c] for c in CLAVES if c in SENSIBLES) + ': un PIN de 4 números no alcanza para eso.')
        return datos

    def clean_permisos(self):
        elegidos = set(self.cleaned_data['permisos'])
        return [c for c in CLAVES if c in elegidos]            # en el orden del catálogo


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
