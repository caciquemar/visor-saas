"""Proyectos de Polyboard subidos por el taller. Cada subida es una Version con sus archivos originales; el conversor
corre en la cola (proyectos/tareas.py) y deja el resultado en la carpeta de la versión (proyectos/archivos.py).
Material es la biblioteca de texturas del taller (lo que en el visor actual es materiales.json)."""
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from conversor.polyboard_a_app import clave as clave_de_material, veta_de_imagen
from talleres.archivos import ruta_de_taller
from talleres.separacion import DatoDeTaller

from .archivos import carpeta_de_version, ruta_original


def codigo_nuevo():
    return secrets.token_urlsafe(9)


def codigo_de_link():
    return secrets.token_urlsafe(16)          # 128 bits: no se adivina


def para_produccion(qs):
    """Los proyectos que se ven en producción (Mi puesto, Tablero, visor del taller, Tareas): habilitados y sin
    archivar (ficha 22). Los que están en desarrollo siguen andando en el link del cliente."""
    return qs.filter(en_produccion=True, archivado_en__isnull=True)


class Proyecto(DatoDeTaller):
    nombre = models.CharField('nombre', max_length=150)
    # Para la etiqueta de cada bulto (ficha 12); no los ve el cliente.
    cliente = models.CharField('cliente', max_length=150, blank=True)
    direccion = models.CharField('dirección de entrega', max_length=200, blank=True)
    # Datos del proyecto (ficha 22): tampoco los ve el cliente.
    telefono = models.CharField('teléfono', max_length=40, blank=True)
    mail = models.EmailField('mail', blank=True)
    pedido = models.CharField('número de pedido', max_length=40, blank=True)
    entrega = models.DateField('entrega comprometida', null=True, blank=True)
    notas = models.TextField('notas', max_length=4000, blank=True)
    # En desarrollo (False): no aparece en producción. Archivado: tampoco, y sale de la lista de proyectos.
    en_produccion = models.BooleanField('en producción', default=False)
    archivado_en = models.DateTimeField('archivado', null=True, blank=True)
    archivado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name='+')
    # Código del link del cliente (ficha 04). Se pasa al conversor en cada versión para que el link no cambie.
    codigo_cliente = models.CharField('código del cliente', max_length=32, unique=True, default=codigo_nuevo,
                                      editable=False)
    version_actual = models.ForeignKey('Version', on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='+', verbose_name='versión actual')
    creado = models.DateTimeField('creado', auto_now_add=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='+')
    actualizado = models.DateTimeField('actualizado', auto_now=True)

    class Meta:
        verbose_name = 'proyecto'
        verbose_name_plural = 'proyectos'
        ordering = ['-actualizado']

    def __str__(self):
        return self.nombre

    def ultima_version(self):
        return self.versiones.order_by('-numero').first()

    @property
    def en_desarrollo(self):
        return not self.en_produccion and self.archivado_en is None

    @property
    def estado(self):
        return 'archivado' if self.archivado_en else 'produccion' if self.en_produccion else 'desarrollo'

    def get_estado_display(self):
        return {'archivado': 'Archivado', 'produccion': 'En producción', 'desarrollo': 'En desarrollo'}[self.estado]


class Version(DatoDeTaller):
    class Estado(models.TextChoices):
        EN_COLA = 'en_cola', 'En cola'
        CONVIRTIENDO = 'convirtiendo', 'Convirtiendo'
        LISTO = 'listo', 'Listo'
        ERROR = 'error', 'Error'

    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name='versiones')
    numero = models.PositiveIntegerField('número')
    estado = models.CharField('estado', max_length=12, choices=Estado.choices, default=Estado.EN_COLA)
    mensaje = models.TextField('mensaje de error', blank=True)
    avisos = models.JSONField('avisos', default=list, blank=True)
    resumen = models.JSONField('resumen', default=dict, blank=True)
    faltan_texturas = models.JSONField('materiales sin textura', default=list, blank=True)
    archivo_proyecto = models.CharField('JSON del proyecto', max_length=400, blank=True)
    subida_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='+')
    creada = models.DateTimeField('creada', auto_now_add=True)
    empezada = models.DateTimeField('empezada', null=True, blank=True)
    terminada = models.DateTimeField('terminada', null=True, blank=True)

    class Meta:
        verbose_name = 'versión'
        verbose_name_plural = 'versiones'
        ordering = ['-numero']
        constraints = [models.UniqueConstraint(fields=['proyecto', 'numero'], name='un_numero_por_proyecto')]

    def __str__(self):
        return f'{self.proyecto} v{self.numero}'

    def carpeta(self):
        return carpeta_de_version(self)

    @property
    def en_proceso(self):
        return self.estado in (self.Estado.EN_COLA, self.Estado.CONVIRTIENDO)

    def revisar_si_se_corto(self):
        """Si el consumidor de la cola se cayó a mitad de una conversión, la versión quedaría 'convirtiendo' para
        siempre: pasado el límite de tiempo (con margen) se marca como error."""
        limite = timedelta(seconds=settings.CONVERSION_SEGUNDOS + 300)
        if self.estado == self.Estado.CONVIRTIENDO and self.empezada and timezone.now() - self.empezada > limite:
            self.estado = self.Estado.ERROR
            self.mensaje = 'Se cortó la conversión. Probá "Volver a convertir"; si vuelve a pasar, avisanos.'
            self.terminada = timezone.now()
            self.save(update_fields=['estado', 'mensaje', 'terminada'])


