from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm

from .models import Usuario


class FormAltaUsuario(AdminUserCreationForm):
    class Meta:
        model = Usuario
        fields = ('email', 'nombre')


class FormUsuario(UserChangeForm):
    class Meta:
        model = Usuario
        fields = '__all__'


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    form = FormUsuario
    add_form = FormAltaUsuario
    ordering = ('nombre', 'email')
    list_display = ('nombre', 'email', 'is_staff', 'is_active', 'last_login')
    list_filter = ('is_staff', 'is_superuser', 'is_active')
    search_fields = ('nombre', 'email')
    readonly_fields = ('last_login', 'creado')
    fieldsets = (
        (None, {'fields': ('email', 'nombre', 'password')}),
        ('Permisos', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Fechas', {'fields': ('last_login', 'creado')}),
    )
    add_fieldsets = (
        (None, {'classes': ('wide',), 'fields': ('email', 'nombre', 'usable_password', 'password1', 'password2')}),
    )
