#!/usr/bin/env python3
"""
api.py — Trabajos a realizar del visor de armado (sin dependencias: solo la biblioteca estándar).

    python api.py --datos DIR [--puerto 8000] [--estatico CARPETA]

Guarda los trabajos en DIR/trabajos.db (SQLite) y las fotos en DIR/fotos/.
En el NAS corre en su propio contenedor y nginx le pasa /api/. Para probar en la PC,
--estatico sirve además el visor (la carpeta "Visor armado"), sin nginx.

  GET    /api/trabajos?proyecto=P        lista del proyecto
  POST   /api/trabajos                   nuevo  {proyecto, texto, piezas, muebles, autor, asignado, limite}
  PATCH  /api/trabajos/<id>              cambia {texto, estado, asignado, limite, piezas, muebles, quien}
                                         estado: pendiente -> en proceso -> hecho (taller) -> instalado
  DELETE /api/trabajos/<id>
  POST   /api/trabajos/<id>/fotos        cuerpo = la imagen (image/jpeg, image/png o image/webp)
  DELETE /api/trabajos/<id>/fotos/<f>
  GET    /api/fotos/<f>
"""
import argparse, json, mimetypes, re, secrets, sqlite3, threading, time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ESTADOS = ('pendiente', 'en proceso', 'hecho', 'instalado')
MAX_FOTO = 12 * 1024 * 1024
MAX_JSON = 256 * 1024
TIPOS_FOTO = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp'}
CAMPOS_TEXTO = {'texto': 4000, 'autor': 80, 'asignado': 80, 'limite': 10, 'quien': 80}

class Base:
    def __init__(self, carpeta):
        self.carpeta = Path(carpeta)
        (self.carpeta / 'fotos').mkdir(parents=True, exist_ok=True)
        self.cx = sqlite3.connect(self.carpeta / 'trabajos.db', check_same_thread=False)
        self.cx.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.cx.execute("""create table if not exists trabajos(
                id integer primary key autoincrement, proyecto text not null, texto text not null,
                estado text not null default 'pendiente', autor text, asignado text,
                creado text not null, limite text, hecho_por text, hecho_en text,
                piezas text not null default '[]', muebles text not null default '[]',
                fotos text not null default '[]')""")
            self.cx.execute("create index if not exists t_proy on trabajos(proyecto)")
            # estados: pendiente -> en proceso -> hecho (en el taller) -> instalado
            cols = {r[1] for r in self.cx.execute("pragma table_info(trabajos)")}
            for c in ('iniciado_por', 'iniciado_en', 'instalado_por', 'instalado_en'):
                if c not in cols:
                    self.cx.execute(f"alter table trabajos add column {c} text")
            self.cx.commit()

    @staticmethod
    def dic(r):
        d = dict(r)
        for k in ('piezas', 'muebles', 'fotos'):
            d[k] = json.loads(d[k])
        return d

    def lista(self, proyecto):
        with self.lock:
            return [self.dic(r) for r in self.cx.execute(
                "select * from trabajos where proyecto=? order by case estado when 'pendiente' then 0 "
                "when 'en proceso' then 1 when 'hecho' then 2 else 3 end, id desc",
                (proyecto,))]

    def uno(self, i):
        with self.lock:
            r = self.cx.execute("select * from trabajos where id=?", (i,)).fetchone()
        return self.dic(r) if r else None

    def nuevo(self, d):
        with self.lock:
            c = self.cx.execute(
                "insert into trabajos(proyecto,texto,estado,autor,asignado,creado,limite,piezas,muebles) values(?,?,'pendiente',?,?,?,?,?,?)",
                (d['proyecto'], d['texto'], d.get('autor'), d.get('asignado'), time.strftime('%Y-%m-%d %H:%M'),
                 d.get('limite'), json.dumps(d.get('piezas', [])), json.dumps(d.get('muebles', []))))
            self.cx.commit()
            i = c.lastrowid
        return self.uno(i)

    def cambiar(self, i, d):
        t = self.uno(i)
        if not t:
            return None
        cambios = {k: d[k] for k in ('texto', 'asignado', 'limite') if k in d}
        for k in ('piezas', 'muebles'):
            if k in d:
                cambios[k] = json.dumps(d[k])
        e = d.get('estado')
        if e in ESTADOS and e != t['estado']:
            ahora, quien = time.strftime('%Y-%m-%d %H:%M'), d.get('quien')
            cambios['estado'] = e
            # quién y cuándo de cada paso: al avanzar se completan los pasos salteados con este mismo;
            # al volver atrás se borran los posteriores
            pasos = [('iniciado_por', 'iniciado_en'), ('hecho_por', 'hecho_en'), ('instalado_por', 'instalado_en')]
            n = ESTADOS.index(e)   # pasos cumplidos: pendiente 0, en proceso 1, hecho 2, instalado 3
            for j, (por, en) in enumerate(pasos):
                if j < n:
                    if j == n - 1 or not t[en]:
                        cambios.update({por: quien, en: ahora})
                else:
                    cambios.update({por: None, en: None})
        if cambios:
            with self.lock:
                self.cx.execute(f"update trabajos set {', '.join(k + '=?' for k in cambios)} where id=?", (*cambios.values(), i))
                self.cx.commit()
        return self.uno(i)

    def borrar(self, i):
        t = self.uno(i)
        if not t:
            return False
        for f in t['fotos']:
            (self.carpeta / 'fotos' / f).unlink(missing_ok=True)
        with self.lock:
            self.cx.execute("delete from trabajos where id=?", (i,))
            self.cx.commit()
        return True

    def agregar_foto(self, i, datos, tipo):
        t = self.uno(i)
        if not t:
            return None
        nombre = f"{i}-{secrets.token_hex(6)}{TIPOS_FOTO[tipo]}"
        (self.carpeta / 'fotos' / nombre).write_bytes(datos)
        with self.lock:
            self.cx.execute("update trabajos set fotos=? where id=?", (json.dumps(t['fotos'] + [nombre]), i))
            self.cx.commit()
        return self.uno(i)

    def quitar_foto(self, i, nombre):
        t = self.uno(i)
        if not t or nombre not in t['fotos']:
            return None
        (self.carpeta / 'fotos' / nombre).unlink(missing_ok=True)
        with self.lock:
            self.cx.execute("update trabajos set fotos=? where id=?", (json.dumps([f for f in t['fotos'] if f != nombre]), i))
            self.cx.commit()
        return self.uno(i)

