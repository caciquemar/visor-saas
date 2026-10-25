"""Mi cuenta (/<taller>/cuenta/): cada uno ve y cambia sus propios datos. Nombre (y usuario, si entra con PIN),
mail y contraseña (pidiendo la contraseña actual), su PIN en este taller (pidiendo el actual), sus huellas y los
talleres donde está. Los cambios de rol o de PIN de otros siguen en Equipo."""
from django import forms
from django.contrib import messages
from django.contrib.auth import password_validation, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.hashers import check_password
from django.shortcuts import redirect, render
from django.urls import reverse

from usuarios.models import Usuario, normalizar_email

from . import equipo_celular
from . import pin as pines
from .formularios import CampoPin, FormDatosPin
from .cuentas import mis_talleres
from .roles import miembro


class FormNombre(forms.Form):
    nombre = forms.CharField(label='Nombre y apellido', max_length=80)


class FormMail(forms.Form):
    email = forms.EmailField(label='Mail nuevo')
    actual = forms.CharField(label='Tu contraseña', strip=False,
                             widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}))

    def __init__(self, *args, usuario, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario

    def clean_actual(self):
        if not self.usuario.check_password(self.cleaned_data['actual']):
            raise forms.ValidationError('La contraseña no es correcta.')
        return self.cleaned_data['actual']

    def clean_email(self):
        email = normalizar_email(self.cleaned_data['email'])
        if Usuario.objects.filter(email=email).exclude(pk=self.usuario.pk).exists():
            raise forms.ValidationError('Ese mail ya lo usa otra cuenta.')
        return email


class FormClave(PasswordChangeForm):
    field_order = ['old_password', 'new_password1', 'new_password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['old_password'].label = 'Contraseña actual'
        self.fields['new_password1'].label = 'Contraseña nueva'
        self.fields['new_password1'].help_text = password_validation.password_validators_help_text_html()
        self.fields['new_password2'].label = 'Repetí la contraseña nueva'


class FormMiPin(forms.Form):
    actual = forms.CharField(label='PIN actual', widget=forms.PasswordInput(attrs={'inputmode': 'numeric',
                                                                                  'autocomplete': 'off'}))
    pin = CampoPin(label='PIN nuevo (4 a 6 números)')
    repetido = forms.CharField(label='Repetí el PIN nuevo', widget=forms.TextInput(attrs={'inputmode': 'numeric',
                                                                                         'autocomplete': 'off'}))

    def __init__(self, *args, membresia, **kwargs):
        super().__init__(*args, **kwargs)
        self.membresia = membresia
        if not membresia.pin:                  # todavía no tiene: no hay actual que pedir
            del self.fields['actual']

    def clean_actual(self):
        if not check_password(self.cleaned_data['actual'], self.membresia.pin):
            raise forms.ValidationError('El PIN actual no es correcto.')
        return self.cleaned_data['actual']

    def clean(self):
        datos = super().clean()
        if datos.get('pin') and datos.get('pin') != datos.get('repetido'):
            self.add_error('repetido', 'No coincide con el PIN nuevo.')
        return datos


@miembro
def mi_cuenta(request, taller):
    u, m = request.user, request.membresia
    con_mail = bool(u.email)
    con_clave = u.has_usable_password()
    # nombre (y, si entra con usuario y PIN, también el usuario)
    form_datos = FormNombre(initial={'nombre': u.nombre}) if con_mail else FormDatosPin(usuario=u)
    form_mail = FormMail(usuario=u) if con_clave else None
    form_clave = FormClave(u) if con_clave else None
    form_pin = FormMiPin(membresia=m) if m.usa_pin else None
    volver = redirect(reverse('taller:cuenta', kwargs={'taller': taller}))
    if request.method == 'POST':
        accion = request.POST.get('accion')
        if accion == 'datos':
            form_datos = FormNombre(request.POST) if con_mail else FormDatosPin(request.POST, usuario=u)
            if form_datos.is_valid():
                u.nombre = form_datos.cleaned_data['nombre'].strip()
                campos = ['nombre']
                if not con_mail:
                    u.usuario = form_datos.cleaned_data['usuario']
                    campos.append('usuario')
                u.save(update_fields=campos)
                messages.success(request, 'Guardaste tus datos.')
                return volver
        elif accion == 'mail' and form_mail is not None:
            form_mail = FormMail(request.POST, usuario=u)
            if form_mail.is_valid():
                u.email = form_mail.cleaned_data['email']
                u.save(update_fields=['email'])
                messages.success(request, f'Desde ahora entrás con {u.email}.')
                return volver
        elif accion == 'clave' and form_clave is not None:
            form_clave = FormClave(u, request.POST)
            if form_clave.is_valid():
                form_clave.save()
                update_session_auth_hash(request, u)          # que no se cierre la sesión
                messages.success(request, 'Cambiaste tu contraseña.')
                return volver
        elif accion == 'pin' and form_pin is not None:
            form_pin = FormMiPin(request.POST, membresia=m)
            if form_pin.is_valid():
                pines.asignar_pin(m, form_pin.cleaned_data['pin'])
                messages.success(request, f'Cambiaste tu PIN en {request.taller.nombre}.')
                return volver
        elif accion == 'quitar_llave':
            borradas, _ = u.llaves.filter(pk=request.POST.get('llave') or 0).delete()
            if borradas:
                messages.success(request, 'Quitaste la huella de ese celular.')
            return volver
    talleres = mis_talleres(request)
    return render(request, 'talleres/cuenta.html', {
        'form_datos': form_datos, 'form_mail': form_mail, 'form_clave': form_clave, 'form_pin': form_pin,
        'llaves': list(u.llaves.all()), 'talleres': talleres,
        'celular_propio': equipo_celular.leer(request)['tipo'] == equipo_celular.PROPIO,
    }, status=400 if request.method == 'POST' else 200)
