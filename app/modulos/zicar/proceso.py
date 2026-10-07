"""Corre pb2zicar en un proceso aparte (lo lanza modulos/zicar/tareas.py), igual que proyectos/proceso.py: no usa
Django ni la base.

    python -m modulos.zicar.proceso entrada.json

entrada.json: {entrada, salida, resultado}
resultado:    {piezas, avisos: [texto], fallados: n}  o  {error: mensaje técnico (va al log)}
"""
import contextlib
import io
import json
import sys
from pathlib import Path


def main(ruta_entrada):
    e = json.loads(Path(ruta_entrada).read_text(encoding='utf-8'))
    from pb2zicar.cli import process_folder

    with contextlib.redirect_stdout(io.StringIO()):         # el CLI va contando pieza por pieza
        procesados, salteados, fallados, con_avisos = process_folder(Path(e['entrada']), Path(e['salida']))
    avisos = []
    for etiqueta, conteo in con_avisos:
        for mensaje, n in conteo.items():
            avisos.append(f'{Path(etiqueta).as_posix()}: {mensaje}' + (f' ({n} veces)' if n > 1 else ''))
    for etiqueta, _motivo in salteados:
        avisos.append(f'{Path(etiqueta).as_posix()}: no tiene la capa PANEL, se salteó')
    for etiqueta, error in fallados:
        print(f'{etiqueta}: {type(error).__name__}: {error}', file=sys.stderr)
        avisos.append(f'{Path(etiqueta).as_posix()}: no se pudo convertir, hay que hacerla a mano')
    Path(e['resultado']).write_text(json.dumps(dict(piezas=procesados, avisos=avisos, fallados=len(fallados)),
                                               ensure_ascii=False), encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
