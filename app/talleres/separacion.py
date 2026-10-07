"""Separación entre talleres: la regla 1 de CLAUDE.md vive entera en este archivo.

- `taller_actual` guarda el taller del pedido (lo pone talleres.middleware.TallerMiddleware) o de la tarea
  (`con_taller` / `tarea_de_taller`).
- Todo modelo con datos de un taller hereda de `DatoDeTaller`. Su manager `objects` filtra solo por
  `taller_actual` y, si al ejecutar la consulta no hay taller, lanza `SinTaller`: si alguien se olvida de
  algo, falla a la vista en vez de devolver datos de todos los talleres.
- `sin_filtro` es la única salida sin filtro. Solo se usa en los archivos de `ARCHIVOS_CON_SIN_FILTRO`
  (lo controla tests/app/test_guardianes.py).
- Al guardar se revisa que el dato y todo lo que apunta (ForeignKey a otro DatoDeTaller) sean del taller actual.
"""
import contextvars
from contextlib import contextmanager
from functools import wraps

from django.db import models

taller_actual = contextvars.ContextVar('taller_actual', default=None)

# Únicos archivos (relativos a app/) que pueden usar `sin_filtro` o `_base_manager`.
ARCHIVOS_CON_SIN_FILTRO = {
    'talleres/separacion.py',      # validaciones de este archivo
    'talleres/middleware.py',      # buscar la membresía antes de saber si el usuario es del taller
    'talleres/cuentas.py',         # elegir taller después de entrar y aceptar invitaciones
    'talleres/admin.py',           # administración del servicio (Martín), ve todos los talleres
    'talleres/rls.py',             # segunda barrera en PostgreSQL: políticas y variable del taller (no lee datos)
}


class SinTaller(RuntimeError):
    """Se pidió un dato de taller sin taller en el contexto."""

    def __init__(self, mensaje='No hay taller en el contexto: usá el middleware, con_taller() o tarea_de_taller'):
        super().__init__(mensaje)


class OtroTaller(PermissionError):
    """Se intentó guardar, mover o enlazar un dato de un taller desde otro."""


def taller_o_error():
    taller = taller_actual.get()
    if taller is None:
        raise SinTaller()
    return taller


@contextmanager
def con_taller(taller):
    """Para tareas y comandos: dentro del bloque, todo se filtra por `taller`."""
    if taller is None or taller.pk is None:
        raise SinTaller('con_taller() necesita un taller guardado')
    marca = taller_actual.set(taller)
    try:
        yield taller
    finally:
        taller_actual.reset(marca)


def tarea_de_taller(funcion):
    """Decorador para tareas de la cola: el primer argumento es el id del taller.

        @task()
        @tarea_de_taller
        def convertir_version(version_id): ...

        convertir_version(taller.id, version.id)
    """
    @wraps(funcion)
    def envuelta(taller_id, *args, **kwargs):
        from .models import Taller
        with con_taller(Taller.objects.get(pk=taller_id)):
            return funcion(*args, **kwargs)
    return envuelta


class QuerySetDeTaller(models.QuerySet):
    def update(self, **campos):
        if 'taller' in campos or 'taller_id' in campos:
            raise OtroTaller('No se puede cambiar el taller de un dato')
        return super().update(**campos)

    def bulk_update(self, objs, fields, *args, **kwargs):
        if 'taller' in fields or 'taller_id' in fields:
            raise OtroTaller('No se puede cambiar el taller de un dato')
        return super().bulk_update(objs, fields, *args, **kwargs)

    def bulk_create(self, objs, *args, **kwargs):
        objs = list(objs)
        for obj in objs:
            obj.validar_taller()
        return super().bulk_create(objs, *args, **kwargs)

    def raw(self, *args, **kwargs):
        raise OtroTaller('raw() no filtra por taller: no se usa con datos de taller')


class TallerDelContexto(models.Expression):
    """El id del taller actual, leído recién al armar el SQL. Así el filtro está en toda consulta (también en
    update, delete y subconsultas), y un queryset armado antes del pedido (por ejemplo el de un ModelForm al
    importar el módulo) usa el taller del pedido en que se ejecuta, no el de cuando se armó."""
    output_field = models.BigIntegerField()

    def as_sql(self, compiler, connection):
        return '%s', [taller_o_error().pk]


class PorTaller(models.Manager.from_queryset(QuerySetDeTaller)):
    """Manager por defecto de los datos de taller: solo ve el taller actual; sin taller, la consulta falla."""

    def get_queryset(self):
        return super().get_queryset().filter(taller_id=TallerDelContexto())


class DatoDeTaller(models.Model):
    taller = models.ForeignKey('talleres.Taller', on_delete=models.PROTECT, editable=False, related_name='+')

    objects = PorTaller()           # el primero declarado es el manager por defecto
    sin_filtro = models.Manager()

    class Meta:
        abstract = True

    def validar_taller(self):
        actual = taller_o_error()
        if self.taller_id is None:
            self.taller = actual
        elif self.taller_id != actual.pk:
            raise OtroTaller(f'{self._meta.verbose_name} es de otro taller')
        if self.pk is not None:
            # Si ya existe una fila con este id, tiene que ser de este taller (si no, el UPDATE la pisaría).
            guardado = type(self)._base_manager.filter(pk=self.pk).values_list('taller_id', flat=True).first()
            if guardado is not None and guardado != self.taller_id:
                raise OtroTaller(f'{self._meta.verbose_name} es de otro taller')
        for campo in self._meta.concrete_fields:
            if not isinstance(campo, models.ForeignKey) or campo.name == 'taller':
                continue
            if not issubclass(campo.related_model, DatoDeTaller):
                continue
            otro_id = getattr(self, campo.attname)
            if otro_id is None:
                continue
            otro = campo.get_cached_value(self, None) if campo.is_cached(self) else None
            if otro is not None and otro.pk == otro_id:
                taller_del_otro = otro.taller_id
            else:
                taller_del_otro = (campo.related_model._base_manager.filter(pk=otro_id)
                                   .values_list('taller_id', flat=True).first())
            if taller_del_otro != self.taller_id:
                raise OtroTaller(f'{campo.verbose_name} apunta a un dato de otro taller')

    def save(self, *args, **kwargs):
        self.validar_taller()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.taller_id != taller_o_error().pk:
            raise OtroTaller(f'{self._meta.verbose_name} es de otro taller')
        return super().delete(*args, **kwargs)
