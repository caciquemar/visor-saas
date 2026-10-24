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

ETAPAS_POR_DEFECTO = ['Cortada', 'Canteada', 'Mecanizada']
# los procesos fijos (ficha 19): se renombran, se apagan y se ordenan como los demás; no se borran. Un taller nuevo
# los tiene en este orden, después de los suyos
FIJOS = [('armado', 'Armado'), ('control', 'Control de calidad'), ('embalaje', 'Embalaje'), ('carga', 'Carga'),
         ('instalacion', 'Instalar en obra')]


def quien(related_name='+', nombre='quién'):
    return models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name=related_name, verbose_name=nombre)


class Etapa(DatoDeTaller):
    """Los procesos del taller (Procesos, en Producción), en el orden que elige el taller (todos se arrastran). Los del
    taller (`tipo='pieza'`) se renombran, apagan y borran si nunca se usaron, y se marcan por pieza o por mueble
    (`por_mueble`: cualquier etiqueta del mueble marca todas sus piezas). Los fijos (FIJOS: armado, control, embalaje,
    carga, instalación) se renombran y se apagan, no se borran. Las marcas por pieza (`Marca`) son de los del taller y
    de Armado: con ellas sale el %."""
    class Tipo(models.TextChoices):
        PIEZA = 'pieza', 'Del taller'
        ARMADO = 'armado', 'Armado'
        CONTROL = 'control', 'Control de calidad'
        EMBALAJE = 'embalaje', 'Embalaje'
        CARGA = 'carga', 'Carga'
        INSTALACION = 'instalacion', 'Instalar en obra'

    nombre = models.CharField('nombre', max_length=40)
    orden = models.PositiveSmallIntegerField('orden', default=0)
    activa = models.BooleanField('activa', default=True)
    tipo = models.CharField('tipo', max_length=12, choices=Tipo.choices, default=Tipo.PIEZA)
    por_mueble = models.BooleanField('se marca por mueble', default=False)

    class Meta:
        verbose_name = 'proceso'
        verbose_name_plural = 'procesos'
        ordering = ['orden', 'pk']
        constraints = [models.UniqueConstraint(fields=['taller', 'tipo'], condition=~models.Q(tipo='pieza'),
                                               name='un_proceso_fijo_de_cada_tipo')]

    @property
    def fijo(self):
        return self.tipo != self.Tipo.PIEZA

    @property
    def marca_piezas(self):
        """Los que dejan marcas por pieza (cuentan para el %): los del taller y Armado."""
        return self.tipo in (self.Tipo.PIEZA, self.Tipo.ARMADO)

    def __str__(self):
        return self.nombre


def procesos():
    """Todos los procesos del taller, en el orden que eligió (Procesos). La primera vez crea los de por defecto; a un
    taller que no tiene algún fijo se lo agrega (prendido, al final)."""
    todos = list(Etapa.objects.all())
    if not todos:
        todos = [Etapa.objects.create(nombre=n, orden=i) for i, n in enumerate(ETAPAS_POR_DEFECTO, 1)]
    tiene = {e.tipo for e in todos}
    for i, (tipo, nombre) in enumerate(FIJOS, 1):
        if tipo not in tiene:
            todos.append(Etapa.objects.create(nombre=nombre, orden=100 + i, tipo=tipo, por_mueble=True))
    return sorted(todos, key=lambda e: (e.orden, e.pk))


def etapas_del_taller():
    """Los procesos que dejan marcas por pieza (los del taller y Armado), en orden, prendidos o no."""
    return [e for e in procesos() if e.marca_piezas]


def etapas_activas():
    """Las que cuentan para el %: los del taller y Armado, prendidos."""
    return [e for e in etapas_del_taller() if e.activa]


def etapa_de_armado():
    """La que mira el embalaje y la que pinta las piezas armadas: Armado si está prendido; si no, la última de las
    del taller que marcan piezas."""
    activas = etapas_activas()
    return next((e for e in activas if e.tipo == Etapa.Tipo.ARMADO), None) or (activas[-1] if activas else None)


def fijo(tipo):
    """El proceso fijo de ese tipo si está prendido; si no, None."""
    return next((e for e in procesos() if e.tipo == tipo and e.activa), None)


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
    """Lo que sube al camión: el proyecto completo (`muebles` vacío) o algunos muebles. `libre` (ficha 21): la que se
    crea en Mi puesto escaneando el primer bulto; lleva solo lo que se carga (sus muebles se van sumando). Anularla
    (sin haber salido) devuelve los bultos a embalados."""
    class Estado(models.TextChoices):
        ARMANDO = 'armando', 'Cargando'
        SALIO = 'salio', 'Salió a obra'
        ENTREGADA = 'entregada', 'Entregada'
        ANULADA = 'anulada', 'Anulada'

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
    libre = models.BooleanField('solo lo que se escanee', default=False)
    anulada_por = quien(nombre='anulada por')
    anulada_en = models.DateTimeField('anulada', null=True, blank=True)

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


# ---------------------------------------------------------------- ficha 19: anotaciones de lo escaneado

class Anotacion(DatoDeTaller):
    """Una nota (con fotos) pegada a lo que se escaneó en Mi puesto: el mueble, y la pieza si fue una pieza, en un
    proceso. Con "Hay que arreglarlo", además crea una tarea del mueble o de la pieza (`tarea`)."""
    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name='anotaciones')
    mueble = models.CharField('mueble', max_length=200)
    panel = models.CharField('pieza (id del panel)', max_length=300, blank=True)
    pieza = models.CharField('pieza', max_length=200, blank=True)                 # "0048 Suelo", para mostrar
    proceso = models.ForeignKey(Etapa, on_delete=models.SET_NULL, null=True, blank=True, related_name='anotaciones')
    texto = models.TextField('texto', max_length=2000, blank=True)
    tarea = models.ForeignKey('trabajos.Trabajo', on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='anotaciones')
    por = quien()
    cuando = models.DateTimeField('cuándo')

    class Meta:
        verbose_name = 'anotación'
        verbose_name_plural = 'anotaciones'
        ordering = ['cuando', 'pk']
        indexes = [models.Index(fields=['taller', 'proyecto'])]

    def __str__(self):
        return f'{self.mueble}: {self.texto[:40]}'


class FotoDeAnotacion(DatoDeTaller):
    anotacion = models.ForeignKey(Anotacion, on_delete=models.CASCADE, related_name='fotos')
    archivo = models.ImageField('archivo', upload_to=ruta_de_taller, max_length=300)
    tamano = models.PositiveIntegerField('tamaño', default=0)
    subida_por = quien(nombre='subida por')
    creada = models.DateTimeField('subida', auto_now_add=True)

    class Meta:
        verbose_name = 'foto de anotación'
        verbose_name_plural = 'fotos de anotaciones'
        ordering = ['pk']