def validar(d, nuevo):
    if not isinstance(d, dict):
        return 'se esperaba un objeto JSON'
    if nuevo and not (isinstance(d.get('proyecto'), str) and d['proyecto'].strip()):
        return 'falta el proyecto'
    if nuevo and not (isinstance(d.get('texto'), str) and d['texto'].strip()):
        return 'falta el texto'
    for k, n in CAMPOS_TEXTO.items():
        if k in d and d[k] is not None and not (isinstance(d[k], str) and len(d[k]) <= n):
            return f'{k} no válido'
    if d.get('limite') and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', d['limite']):
        return 'limite debe ser AAAA-MM-DD'
    if 'estado' in d and d['estado'] not in ESTADOS:
        return f"estado no válido (se espera: {', '.join(ESTADOS)})"
    for k in ('piezas', 'muebles'):
        if k in d and not (isinstance(d[k], list) and len(d[k]) <= 500 and all(isinstance(x, str) and len(x) <= 200 for x in d[k])):
            return f'{k} no válido'
    return None

def manejador(base, estatico):
    class H(SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=estatico or '.', **k)

        def log_message(self, fmt, *a):
            pass

        def responder(self, codigo, obj=None):
            cuerpo = json.dumps(obj, ensure_ascii=False).encode() if obj is not None else b''
            self.send_response(codigo)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

        def leer(self, maximo):
            n = int(self.headers.get('Content-Length') or 0)
            if n <= 0 or n > maximo:
                return None
            return self.rfile.read(n)

        def leer_json(self):
            b = self.leer(MAX_JSON)
            try:
                return json.loads(b) if b else None
            except ValueError:
                return None

        def ruta(self):
            u = urlparse(self.path)
            return u.path.rstrip('/'), parse_qs(u.query)

        def do_GET(self):
            ruta, q = self.ruta()
            if ruta == '/api/trabajos':
                return self.responder(200, base.lista((q.get('proyecto') or [''])[0]))
            m = re.fullmatch(r'/api/fotos/([\w.-]+)', ruta)
            if m:
                f = base.carpeta / 'fotos' / m.group(1)
                if not f.is_file():
                    return self.responder(404, {'error': 'no existe'})
                b = f.read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', mimetypes.guess_type(f.name)[0] or 'application/octet-stream')
                self.send_header('Cache-Control', 'public, max-age=31536000, immutable')
                self.send_header('Content-Length', str(len(b)))
                self.end_headers()
                return self.wfile.write(b)
            if ruta.startswith('/api/'):
                return self.responder(404, {'error': 'no existe'})
            if not estatico or re.search(r'(^|/)\.|\.(py|db)$', urlparse(self.path).path):
                return self.responder(404, {'error': 'no existe'})
            return super().do_GET()

        def do_POST(self):
            ruta, _ = self.ruta()
            if ruta == '/api/trabajos':
                d = self.leer_json()
                err = validar(d, True)
                return self.responder(400, {'error': err}) if err else self.responder(201, base.nuevo(d))
            m = re.fullmatch(r'/api/trabajos/(\d+)/fotos', ruta)
            if m:
                tipo = (self.headers.get('Content-Type') or '').split(';')[0].strip()
                if tipo not in TIPOS_FOTO:
                    return self.responder(415, {'error': 'formato de imagen no admitido'})
                b = self.leer(MAX_FOTO)
                if not b:
                    return self.responder(413, {'error': 'imagen vacía o demasiado grande'})
                t = base.agregar_foto(int(m.group(1)), b, tipo)
                return self.responder(200, t) if t else self.responder(404, {'error': 'no existe'})
            return self.responder(404, {'error': 'no existe'})

        def do_PATCH(self):
            ruta, _ = self.ruta()
            m = re.fullmatch(r'/api/trabajos/(\d+)', ruta)
            if not m:
                return self.responder(404, {'error': 'no existe'})
            d = self.leer_json()
            err = validar(d, False)
            if err:
                return self.responder(400, {'error': err})
            t = base.cambiar(int(m.group(1)), d)
            return self.responder(200, t) if t else self.responder(404, {'error': 'no existe'})

        def do_DELETE(self):
            ruta, _ = self.ruta()
            m = re.fullmatch(r'/api/trabajos/(\d+)/fotos/([\w.-]+)', ruta)
            if m:
                t = base.quitar_foto(int(m.group(1)), m.group(2))
                return self.responder(200, t) if t else self.responder(404, {'error': 'no existe'})
            m = re.fullmatch(r'/api/trabajos/(\d+)', ruta)
            if m and base.borrar(int(m.group(1))):
                return self.responder(204)
            return self.responder(404, {'error': 'no existe'})
    return H

