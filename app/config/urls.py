from django.contrib import admin
from django.contrib.auth import views as auth
from django.urls import include, path, reverse_lazy

from talleres import cuentas

admin.site.site_header = 'Visor · administración'
admin.site.site_title = 'Visor'

# Lo que no es un taller va primero, y su primera parte está en talleres.models.RESERVADOS.
urlpatterns = [
    path('', cuentas.inicio, name='inicio'),
    path('admin/', admin.site.urls),
    path('entrar/', auth.LoginView.as_view(template_name='cuentas/entrar.html', redirect_authenticated_user=True),
         name='entrar'),
    path('salir/', cuentas.salir, name='salir'),
    path('cuenta/olvide/', auth.PasswordResetView.as_view(
        template_name='cuentas/olvide.html', email_template_name='cuentas/mail_clave.txt',
        subject_template_name='cuentas/mail_clave_asunto.txt', success_url=reverse_lazy('olvide_enviado')),
        name='olvide'),
    path('cuenta/olvide/enviado/', auth.PasswordResetDoneView.as_view(template_name='cuentas/olvide_enviado.html'),
         name='olvide_enviado'),
    path('cuenta/clave/<uidb64>/<token>/', auth.PasswordResetConfirmView.as_view(
        template_name='cuentas/clave_nueva.html', success_url=reverse_lazy('clave_lista')), name='clave_nueva'),
    path('cuenta/clave/lista/', auth.PasswordResetCompleteView.as_view(template_name='cuentas/clave_lista.html'),
         name='clave_lista'),
    path('cuenta/invitacion/<str:token>/', cuentas.invitacion, name='invitacion'),
    path('c/', include('proyectos.urls_cliente')),          # link del cliente, sin login
    path('<slug:taller>/', include('talleres.urls')),
]
