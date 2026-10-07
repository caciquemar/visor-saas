"""Trabajos a realizar en un proyecto (lo que en el visor actual es servidor/api.py con trabajos.db): qué hay que
hacer, en qué piezas y muebles, para quién y para cuándo, con fotos. Pasan por pendiente -> en proceso -> hecho (en el
taller) -> instalado, y de cada paso queda quién y cuándo (en el trabajo, el último; en CambioDeEstado, todos).

Van con el proyecto y no con la versión: las piezas se guardan con el id del conversor, que sigue igual al volver a
convertir."""
from django.conf import settings
from django.db import models
from django.utils import timezone

from proyectos.models import Proyecto
from talleres.archivos import ruta_de_taller
from talleres.separacion import DatoDeTaller


class Trabajo(DatoDeTaller):
    class Estado(models.TextChoices):
        PENDIENTE = 'pendiente', 'Pendiente'
        EN_PROCESO = 'en proceso', 'En proceso'
        HECHO = 'hecho', 'Hecho'
        INSTALADO = 'instalado', 'Instalado'

    # (quién, cuándo) de cada paso, en orden: pendiente 0 pasos cumplidos, en proceso 1, hecho 2, instalado 3
    PASOS = (('iniciado_por', 'iniciado_en'), ('hecho_por', 'hecho_en'), ('instalado_por', 'instalado_en'))

    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name='trabajos')
    texto = models.TextField('qué hay que hacer', max_length=4000)
    estado = models.CharField('estado', max_length=12, choices=Estado.choices, default=Estado.PENDIENTE)
    piezas = models.JSONField('piezas', default=list, blank=True)       # claves del visor (id del conversor o nº)
    muebles = models.JSONField('muebles', default=list, blank=True)     # nombres de mueble
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='+', verbose_name='anotado por')
    asignado = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='+', verbose_name='para quién')
    limite = models.DateField('fecha límite', null=True, blank=True)
    creado = models.DateTimeField('anotado', auto_now_add=True)
    iniciado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='+', verbose_name='empezado por')
    iniciado_en = models.DateTimeField('empezado', null=True, blank=True)
    hecho_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='+', verbose_name='hecho por')
    hecho_en = models.DateTimeField('hecho', null=True, blank=True)
    instalado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name='+', verbose_name='instalado por')
    instalado_en = models.DateTimeField('instalado', null=True, blank=True)

    class Meta:
        verbose_name = 'trabajo'
        verbose_name_plural = 'trabajos'
        ordering = ['-pk']
        indexes = [models.Index(fields=['taller', 'proyecto'])]

    def __str__(self):
        return self.texto[:60]

    def cambiar_estado(self, estado, usuario, ahora):
        """Como en api.py: al avanzar, los pasos salteados se completan con el mismo usuario y hora (y el último
        siempre); al volver atrás se borran los pasos posteriores. Devuelve el estado anterior o None si no cambió."""
        if estado == self.estado:
            return None
        anterior, self.estado = self.estado, estado
        n = self.Estado.values.index(estado)
        for j, (por, en) in enumerate(self.PASOS):
            if j < n:
                if j == n - 1 or getattr(self, en) is None:
                    setattr(self, por, usuario)
                    setattr(self, en, ahora)
            else:
                setattr(self, por, None)
                setattr(self, en, None)
        return anterior

    def pasar_a(self, estado, usuario):
        """Cambia el estado y lo suma al historial (CambioDeEstado). No guarda el trabajo: eso lo hace quien llama.
        Devuelve si cambió."""
        ahora = timezone.now()
        anterior = self.cambiar_estado(estado, usuario, ahora)
        if anterior is None:
            return False
        CambioDeEstado.objects.create(trabajo=self, de=anterior, a=self.estado, usuario=usuario, cuando=ahora)
        return True

    def siguiente(self):
        """El estado que sigue (pendiente -> en proceso -> hecho -> instalado); None si ya está instalado."""
        i = self.Estado.values.index(self.estado)
        return self.Estado.values[i + 1] if i + 1 < len(self.Estado.values) else None

    def vencido(self, hoy=None):
        hoy = hoy or timezone.localdate()
        return self.estado in (self.Estado.PENDIENTE, self.Estado.EN_PROCESO) and bool(self.limite) and self.limite < hoy


class CambioDeEstado(DatoDeTaller):
    """Historial de estados: solo se agregan filas. El trabajo guarda el último quién/cuándo de cada paso; acá queda
    también lo que se deshizo al volver atrás."""
    trabajo = models.ForeignKey(Trabajo, on_delete=models.CASCADE, related_name='cambios')
    de = models.CharField('de', max_length=12, choices=Trabajo.Estado.choices)
    a = models.CharField('a', max_length=12, choices=Trabajo.Estado.choices)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='+', verbose_name='quién')
    cuando = models.DateTimeField('cuándo')

    class Meta:
        verbose_name = 'cambio de estado'
        verbose_name_plural = 'cambios de estado'
        ordering = ['cuando', 'pk']


class Foto(DatoDeTaller):
    trabajo = models.ForeignKey(Trabajo, on_delete=models.CASCADE, related_name='fotos')
    archivo = models.ImageField('archivo', upload_to=ruta_de_taller, max_length=300)
    tamano = models.PositiveIntegerField('tamaño', default=0)
    subida_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='+', verbose_name='subida por')
    creada = models.DateTimeField('subida', auto_now_add=True)

    class Meta:
        verbose_name = 'foto'
        verbose_name_plural = 'fotos'
        ordering = ['pk']
