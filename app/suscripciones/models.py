"""Planes, cotización, suscripción de cada taller y pagos (ficha 08). El taller paga por período (mensual, semestral
o anual) con un link de pago; no hay cobro automático. Qué estado tiene cada taller lo decide `estados.py`."""
import secrets
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models

from talleres.separacion import DatoDeTaller


class Plan(models.Model):
    """Un plan del servicio. Precio, límites y funciones se cambian en la administración (no es dato de un taller)."""
    clave = models.SlugField('clave', max_length=20, unique=True)
    nombre = models.CharField('nombre', max_length=40)
    precio_usd = models.DecimalField('precio por mes (USD)', max_digits=8, decimal_places=2)
    max_proyectos = models.PositiveIntegerField('proyectos activos', null=True, blank=True,
                                                help_text='Sin nada: sin límite. Los archivados no cuentan.')
    max_usuarios = models.PositiveIntegerField('usuarios', null=True, blank=True,
                                               help_text='Sin nada: sin límite. Cuentan todos los miembros activos '
                                                         '(también los que entran con PIN) y las invitaciones sin usar.')
    funciones = models.JSONField('funciones', default=list, blank=True)
    orden = models.PositiveSmallIntegerField('orden', default=0, help_text='De menor a mayor: el más completo, último.')
    a_la_venta = models.BooleanField('a la venta', default=True, help_text='Si no, no aparece para elegir.')

    class Meta:
        verbose_name = 'plan'
        verbose_name_plural = 'planes'
        ordering = ['orden', 'pk']

    def __str__(self):
        return self.nombre

    def clean(self):
        from talleres.limites import FUNCIONES
        desconocidas = set(self.funciones or []) - set(FUNCIONES)
        if desconocidas:
            raise ValidationError({'funciones': f'No existen: {", ".join(sorted(desconocidas))}'})


class Cotizacion(models.Model):
    """Pesos por dólar de un día: la lee la tarea diaria del BCRA (dólar minorista, promedio vendedor) o la carga
    Martín a mano. Vale la última."""
    class Fuente(models.TextChoices):
        BCRA = 'bcra', 'BCRA'
        MANUAL = 'manual', 'A mano'

    fecha = models.DateField('fecha')
    ars_por_usd = models.DecimalField('pesos por dólar', max_digits=10, decimal_places=2)
    fuente = models.CharField('fuente', max_length=10, choices=Fuente.choices, default=Fuente.MANUAL)
    creada = models.DateTimeField('cargada', auto_now_add=True)

    class Meta:
        verbose_name = 'cotización'
        verbose_name_plural = 'cotizaciones'
        ordering = ['-fecha', '-creada']

    def __str__(self):
        return f'{self.fecha:%d/%m/%Y}: $ {self.ars_por_usd}'


class Suscripcion(DatoDeTaller):
    """Una por taller (se crea sola con el taller, en prueba). Las fechas son días completos: el taller tiene
    servicio hasta el final de `pagado_hasta`."""
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name='+', verbose_name='plan')
    plan_proximo = models.ForeignKey(Plan, on_delete=models.PROTECT, null=True, blank=True, related_name='+',
                                     verbose_name='plan desde el próximo período',
                                     help_text='Bajar de plan vale cuando termina lo ya pagado.')
    cambio_de_plan = models.DateField('cambia de plan el', null=True, blank=True)
    prueba_hasta = models.DateField('prueba hasta')
    pagado_hasta = models.DateField('pagado hasta', null=True, blank=True)
    sin_cobro_hasta = models.DateField('sin cobro hasta', null=True, blank=True,
                                       help_text='Pilotos y talleres propios: funciona como pagado hasta esa fecha.')
    estado = models.CharField('estado', max_length=20, default='prueba', editable=False)
    estado_desde = models.DateField('estado desde', null=True, blank=True, editable=False)
    avisos = models.JSONField('avisos mandados', default=list, blank=True, editable=False)
    creada = models.DateTimeField('creada', auto_now_add=True)

    class Meta:
        verbose_name = 'suscripción'
        verbose_name_plural = 'suscripciones'
        constraints = [models.UniqueConstraint(fields=['taller'], name='una_suscripcion_por_taller')]

    def __str__(self):
        return f'{self.taller}: {self.plan} ({self.estado})'


def codigo_de_pago():
    return secrets.token_urlsafe(16)


