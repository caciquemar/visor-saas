"""Catálogo de módulos. Qué taller tiene cuál se prende en la ficha de cada taller (talleres/admin.py)."""
from django.contrib import admin

from . import registro
from .models import Modulo


@admin.register(Modulo)
class ModuloAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'clave', 'disponible')
    readonly_fields = ('clave',)

    @admin.display(description='disponible en el servidor', boolean=True)
    def disponible(self, obj):
        m = registro.registrados().get(obj.clave)
        return bool(m and m.disponible())

    def has_add_permission(self, request):
        return False            # los crea una migración: un módulo sin código no hace nada

    def has_delete_permission(self, request, obj=None):
        return False