class Original(DatoDeTaller):
    class Tipo(models.TextChoices):
        DXF = 'dxf', 'DXF 3D'
        OCP = 'ocp', 'Lista de OptiCut'
        POSTPROCESADOR = 'zip', 'Carpeta del postprocesador'      # módulo Zicar

    version = models.ForeignKey(Version, on_delete=models.CASCADE, related_name='originales')
    tipo = models.CharField('tipo', max_length=3, choices=Tipo.choices)
    nombre = models.CharField('nombre', max_length=255)       # como lo subió el taller
    archivo = models.FileField('archivo', upload_to=ruta_original, max_length=400)
    tamano = models.PositiveBigIntegerField('tamaño', default=0)

    class Meta:
        verbose_name = 'archivo original'
        verbose_name_plural = 'archivos originales'
        ordering = ['tipo', 'nombre']

    def __str__(self):
        return self.nombre


VETAS = [('', 'Automática'), ('h', 'Horizontal'), ('v', 'Vertical'), ('n', 'Sin veta')]


class Material(DatoDeTaller):
    """Un tablero o un canto. Van separados porque muchos se llaman igual y tienen otra imagen."""
    class Tipo(models.TextChoices):
        TABLERO = 'tablero', 'Tablero'
        CANTO = 'canto', 'Canto'

    tipo = models.CharField('tipo', max_length=7, choices=Tipo.choices, default=Tipo.TABLERO, editable=False)
    nombre = models.CharField('nombre', max_length=200)
    clave = models.CharField(max_length=200, editable=False)       # sin mayúsculas ni acentos, como el conversor
    ruta_polyboard = models.CharField('imagen en Polyboard', max_length=300, blank=True)
    ancho_mm = models.PositiveIntegerField('ancho que cubre la imagen (mm)', null=True, blank=True)
    color = models.CharField('color', max_length=7, blank=True)
    textura = models.ImageField('textura', upload_to=ruta_de_taller, blank=True, max_length=300)
    # Hacia dónde van las fibras en la imagen subida. Automática: la adivina veta_de_imagen al subirla y queda en
    # veta_detectada, así la flecha de Materiales muestra lo mismo que hace el conversor.
    veta = models.CharField('veta de la imagen', max_length=1, blank=True, choices=VETAS)
    veta_detectada = models.CharField(max_length=1, blank=True, editable=False)
    proporcion = models.FloatField(null=True, blank=True, editable=False)    # alto / ancho de la imagen
    creado = models.DateTimeField('creado', auto_now_add=True)
    actualizado = models.DateTimeField('actualizado', auto_now=True)

    class Meta:
        verbose_name = 'material'
        verbose_name_plural = 'materiales'
        ordering = ['tipo', 'nombre']
        constraints = [models.UniqueConstraint(fields=['taller', 'tipo', 'clave'], name='un_material_por_tipo_y_nombre')]

    def __str__(self):
        return f'{self.get_tipo_display().lower()} {self.nombre}'

    @property
    def falta(self):
        """Sin imagen ni color. Con color definido no lleva textura (decisión de Martín): no falta nada."""
        return not self.textura and not self.color

    @property
    def veta_efectiva(self):
        """'h', 'v' o 'n' (sin veta); '' si no hay imagen o no se pudo leer."""
        return (self.veta or self.veta_detectada) if self.textura else ''

    def save(self, *args, **kwargs):
        self.clave = clave_de_material(self.nombre)
        if not self.textura:
            self.veta_detectada, self.proporcion = '', None
        elif not self.textura._committed:          # imagen recién subida
            analizar_textura(self, self.textura)
        super().save(*args, **kwargs)


