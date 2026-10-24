"""Avance de las piezas por etapas, fin de fabricación de cada mueble, bultos y cargas (ficha 13).

Las marcas van por la clave de la pieza (etiquetas/claves.py), no por la versión: al subir una versión nueva, el
avance sigue en las piezas que siguen iguales. Nada se borra: deshacer una marca, reabrir un mueble o volver atrás un
bulto deja quién y cuándo.

Ubicaciones (ficha 17): dónde queda cada pieza o bulto en el taller (estante, depósito…). `Ubicado` es el historial;
dónde está algo es su último `Ubicado` vigente."""
from django.conf import settings
from django.db import models

from proyectos.models import Proyecto
from talleres.archivos import ruta_de_taller
from talleres.separacion import DatoDeTaller

ETAPAS_POR_DEFECTO = ['Cortada', 'Canteada', 'Mecanizada', 'Armada']


def quien(related_name='+', nombre='quién'):
    return models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name=related_name, verbose_name=nombre)


class Etapa(DatoDeTaller):
    """Etapas de las piezas del taller, en orden. La última activa es la de armado: la que mira "Fabricación
    terminada"."""
    nombre = models.CharField('nombre', max_length=40)
    orden = models.PositiveSmallIntegerField('orden', default=0)
    activa = models.BooleanField('activa', default=True)

    class Meta:
        verbose_name = 'etapa'
        verbose_name_plural = 'etapas'
        ordering = ['orden', 'pk']

    def __str__(self):
        return self.nombre


def etapas_del_taller():
    """Las etapas del taller (todas, en orden). La primera vez crea las de por defecto."""
    etapas = list(Etapa.objects.all())
    if not etapas:
        etapas = [Etapa.objects.create(nombre=n, orden=i) for i, n in enumerate(ETAPAS_POR_DEFECTO, 1)]
    return etapas


def etapas_activas():
    return [e for e in etapas_del_taller() if e.activa]


class Marca(DatoDeTaller):
    """Una pieza pasó por una etapa. Una sola vigente por pieza y etapa; deshacer la deja con `deshecha_en`."""
    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name='marcas')
    etapa = models.ForeignKey(Etapa, on_delete=models.PROTECT, related_name='marcas')
    clave = models.JSONField('pieza')
    huella = models.CharField(max_length=64)
    mueble = models.CharField('mueble', max_length=200, blank=True)       # el de la clave, para buscar por mueble
    por = quien()
    cuando = models.DateTimeField('cuándo')
    deshecha_por = quien(nombre='deshecha por')
    deshecha_en = models.DateTimeField('deshecha', null=True, blank=True)

    class Meta:
        verbose_name = 'marca de avance'
        verbose_name_plural = 'marcas de avance'
        ordering = ['cuando', 'pk']
        constraints = [models.UniqueConstraint(fields=['proyecto', 'etapa', 'huella'],
                                               condition=models.Q(deshecha_en__isnull=True),
                                               name='una_marca_vigente_por_pieza_y_etapa')]
        indexes = [models.Index(fields=['taller', 'proyecto'])]

    def __str__(self):
        return f'{self.clave.get("nombre")} {self.etapa}'


class FinDeMueble(DatoDeTaller):
    """"Fabricación terminada" de un mueble, con sus bultos. Si faltaban piezas en la etapa de armado, queda el
    motivo y cuáles faltaban. Reabrir lo deja con `anulado_en` (solo si ningún bulto se cargó)."""
    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name='fines')
    mueble = models.CharField('mueble', max_length=200)
    bultos = models.PositiveSmallIntegerField('bultos', default=1)
    motivo = models.TextField('motivo', max_length=1000, blank=True)
    faltantes = models.JSONField('piezas que faltaban', default=list, blank=True)
    por = quien()
    cuando = models.DateTimeField('cuándo')
    anulado_por = quien(nombre='reabierto por')
    anulado_en = models.DateTimeField('reabierto', null=True, blank=True)

    class Meta:
        verbose_name = 'fin de fabricación'
        verbose_name_plural = 'fines de fabricación'
        ordering = ['cuando', 'pk']
        constraints = [models.UniqueConstraint(fields=['proyecto', 'mueble'],
                                               condition=models.Q(anulado_en__isnull=True),
                                               name='un_fin_vigente_por_mueble')]

    def __str__(self):
        return f'{self.mueble} terminado'


