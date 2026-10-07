from django.shortcuts import get_object_or_404

from modulos.registro import con_modulo
from talleres.archivos import abrir_de_taller
from talleres.roles import con_rol

from .models import ResultadoZicar
from .modulo import GESTION


@con_modulo('zicar')
@con_rol(*GESTION)
def descargar(request, taller, id, numero):
    r = get_object_or_404(ResultadoZicar, version__proyecto_id=id, version__numero=numero,
                          estado=ResultadoZicar.Estado.LISTO)
    return abrir_de_taller(request, r.archivo, descarga=True, nombre=r.nombre)
