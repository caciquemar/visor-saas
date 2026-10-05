"""Vistas como las que va a tener la app, escritas igual: sin filtrar a mano por taller."""
from django import forms
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from talleres.archivos import abrir_de_taller
from talleres.roles import miembro

from .models import Nota


class FormNota(forms.ModelForm):
    class Meta:
        model = Nota
        fields = ('texto', 'padre', 'archivo')


@miembro
def lista(request, taller):
    return HttpResponse('\n'.join(n.texto for n in Nota.objects.order_by('pk')))


@miembro
def ver(request, taller, id):
    return HttpResponse(get_object_or_404(Nota, pk=id).texto)


@miembro
def nueva(request, taller):
    form = FormNota(request.POST, request.FILES)
    if not form.is_valid():
        return HttpResponse(form.errors.as_json(), status=400)
    return HttpResponse(str(form.save().pk))


@require_POST
@miembro
def editar(request, taller, id):
    nota = get_object_or_404(Nota, pk=id)
    form = FormNota(request.POST, request.FILES, instance=nota)
    if not form.is_valid():
        return HttpResponse(form.errors.as_json(), status=400)
    form.save()
    return redirect('notas:ver', taller=taller, id=id)


@require_POST
@miembro
def borrar(request, taller, id):
    get_object_or_404(Nota, pk=id).delete()
    return HttpResponse('borrada')


@miembro
def archivo_de_nota(request, taller, id):
    return abrir_de_taller(request, get_object_or_404(Nota, pk=id).archivo.name)


@miembro
def archivo_por_ruta(request, taller, ruta):
    return abrir_de_taller(request, ruta)