class Carga(DatoDeTaller):
    """Lo que sube al camión: el proyecto completo (`muebles` vacío) o algunos muebles."""
    class Estado(models.TextChoices):
        ARMANDO = 'armando', 'Cargando'
        SALIO = 'salio', 'Salió a obra'
        ENTREGADA = 'entregada', 'Entregada'

    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name='cargas')
    muebles = models.JSONField('muebles', default=list, blank=True)
    estado = models.CharField('estado', max_length=10, choices=Estado.choices, default=Estado.ARMANDO)
    creada_por = quien(nombre='armada por')
    creada_en = models.DateTimeField('armada')
    salio_por = quien(nombre='salió por')
    salio_en = models.DateTimeField('salió', null=True, blank=True)
    motivo = models.TextField('motivo de los faltantes', max_length=1000, blank=True)
    faltantes = models.JSONField('faltantes al salir', default=list, blank=True)
    entregada_por = quien(nombre='entregada por')
    entregada_en = models.DateTimeField('entregada', null=True, blank=True)

    class Meta:
        verbose_name = 'carga'
        verbose_name_plural = 'cargas'
        ordering = ['-creada_en', '-pk']

    def __str__(self):
        return f'carga {self.pk} de {self.proyecto}'


class Bulto(DatoDeTaller):
    class Estado(models.TextChoices):
        EMBALADO = 'embalado', 'Embalado'
        CARGADO = 'cargado', 'Cargado'
        ENTREGADO = 'entregado', 'Entregado'

    fin = models.ForeignKey(FinDeMueble, on_delete=models.CASCADE, related_name='lista_de_bultos')
    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name='bultos')
    mueble = models.CharField('mueble', max_length=200)
    numero = models.PositiveSmallIntegerField('número')
    estado = models.CharField('estado', max_length=10, choices=Estado.choices, default=Estado.EMBALADO)
    carga = models.ForeignKey(Carga, on_delete=models.SET_NULL, null=True, blank=True, related_name='bultos')
    embalado_por = quien(nombre='embalado por')
    embalado_en = models.DateTimeField('embalado')
    cargado_por = quien(nombre='cargado por')
    cargado_en = models.DateTimeField('cargado', null=True, blank=True)
    entregado_por = quien(nombre='entregado por')
    entregado_en = models.DateTimeField('entregado', null=True, blank=True)

    class Meta:
        verbose_name = 'bulto'
        verbose_name_plural = 'bultos'
        ordering = ['mueble', 'numero']
        constraints = [models.UniqueConstraint(fields=['fin', 'numero'], name='un_numero_por_bulto')]

    def __str__(self):
        return f'{self.mueble} · bulto {self.numero} de {self.fin.bultos}'


class Movimiento(DatoDeTaller):
    """Historial de los bultos: solo se agregan filas. Base del estado del pedido para el cliente (más adelante)."""
    bulto = models.ForeignKey(Bulto, on_delete=models.CASCADE, related_name='movimientos')
    carga = models.ForeignKey(Carga, on_delete=models.SET_NULL, null=True, blank=True, related_name='movimientos')
    de = models.CharField('de', max_length=10, choices=Bulto.Estado.choices, blank=True)
    a = models.CharField('a', max_length=10, choices=Bulto.Estado.choices)
    usuario = quien()
    cuando = models.DateTimeField('cuándo')

    class Meta:
        verbose_name = 'movimiento de bulto'
        verbose_name_plural = 'movimientos de bultos'
        ordering = ['cuando', 'pk']


class Ubicacion(DatoDeTaller):
    """Lugares del taller donde quedan las piezas y los bultos (ficha 17). Se eligen en Mi puesto."""
    nombre = models.CharField('nombre', max_length=40)
    orden = models.PositiveSmallIntegerField('orden', default=0)
    activa = models.BooleanField('activa', default=True)

    class Meta:
        verbose_name = 'ubicación'
        verbose_name_plural = 'ubicaciones'
        ordering = ['orden', 'pk']

    def __str__(self):
        return self.nombre


