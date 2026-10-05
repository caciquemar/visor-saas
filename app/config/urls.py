from django.contrib import admin
from django.urls import path

admin.site.site_header = 'Visor · administración'
admin.site.site_title = 'Visor'

urlpatterns = [
    path('admin/', admin.site.urls),
]
