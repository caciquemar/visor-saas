"""Administración del servicio (Martín): ve todos los talleres, por eso lee con `sin_filtro`.
Los dueños de los talleres no entran acá: usan Equipo dentro de su taller."""
from django import forms
from django.contrib import admin, messages
from django.contrib.admin.utils import unquote
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils.html import format_html

from modulos.models import TallerModulo

from .mails import invitar, reenviar
from .models import Invitacion, Membresia, Taller
from .separacion import con_taller


class MiembrosInline(admin.TabularInline):
    model = Membresia
    fields = readonly_fields = ('usuario', 'rol', 'activa', 'creada')
    extra = 0
    can_delete = False
    verbose_name_plural = 'miembros'

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return Membresia.sin_filtro.select_related('usuario')


class InvitacionesInline(admin.TabularInline):
    model = Invitacion
    fields = readonly_fields = ('email', 'rol', 'creada', 'vence', 'usada', 'reenviar')
    extra = 0
    can_delete = False
    verbose_name_plural = 'invitaciones'

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return Invitacion.sin_filtro.all()

    @admin.display(description='')
    def reenviar(self, obj):
        """Botón solo en la última invitación sin usar de cada mail (al reenviar, la anterior queda anulada). Manda
        el formulario del taller a otra dirección (formaction): ver TallerAdmin.reenviar_invitacion."""
        if obj.pk is None or obj.usada is not None:
            return ''
        ultima = (Invitacion.sin_filtro.filter(taller_id=obj.taller_id, email=obj.email)
                  .order_by('-creada', '-pk').values_list('pk', flat=True).first())
        if ultima != obj.pk:
            return ''
        url = reverse('admin:talleres_taller_reenviar', args=[obj.taller_id, obj.pk])
        return format_html('<button type="submit" formaction="{}" formnovalidate class="button">Reenviar</button>',
                           url)


class ModulosInline(admin.TabularInline):
    """Módulos del taller (regla 3): se prenden acá, uno por fila. La configuración es JSON (por ahora ninguno
    la usa)."""
    model = TallerModulo
    fields = ('modulo', 'prendido', 'configuracion')
    extra = 0
    verbose_name_plural = 'módulos'

    def get_queryset(self, request):
        return TallerModulo.sin_filtro.select_related('modulo')


class FormTaller(forms.ModelForm):
    email_dueno = forms.EmailField(label='Mail del dueño', required=False,
                                   help_text='Le llega una invitación para entrar como dueño.')

    class Meta:
        model = Taller
        fields = ('nombre', 'slug', 'activo')


@admin.register(Taller)
class TallerAdmin(admin.ModelAdmin):
    form = FormTaller
    list_display = ('nombre', 'slug', 'activo', 'miembros', 'creado')
    search_fields = ('nombre', 'slug')
    prepopulated_fields = {'slug': ('nombre',)}

    @admin.display(description='miembros activos')
    def miembros(self, obj):
        return Membresia.sin_filtro.filter(taller=obj, activa=True).count()

    def get_fields(self, request, obj=None):
        return ('nombre', 'slug', 'activo', 'email_dueno')

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['email_dueno'].required = obj is None
        form.base_fields['email_dueno'].label = 'Mail del dueño' if obj is None else 'Invitar otro dueño'
        return form

    def get_inlines(self, request, obj):
        return [ModulosInline, MiembrosInline, InvitacionesInline] if obj else []

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        taller = None
        if object_id:
            try:
                taller = Taller.objects.filter(pk=unquote(object_id)).first()
            except (ValueError, TypeError):
                taller = None
        if taller is None:
            return super().changeform_view(request, object_id, form_url, extra_context)
        with con_taller(taller):          # los formularios de miembros validan dentro del taller
            respuesta = super().changeform_view(request, object_id, form_url, extra_context)
            if hasattr(respuesta, 'render'):
                respuesta.render()
            return respuesta

    def get_urls(self):
        propias = [path('<int:taller_id>/reenviar-invitacion/<int:inv_id>/',
                        self.admin_site.admin_view(self.reenviar_invitacion), name='talleres_taller_reenviar')]
        return propias + super().get_urls()

    def reenviar_invitacion(self, request, taller_id, inv_id):
        if request.method != 'POST' or not self.has_change_permission(request):
            raise PermissionDenied
        taller = get_object_or_404(Taller, pk=taller_id)
        with con_taller(taller):
            inv = get_object_or_404(Invitacion, pk=inv_id, usada__isnull=True)
            reenviar(taller, inv, request.user)
        messages.info(request, f'Se reenvió la invitación a {inv.email} (la anterior quedó anulada).')
        return redirect('admin:talleres_taller_change', taller.pk)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        email = form.cleaned_data.get('email_dueno')
        if email:
            with con_taller(obj):
                invitar(obj, email, Membresia.Rol.DUENO, request.user)
            messages.info(request, f'Se mandó la invitación de dueño a {email}.')