class Ubicado(DatoDeTaller):
    """Una pieza (por su huella) o un bulto quedó en una ubicación; sin ubicación = salió del taller (cargado).
    Solo se agregan filas; deshacer la lectura del puesto la deja con `deshecho_en`."""
    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name='ubicados')
    huella = models.CharField(max_length=64, blank=True)
    clave = models.JSONField('pieza', null=True, blank=True)
    bulto = models.ForeignKey(Bulto, on_delete=models.CASCADE, null=True, blank=True, related_name='ubicados')
    ubicacion = models.ForeignKey(Ubicacion, on_delete=models.PROTECT, null=True, blank=True,
                                  related_name='ubicados', verbose_name='ubicación')
    marca = models.ForeignKey(Marca, on_delete=models.SET_NULL, null=True, blank=True, related_name='ubicados')
    por = quien()
    cuando = models.DateTimeField('cuándo')
    deshecho_en = models.DateTimeField('deshecho', null=True, blank=True)

    class Meta:
        verbose_name = 'lugar de una pieza o bulto'
        verbose_name_plural = 'lugares de piezas y bultos'
        ordering = ['cuando', 'pk']
        indexes = [models.Index(fields=['taller', 'proyecto', 'huella'])]

    def __str__(self):
        return f'{self.bulto or (self.clave or {}).get("nombre")} en {self.ubicacion or "camión"}'


# ---------------------------------------------------------------- ficha 18: del armado a la instalación

PUNTOS_POR_DEFECTO = ['Cantos', 'Todas las piezas', 'Frentes', 'Herrajes']


class PuntoDeControl(DatoDeTaller):
    """Un punto de la lista del control de calidad de cada mueble (Procesos, solo el dueño)."""
    nombre = models.CharField('nombre', max_length=40)
    orden = models.PositiveSmallIntegerField('orden', default=0)
    activa = models.BooleanField('activo', default=True)

    class Meta:
        verbose_name = 'punto de control'
        verbose_name_plural = 'puntos de control'
        ordering = ['orden', 'pk']

    def __str__(self):
        return self.nombre


def puntos_de_control():
    """Los puntos del taller (todos, en orden). La primera vez crea los de por defecto."""
    puntos = list(PuntoDeControl.objects.all())
    if not puntos:
        puntos = [PuntoDeControl.objects.create(nombre=n, orden=i) for i, n in enumerate(PUNTOS_POR_DEFECTO, 1)]
    return puntos


class Control(DatoDeTaller):
    """Control de calidad de un mueble armado. Vale el último. `resultados`: [{punto, nombre, ok, nota, tarea}];
    cada punto mal crea una tarea del mueble (y se puede seguir: decisión de Martín, 2026-10-24)."""
    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name='controles')
    mueble = models.CharField('mueble', max_length=200)
    resultados = models.JSONField('resultados', default=list)
    ok = models.BooleanField('todo ok', default=True)
    por = quien()
    cuando = models.DateTimeField('cuándo')

    class Meta:
        verbose_name = 'control de calidad'
        verbose_name_plural = 'controles de calidad'
        ordering = ['cuando', 'pk']
        indexes = [models.Index(fields=['taller', 'proyecto'])]

    def __str__(self):
        return f'control de {self.mueble}'


class Instalacion(DatoDeTaller):
    """Un mueble quedó instalado en la obra. Con bultos sin entregar o tareas abiertas, queda el motivo. Deshacer (dueño
    u oficina) lo deja con `anulado_en`."""
    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name='instalaciones')
    mueble = models.CharField('mueble', max_length=200)
    nota = models.TextField('nota', max_length=1000, blank=True)
    motivo = models.TextField('motivo', max_length=1000, blank=True)
    faltantes = models.JSONField('lo que faltaba', default=list, blank=True)
    por = quien()
    cuando = models.DateTimeField('cuándo')
    anulado_por = quien(nombre='deshecho por')
    anulado_en = models.DateTimeField('deshecho', null=True, blank=True)

    class Meta:
        verbose_name = 'instalación'
        verbose_name_plural = 'instalaciones'
        ordering = ['cuando', 'pk']
        constraints = [models.UniqueConstraint(fields=['proyecto', 'mueble'],
                                               condition=models.Q(anulado_en__isnull=True),
                                               name='una_instalacion_vigente_por_mueble')]

    def __str__(self):
        return f'{self.mueble} instalado'


class FotoDeInstalacion(DatoDeTaller):
    instalacion = models.ForeignKey(Instalacion, on_delete=models.CASCADE, related_name='fotos')
    archivo = models.ImageField('archivo', upload_to=ruta_de_taller, max_length=300)
    tamano = models.PositiveIntegerField('tamaño', default=0)
    subida_por = quien(nombre='subida por')
    creada = models.DateTimeField('subida', auto_now_add=True)

    class Meta:
        verbose_name = 'foto de instalación'
        verbose_name_plural = 'fotos de instalación'
        ordering = ['pk']
