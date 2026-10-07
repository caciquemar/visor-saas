"""La carpeta del postprocesador de Polyboard llega como ZIP (si se arrastra la carpeta, el navegador arma el ZIP).
Acá se revisa y se descomprime sin confiar en lo que trae: nada fuera de la carpeta destino, solo DXF, con tope de
cantidad y de tamaño descomprimido."""
import posixpath
import shutil
import zipfile
from pathlib import Path

MAX_ARCHIVOS = 2000
MAX_DESCOMPRIMIDO_MB = 500


class ZipInvalido(ValueError):
    pass


def ruta_segura(nombre):
    """'Rack/c-guatambu_19 mm/0005.dxf' -> ['Rack', 'c-guatambu_19 mm', '0005.dxf']; None si es peligrosa."""
    nombre = nombre.replace('\\', '/')
    if nombre.startswith('/') or ':' in nombre or '\x00' in nombre:
        return None
    partes = [p for p in nombre.split('/') if p not in ('', '.')]
    if not partes or '..' in partes:
        return None
    return partes


def dxfs_del_zip(zf):
    """[(info, partes)] de los DXF del ZIP. Lanza ZipInvalido con un mensaje para el taller."""
    infos = zf.infolist()
    if len(infos) > MAX_ARCHIVOS:
        raise ZipInvalido(f'La carpeta tiene más de {MAX_ARCHIVOS} archivos. Subí solo la carpeta del '
                          'postprocesador de este proyecto.')
    dxfs, total = [], 0
    for info in infos:
        if info.is_dir():
            continue
        partes = ruta_segura(info.filename)
        if partes is None:
            raise ZipInvalido('El ZIP tiene archivos con rutas raras. Comprimí de nuevo la carpeta del '
                              'postprocesador.')
        if not partes[-1].lower().endswith('.dxf'):
            continue
        total += info.file_size
        dxfs.append((info, partes))
    if total > MAX_DESCOMPRIMIDO_MB * 1024 * 1024:
        raise ZipInvalido('La carpeta es demasiado grande. Subí solo la carpeta del postprocesador de este proyecto.')
    if not dxfs:
        raise ZipInvalido('No hay ningún DXF en la carpeta. Tiene que ser la carpeta que genera Polyboard en '
                          '"Exportar a postprocesador" (una subcarpeta por material con un DXF por pieza).')
    return dxfs


def carpeta_raiz(dxfs):
    """Si todo está dentro de una carpeta (la del proyecto: <proyecto>/<material>/<pieza>.dxf), su nombre; si no
    (se comprimieron directamente las carpetas de los materiales), None."""
    primeras = {partes[0] for _, partes in dxfs}
    if len(primeras) == 1 and all(len(partes) >= 3 for _, partes in dxfs):
        return primeras.pop()
    return None


def revisar(archivo):
    """Para el formulario: el archivo subido es un ZIP con DXF. Devuelve el nombre de la carpeta raíz (o None)."""
    try:
        with zipfile.ZipFile(archivo) as zf:
            return carpeta_raiz(dxfs_del_zip(zf))
    except zipfile.BadZipFile:
        raise ZipInvalido('El archivo no es un ZIP o está dañado. Comprimí de nuevo la carpeta del postprocesador.')
    finally:
        archivo.seek(0)


def extraer(ruta_zip, destino):
    """Descomprime solo los DXF en `destino`, sin la carpeta raíz. Devuelve el nombre de esa carpeta (o None)."""
    destino = Path(destino)
    with zipfile.ZipFile(ruta_zip) as zf:
        dxfs = dxfs_del_zip(zf)
        raiz = carpeta_raiz(dxfs)
        for info, partes in dxfs:
            if raiz is not None:
                partes = partes[1:]
            final = destino.joinpath(*partes)
            if not final.resolve().is_relative_to(destino.resolve()):
                raise ZipInvalido('El ZIP tiene archivos con rutas raras.')
            final.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as origen, open(final, 'wb') as f:
                shutil.copyfileobj(origen, f, 1024 * 1024)
    return raiz


def comprimir(carpeta, ruta_zip, raiz):
    """ZIP del resultado con la misma forma que en la PC: <raiz>/<material>/<pieza>.dxf, en orden fijo."""
    carpeta = Path(carpeta)
    with zipfile.ZipFile(ruta_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(p for p in carpeta.rglob('*') if p.is_file()):
            nombre = posixpath.join(raiz, f.relative_to(carpeta).as_posix())
            info = zipfile.ZipInfo(nombre, date_time=(2000, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, f.read_bytes())