class Pago(DatoDeTaller):
    """Un intento de pago: se crea al generar el link y queda aprobado solo después de consultarlo en la pasarela
    (nunca por lo que diga el aviso). Es lo que después se factura (ficha 09)."""
    class Periodo(models.TextChoices):
        MENSUAL = 'mensual', 'Mensual'
        SEMESTRAL = 'semestral', 'Semestral'
        ANUAL = 'anual', 'Anual'
        DIFERENCIA = 'diferencia', 'Cambio de plan'

    class Estado(models.TextChoices):
        PENDIENTE = 'pendiente', 'Pendiente'
        APROBADO = 'aprobado', 'Aprobado'
        RECHAZADO = 'rechazado', 'Rechazado'
        VENCIDO = 'vencido', 'Vencido'

    suscripcion = models.ForeignKey(Suscripcion, on_delete=models.PROTECT, related_name='pagos')
    codigo = models.CharField('código', max_length=32, unique=True, default=codigo_de_pago, editable=False)
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name='+', verbose_name='plan')
    periodo = models.CharField('período', max_length=12, choices=Periodo.choices)
    meses = models.PositiveSmallIntegerField('meses de servicio', default=0)
    monto_usd = models.DecimalField('monto (USD)', max_digits=10, decimal_places=2)
    cotizacion = models.DecimalField('pesos por dólar', max_digits=10, decimal_places=2)
    monto_ars = models.DecimalField('monto (ARS)', max_digits=12, decimal_places=2)
    estado = models.CharField('estado', max_length=12, choices=Estado.choices, default=Estado.PENDIENTE)
    pasarela = models.CharField('pasarela', max_length=20)
    link = models.URLField('link de pago', max_length=500, blank=True)
    id_externo = models.CharField('id en la pasarela', max_length=64, blank=True)
    datos = models.JSONField('lo último que dijo la pasarela', default=dict, blank=True)
    desde = models.DateField('servicio desde', null=True, blank=True)
    hasta = models.DateField('servicio hasta', null=True, blank=True)
    creado = models.DateTimeField('creado', auto_now_add=True)
    creado_por = models.ForeignKey('usuarios.Usuario', on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='+')
    resuelto = models.DateTimeField('aprobado o rechazado', null=True, blank=True)
    nota = models.CharField('nota', max_length=200, blank=True)

    class Meta:
        verbose_name = 'pago'
        verbose_name_plural = 'pagos'
        ordering = ['-creado']
        # Un pago de la pasarela aprueba uno solo de los nuestros (en todo el servicio, no por taller).
        constraints = [models.UniqueConstraint(fields=['pasarela', 'id_externo'], condition=~models.Q(id_externo=''),
                                               name='un_pago_externo_por_pago')]

    def __str__(self):
        return f'{self.get_periodo_display()} {self.plan}: $ {self.monto_ars} ({self.get_estado_display().lower()})'

    @property
    def monto_ars_entero(self):
        return int(self.monto_ars.quantize(Decimal('1')))


class Cobro(models.Model):
    """Configuración del cobro, una sola fila (la cambia Martín en la administración). La clave privada de Payway
    NO está acá: queda en el .env (PAYWAY_CLAVE_PRIVADA), porque con ella se consultan y anulan pagos. Los valores
    iniciales salen del .env (SUSCRIPCIONES_ACTIVAS, PASARELA, PAYWAY_*); después mandan los de acá."""
    class Pasarela(models.TextChoices):
        PAYWAY = 'payway', 'Payway'
        SIMULADA = 'simulada', 'Simulada (solo en la PC)'

    class Ambiente(models.TextChoices):
        SANDBOX = 'sandbox', 'Prueba (Sandbox): no cobra de verdad'
        PRODUCCION = 'produccion', 'Producción: cobra de verdad'

    activo = models.BooleanField('cobro activo', default=False,
                                 help_text='Apagado: todo taller tiene todo, sin topes ni bloqueos, y no se muestra '
                                           'Mi suscripción. Prendido: se aplican los planes y los estados.')
    pasarela = models.CharField('pasarela', max_length=12, choices=Pasarela.choices, default=Pasarela.PAYWAY)
    ambiente = models.CharField('ambiente de Payway', max_length=12, choices=Ambiente.choices,
                                default=Ambiente.SANDBOX,
                                help_text='Tiene que coincidir con la clave privada del .env del servidor.')
    sitio = models.CharField('número de sitio', max_length=20, blank=True)
    establecimiento = models.CharField('número de establecimiento', max_length=20, blank=True)
    cuit = models.CharField('CUIT del comercio', max_length=11, blank=True, help_text='Sin guiones.')
    clave_publica = models.CharField('clave pública de Payway', max_length=100, blank=True)
    modificado = models.DateTimeField('modificado', auto_now=True)

    class Meta:
        verbose_name = 'configuración del cobro'
        verbose_name_plural = 'configuración del cobro'

    def __str__(self):
        return 'Configuración del cobro'

    def clean(self):
        from django.conf import settings
        if self.pasarela == self.Pasarela.SIMULADA and not settings.PASARELA_SIMULADA_PERMITIDA:
            raise ValidationError({'pasarela': 'La simulada solo existe en la PC (DEBUG=1): en el servidor '
                                               'cualquiera podría aprobar un pago.'})
        if self.cuit and not (self.cuit.isdigit() and len(self.cuit) == 11):
            raise ValidationError({'cuit': 'Tienen que ser 11 números, sin guiones.'})
        if self.establecimiento and not self.establecimiento.isdigit():
            raise ValidationError({'establecimiento': 'Solo números.'})

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
        from .config import olvidar
        olvidar()