def analizar_textura(material, archivo):
    """Llena veta_detectada y proporcion con la imagen. Si no se puede leer, quedan vacías (la flecha no sale)."""
    from PIL import Image, UnidentifiedImageError
    try:
        archivo.seek(0)
        with Image.open(archivo) as im:
            material.proporcion = im.height / im.width
            im.draft('RGB', (1024, 1024))          # JPEG grande: se lee achicado, no ocupa memoria de más
            im.thumbnail((512, 512))               # veta_de_imagen mira 256 px igual
            material.veta_detectada = veta_de_imagen(im.convert('RGB'))
    except (OSError, ValueError, UnidentifiedImageError):
        material.veta_detectada, material.proporcion = '', None
    finally:
        archivo.seek(0)


class LinkCliente(DatoDeTaller):
    """Link para el cliente final: /c/<código>. Muestra la versión cliente de la versión actual del proyecto (sin
    números de mecanizado ni datos de taller). El código es otro que `Proyecto.codigo_cliente` (el que usa el
    conversor para nombrar los archivos): anular un link y crear otro no obliga a reconvertir."""
    DIAS = 90

    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name='links')
    codigo = models.CharField('código', max_length=32, unique=True, default=codigo_de_link, editable=False)
    vence = models.DateTimeField('vence', null=True, blank=True)
    anulado = models.DateTimeField('anulado', null=True, blank=True)
    visitas = models.PositiveIntegerField('visitas', default=0)
    ultima_visita = models.DateTimeField('última visita', null=True, blank=True)
    creado = models.DateTimeField('creado', auto_now_add=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='+')

    class Meta:
        verbose_name = 'link del cliente'
        verbose_name_plural = 'links del cliente'
        ordering = ['-creado']

    def __str__(self):
        return f'link de {self.proyecto}'

    @property
    def vigente(self):
        return self.anulado is None and (self.vence is None or timezone.now() < self.vence)

    @property
    def vencido(self):
        return self.anulado is None and self.vence is not None and timezone.now() >= self.vence

    def url(self):
        return f'{settings.URL_APP}/c/{self.codigo}/'


# ---------------------------------------------------------------- probador de colores (ficha 14)

class GrupoDeColor(DatoDeTaller):
    """Tableros del proyecto que el cliente puede cambiar juntos ("Frentes", "Cuerpos") y los tableros de la
    biblioteca que se le ofrecen. Va por proyecto: en una versión nueva, los tableros que ya no están se ignoran."""
    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name='grupos_de_color')
    nombre = models.CharField('nombre para el cliente', max_length=60)
    orden = models.PositiveSmallIntegerField('orden', default=0)
    tableros = models.JSONField('tableros del proyecto', default=list)        # nombres, como en el proyecto
    opciones = models.JSONField('opciones', default=list)                     # ids de Material (tableros)
    creado = models.DateTimeField('creado', auto_now_add=True)

    class Meta:
        verbose_name = 'grupo de colores'
        verbose_name_plural = 'grupos de colores'
        ordering = ['orden', 'pk']

    def __str__(self):
        return self.nombre


class Combinacion(DatoDeTaller):
    """Modelos de realidad aumentada de una combinación de colores, generados la primera vez que el cliente los
    pide (proyectos/probador.py). `clave` sale de las elecciones y de la fecha de los materiales usados."""
    class Estado(models.TextChoices):
        EN_COLA = 'en_cola', 'En cola'
        LISTA = 'lista', 'Lista'
        ERROR = 'error', 'Error'

    version = models.ForeignKey(Version, on_delete=models.CASCADE, related_name='combinaciones')
    clave = models.CharField(max_length=20)
    elecciones = models.JSONField(default=dict)          # {id de grupo: id de Material}
    estado = models.CharField(max_length=8, choices=Estado.choices, default=Estado.EN_COLA)
    ar = models.JSONField(default=dict)                   # como cliente['ar']: {mueble o '': ruta del GLB}
    creada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'combinación de colores'
        verbose_name_plural = 'combinaciones de colores'
        constraints = [models.UniqueConstraint(fields=['version', 'clave'], name='una_combinacion_por_clave')]


class EleccionCliente(DatoDeTaller):
    """"Me gusta esta": la combinación que mandó el cliente desde el link. No cambia el proyecto."""
    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name='elecciones')
    version = models.ForeignKey(Version, on_delete=models.SET_NULL, null=True, related_name='+')
    link = models.ForeignKey(LinkCliente, on_delete=models.SET_NULL, null=True, related_name='+')
    nombre = models.CharField('nombre', max_length=80)
    comentario = models.TextField('comentario', max_length=1000, blank=True)
    # foto de los nombres al elegir (grupo, tableros del proyecto, elegido), por si después cambian
    elecciones = models.JSONField(default=list)
    creada = models.DateTimeField('creada', auto_now_add=True)

    class Meta:
        verbose_name = 'elección del cliente'
        verbose_name_plural = 'elecciones del cliente'
        ordering = ['-creada']
