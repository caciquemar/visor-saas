"""Corre el conversor en un proceso aparte (lo lanza proyectos/tareas.py). No usa Django ni la base: recibe todo
en un JSON y deja el resultado en otro, así un proyecto que se cuelga o se come la memoria no tumba la cola.

    python -m proyectos.proceso entrada.json

entrada.json: {dxf, ocps, destino, texturas, biblioteca, codigo, memoria_mb, salida}
salida.json:  {proyecto, archivo, avisos, resumen, con_imagen}  o  {error: mensaje para el taller}
              o {memoria: true} si se quedó sin memoria.
con_imagen: materiales usados que en Polyboard tienen imagen,
            {'tableros': {nombre: [ruta en Polyboard, ancho en mm o null]}, 'cantos': {...}}.
"""
import json
import logging
import sys
from pathlib import Path


def limitar_memoria(mb):
    """Solo en Linux/macOS: tope de memoria del proceso. En Windows no hay `resource` y se sigue sin tope."""
    try:
        import resource
    except ImportError:
        return
    tope = int(mb) * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (tope, tope))


def materiales_con_imagen(archivo, ocps):
    """Tableros y cantos usados que en Polyboard tienen imagen, por separado (pueden llamarse igual)."""
    from conversor.polyboard_a_app import materiales_del_ocp

    datos = json.loads(Path(archivo).read_text(encoding='utf-8'))
    usados = {'tableros': {p['mat'] for p in datos['paneles'] if p['mat']},
              'cantos': {c['mat'] for p in datos['paneles'] for c in p['cantos'] if c['mat']}}
    con_imagen = {'tableros': {}, 'cantos': {}}
    for ocp in ocps:
        for tipo, mats in materiales_del_ocp(ocp).items():
            for nombre, info in mats.items():
                if nombre in usados[tipo] and info.get('textura') and nombre not in con_imagen[tipo]:
                    con_imagen[tipo][nombre] = list(info['textura'])
    return con_imagen


def main(ruta_entrada):
    e = json.loads(Path(ruta_entrada).read_text(encoding='utf-8'))
    salida = Path(e['salida'])
    if e.get('memoria_mb'):
        limitar_memoria(e['memoria_mb'])
    logging.basicConfig(level=logging.WARNING, format='%(message)s')

    from conversor import ErrorConversion, convertir
    try:
        r = convertir(e['dxf'], e['ocps'], e['destino'], e['texturas'], biblioteca=e['biblioteca'],
                      codigo=e['codigo'], sin_canto=e.get('sin_canto'))
        res = dict(proyecto=r.proyecto, archivo=r.archivo.name, avisos=r.avisos, resumen=r.resumen,
                   con_imagen=materiales_con_imagen(r.archivo, e['ocps']))
    except ErrorConversion as error:
        res = dict(error=str(error))
    except MemoryError:
        res = dict(memoria=True)
    res['memoria_mb'] = memoria_usada()
    salida.write_text(json.dumps(res, ensure_ascii=False), encoding='utf-8')
    return 0


def memoria_usada():
    """Solo en Linux: pico de memoria de este proceso en MB, {'real': VmHWM, 'reservada': VmPeak}. El tope de
    limitar_memoria() es sobre la reservada; el límite del contenedor (mem_limit), sobre la real."""
    try:
        estado = Path('/proc/self/status').read_text()
    except OSError:
        return None
    valores = {}
    for linea in estado.splitlines():
        campo, _, resto = linea.partition(':')
        if campo in ('VmHWM', 'VmPeak'):
            valores['real' if campo == 'VmHWM' else 'reservada'] = round(int(resto.split()[0]) / 1024)
    return valores or None


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
