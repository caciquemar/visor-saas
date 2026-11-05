"""Administración del servicio (Martín): planes, cotización del dólar, la suscripción de cada taller y los pagos.
Ve todos los talleres, por eso lee con `sin_filtro`; para guardar, entra al taller del dato (con_taller)."""
from django import forms
from django.contrib import admin, messages
from django.utils import timezone

from talleres.limites import FUNCIONES, NOMBRES
from talleres.separacion import con_taller

from . import estados
from .models import Cotizacion, Pago, Plan, Suscripcion
from .servicio import aprobar


class FormPlan(forms.ModelForm):
    funciones = forms.MultipleChoiceField(label='funciones', required=False, widget=forms.CheckboxSelectMultiple,
                                          choices=[(f, NOMBRES[f]) for f in FUNCIONES])

    class Meta:
        model = Plan
        fields = ('nombre', 'clave', 'precio_usd', 'max_proyectos', 'max_usuarios', 'funciones', 'orden', 'a_la_venta')


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    form = FormPlan
    list_display = ('nombre', 'precio_usd', 'max_proyectos', 'max_usuarios', 'orden', 'a_la_venta')


@admin.register(Cotizacion)
class CotizacionAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'ars_por_usd', 'fuente', 'creada')
    fields = ('fecha', 'ars_por_usd')

    def save_model(self, request, obj, form, change):
        obj.fuente = Cotizacion.Fuente.MANUAL
        super().save_model(request, obj, form, change)


class DelTaller(admin.ModelAdmin):
    """Datos de un taller: se leen sin filtro y se guardan dentro de su taller."""

    def get_queryset(self, request):
        return self.model.sin_filtro.select_related('taller')

    def save_model(self, request, obj, form, change):
        with con_taller(obj.taller):
            super().save_model(request, obj, form, change)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Suscripcion)
class SuscripcionAdmin(DelTaller):
    list_display = ('taller', 'plan', 'estado_hoy', 'prueba_hasta', 'pagado_hasta', 'sin_cobro_hasta')
    list_filter = ('estado', 'plan')
    search_fields = ('taller__nombre', 'taller__slug')
    fields = ('taller', 'plan', 'plan_proximo', 'cambio_de_plan', 'prueba_hasta', 'pagado_hasta', 'sin_cobro_hasta',
              'estado', 'estado_desde', 'avisos')
    readonly_fields = ('taller', 'estado', 'estado_desde', 'avisos')

    @admin.display(description='estado hoy')
    def estado_hoy(self, obj):
        return estados.NOMBRES[estados.estado(obj, timezone.localdate())]


@admin.register(Pago)
class PagoAdmin(DelTaller):
    list_display = ('creado', 'taller', 'plan', 'periodo', 'monto_ars', 'estado', 'pasarela', 'nota')
    list_filter = ('estado', 'pasarela', 'periodo')
    search_fields = ('taller__nombre', 'codigo', 'id_externo')
    readonly_fields = [f.name for f in Pago._meta.fields if f.name != 'nota'] + ['taller']
    actions = ['aprobar_a_mano']

    @admin.action(description='Aprobar a mano (pago confirmado en Payway o por transferencia)')
    def aprobar_a_mano(self, request, queryset):
        hechos = 0
        for pago in queryset.filter(estado__in=[Pago.Estado.PENDIENTE, Pago.Estado.VENCIDO]):
            with con_taller(pago.taller):
                if pago.estado == Pago.Estado.VENCIDO:
                    Pago.objects.filter(pk=pago.pk).update(estado=Pago.Estado.PENDIENTE)
                aprobar(pago, nota=f'Aprobado a mano por {request.user}')
            hechos += 1
        messages.info(request, f'Pagos aprobados: {hechos}.')
