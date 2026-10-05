"""Conversor de proyectos de Polyboard (DXF 3D + lista de OptiCut) al formato del visor.

    from conversor import convertir, ErrorConversion
    r = convertir('cocina.dxf', ['cocina.ocp'], 'salida/')
"""
from .polyboard_a_app import ErrorConversion, Resultado, convertir

__all__ = ['convertir', 'ErrorConversion', 'Resultado']
