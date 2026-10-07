import re

from django import forms
from django.conf import settings

from .archivos import solo_nombre
from talleres.models import Taller

from .models import Material

MB = 1024 * 1024
DXF_TEXTO = re.compile(rb'^(\xef\xbb\xbf)?\s*0\s*\r?\n\s*SECTION\b')
DXF_BINARIO = b'AutoCAD Binary DXF'


class SubidaMultiple(forms.ClearableFileInput):
    allow_multiple_selected = True


class CampoArchivos(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('widget', SubidaMultiple(attrs={'accept': '.dxf,.ocp'}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        limpiar = super().clean
        if isinstance(data, (list, tuple)) and data:
            return [limpiar(d, initial) for d in data]
        return [limpiar(data, initial)]


def comienzo(archivo, n=512):
    archivo.seek(0)
    datos = archivo.read(n)
    archivo.seek(0)
    return datos


class FormSubida(forms.Form):
    """Un DXF 3D y uno o varios .ocp. Se controla tipo, tamaño y que el contenido sea lo que dice ser."""
    archivos = CampoArchivos(label='Archivos del proyecto',
                             help_text='El DXF 3D y la lista de OptiCut (.ocp) exportados de Polyboard. '
                                       'Si el proyecto está dividido, todos los .ocp.')

    def clean_archivos(self):
        archivos = self.cleaned_data['archivos']
        dxfs, ocps, errores = [], [], []
        for a in archivos:
            nombre = solo_nombre(a.name)
            extension = nombre.rsplit('.', 1)[-1].lower() if '.' in nombre else ''
            if extension == 'dxf':
                if a.size > settings.MAX_DXF_MB * MB:
                    errores.append(f'{nombre} pesa {a.size // MB} MB; el máximo es {settings.MAX_DXF_MB} MB.')
                else:
                    datos = comienzo(a)
                    if not (DXF_TEXTO.match(datos) or datos.startswith(DXF_BINARIO)):
                        errores.append(f'{nombre} no es un DXF. Exportalo de nuevo desde Polyboard (DXF 3D).')
                dxfs.append(a)
            elif extension == 'ocp':
                if a.size > settings.MAX_OCP_MB * MB:
                    errores.append(f'{nombre} pesa {a.size // MB} MB; el máximo es {settings.MAX_OCP_MB} MB.')
                elif b'BZh9' not in comienzo(a):
                    errores.append(f'{nombre} no parece una lista de OptiCut o está dañada. '
                                   'Exportala de nuevo desde Polyboard.')
                ocps.append(a)
            else:
                errores.append(f'{nombre}: solo se suben el DXF 3D (.dxf) y la lista de OptiCut (.ocp).')
        if not dxfs:
            errores.append('Falta el DXF 3D del proyecto.')
        elif len(dxfs) > 1:
            errores.append('Subí un solo DXF por proyecto (el 3D completo).')
        if not ocps:
            errores.append('Falta la lista de OptiCut (.ocp) del proyecto.')
        if errores:
            raise forms.ValidationError(errores)
        return dxfs[0], ocps


class FormProyectoNuevo(FormSubida):
    nombre = forms.CharField(label='Nombre del proyecto', max_length=150, required=False,
                             help_text='Si lo dejás vacío, se usa el nombre del DXF.')
    field_order = ['nombre', 'archivos']


class FormMaterial(forms.ModelForm):
    class Meta:
        model = Material
        fields = ('textura', 'ancho_mm', 'color')
        widgets = {'color': forms.TextInput(attrs={'placeholder': '#A1B2C3', 'size': 8}),
                   'textura': forms.FileInput(attrs={'accept': 'image/jpeg,image/png,image/webp'})}
        help_texts = {'ancho_mm': 'Cuántos milímetros del material cubre la imagen a lo ancho. '
                                  'Si no lo sabés, dejalo vacío (se usa 1 metro).',
                      'color': 'Opcional: el color que se ve si no hay textura (o en lugar del de Polyboard).'}

    def clean_textura(self):
        textura = self.cleaned_data.get('textura')
        if textura and hasattr(textura, 'size'):
            if textura.size > settings.MAX_TEXTURA_MB * MB:
                raise forms.ValidationError(f'La imagen pesa {textura.size // MB} MB; el máximo es '
                                            f'{settings.MAX_TEXTURA_MB} MB.')
            formato = getattr(getattr(textura, 'image', None), 'format', None)
            if formato not in ('JPEG', 'PNG', 'WEBP'):
                raise forms.ValidationError('Subí la imagen en JPG, PNG o WEBP.')
        return textura

    def clean_color(self):
        color = (self.cleaned_data.get('color') or '').strip()
        if color and not re.fullmatch(r'#[0-9A-Fa-f]{6}', color):
            raise forms.ValidationError('El color tiene que ser como #A1B2C3.')
        return color.upper()


class FormSinCanto(forms.ModelForm):
    class Meta:
        model = Taller
        fields = ('color_sin_canto',)
        widgets = {'color_sin_canto': forms.TextInput(attrs={'type': 'color'})}

    def clean_color_sin_canto(self):
        color = (self.cleaned_data.get('color_sin_canto') or '').strip().upper()
        if not re.fullmatch(r'#[0-9A-F]{6}', color):
            raise forms.ValidationError('El color tiene que ser como #B58F63.')
        return color