def reiniciar_si_cambia(intervalo=30):
    """En el NAS este archivo llega por Nextcloud: si cambia, el servicio se reinicia solo con la
    versión nueva (si no, seguiría corriendo la vieja hasta reiniciar la app a mano)."""
    import os, sys
    yo = Path(__file__).resolve()
    antes = yo.stat().st_mtime
    def vigilar():
        while True:
            time.sleep(intervalo)
            try:
                ahora = yo.stat().st_mtime
                if ahora != antes and compile(yo.read_text(encoding='utf-8'), str(yo), 'exec'):
                    print('api.py cambió: reiniciando con la versión nueva', flush=True)
                    os.execv(sys.executable, [sys.executable, *sys.argv])
            except (OSError, SyntaxError, ValueError):
                pass   # a medio sincronizar o con errores: se reintenta en el próximo ciclo
    threading.Thread(target=vigilar, daemon=True).start()

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--datos', required=True, help='carpeta para trabajos.db y fotos/')
    ap.add_argument('--puerto', type=int, default=8000)
    ap.add_argument('--estatico', help='carpeta del visor para servirla también (pruebas en la PC)')
    a = ap.parse_args()
    srv = ThreadingHTTPServer(('0.0.0.0', a.puerto), manejador(Base(a.datos), a.estatico))
    reiniciar_si_cambia()
    print(f"API de trabajos en :{a.puerto}  datos: {a.datos}" + (f"  visor: {a.estatico}" if a.estatico else ''))
    srv.serve_forever()

if __name__ == '__main__':
    main()
