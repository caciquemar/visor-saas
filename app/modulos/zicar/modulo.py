"""Módulo Zicar (solo Nord Good): en la subida, la carpeta del postprocesador de Polyboard (ZIP o carpeta, que el
navegador comprime); en la conversión, pb2zicar (repo privado aparte, ver docs/decisiones.md); en el proyecto, el
botón "Descargar Zicar". Solo dueño y oficina, igual que subir proyectos."""
import importlib.util

from django import forms
from django.conf import settings
from django.template.loader import render_to_string

from modulos.registro import Modulo, registrar
from proyectos.archivos import solo_nombre
from proyectos.models import Original
from talleres.roles import Rol

from .zips import ZipInvalido, revisar

CAMPO = 'zicar'
GESTION = (Rol.DUENO, Rol.OFICINA)
MB = 1024 * 1024


class CampoCarpeta(forms.FileField):
    widget = forms.ClearableFileInput(attrs={'accept': '.zip'})

    def clean(self, data, initial=None):
        archivo = super().clean(data, initial)
        if not archivo:
            return None
        nombre = solo_nombre(archivo.name)
        if not nombre.lower().endswith('.zip'):
            raise forms.ValidationError(f'{nombre}: la carpeta del postprocesador va comprimida en ZIP (o arrastrá '
                                        'la carpeta y se comprime sola).')
        if archivo.size > settings.MAX_ZICAR_MB * MB:
            raise forms.ValidationError(f'{nombre} pesa {archivo.size // MB} MB; el máximo es '
                                        f'{settings.MAX_ZICAR_MB} MB.')
        try:
            revisar(archivo)
        except ZipInvalido as e:
            raise forms.ValidationError(str(e))
        return archivo


@registrar
class Zicar(Modulo):
    clave = 'zicar'

    def disponible(self):
        return importlib.util.find_spec('pb2zicar') is not None

    def campos_de_subida(self, form):
        form.fields[CAMPO] = CampoCarpeta(
            label='Carpeta del postprocesador (Zicar)', required=False,
            help_text='Opcional. La carpeta que genera Polyboard en "Exportar a postprocesador" (tipo DXF): '
                      'arrastrala o elegí el ZIP. Con ella se generan los DXF para la Zicar.')

    def html_de_subida(self, form):
        return render_to_string('zicar/subida.html', {'campo': form[CAMPO], 'max_mb': settings.MAX_ZICAR_MB})

    def al_guardar_version(self, version, datos):
        archivo = datos.get(CAMPO)
        if archivo:
            Original.objects.create(version=version, tipo=Original.Tipo.POSTPROCESADOR,
                                    nombre=solo_nombre(archivo.name)[:255], archivo=archivo, tamano=archivo.size)

    def al_encolar(self, version):
        from .tareas import encolar
        encolar(version)

    def en_proceso(self, version):
        resultado = self.resultado(version)
        return bool(resultado and resultado.en_proceso)

    def html_de_version(self, request, proyecto, version):
        if request.membresia is None or request.membresia.rol not in GESTION:
            return ''
        resultado = self.resultado(version)
        if resultado is None:
            return ''
        from .tareas import revisar_si_se_corto
        revisar_si_se_corto(resultado)
        return render_to_string('zicar/version.html', {'r': resultado, 'proyecto': proyecto, 'v': version},
                                request=request)

    def oculta_original(self, original):
        return original.tipo == Original.Tipo.POSTPROCESADOR

    @staticmethod
    def resultado(version):
        from .models import ResultadoZicar
        return ResultadoZicar.objects.filter(version=version).first()
