from decimal import Decimal

from django import forms

from .models import FormatoEtiquetas

A4 = (Decimal(210), Decimal(297))


class FormFormato(forms.ModelForm):
    class Meta:
        model = FormatoEtiquetas
        fields = ['formato', 'ancho', 'alto', 'columnas', 'filas', 'margen_sup', 'margen_izq', 'sep_h', 'sep_v',
                  'ajuste_x', 'ajuste_y', 'bordes']

    LIMITES = {'ancho': (20, 210), 'alto': (15, 297), 'columnas': (1, 10), 'filas': (1, 30),
               'margen_sup': (0, 100), 'margen_izq': (0, 100), 'sep_h': (0, 50), 'sep_v': (0, 50),
               'ajuste_x': (-10, 10), 'ajuste_y': (-10, 10)}

    def clean(self):
        datos = super().clean()
        for campo, (menos, mas) in self.LIMITES.items():
            v = datos.get(campo)
            if v is not None and not menos <= v <= mas:
                self.add_error(campo, f'Tiene que estar entre {menos} y {mas}.')
        if self.errors:
            return datos
        if datos['formato'] == FormatoEtiquetas.MEDIDA_HOJA:
            ancho = datos['margen_izq'] + datos['columnas'] * datos['ancho'] + (datos['columnas'] - 1) * datos['sep_h']
            alto = datos['margen_sup'] + datos['filas'] * datos['alto'] + (datos['filas'] - 1) * datos['sep_v']
            if ancho > A4[0] + Decimal('0.5'):
                self.add_error('columnas', f'No entran en una hoja A4: ocupan {ancho:g} mm de ancho (hay 210).')
            if alto > A4[1] + Decimal('0.5'):
                self.add_error('filas', f'No entran en una hoja A4: ocupan {alto:g} mm de alto (hay 297).')
        return datos
