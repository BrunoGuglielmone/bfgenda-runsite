from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_POST, require_http_methods

from agenda.forms import CategoriaForm
from agenda.models import Categoria

from .common import (
    ConfirmationViewConfig,
    FormViewConfig,
    confirmation_response,
    form_response,
    get_return_url,
    saved_response,
)


def _category_form_config(*, editing: bool, cancel_url: str, hidden_fields=()):
    return FormViewConfig(
        eyebrow="Categoría",
        title="Editar categoría" if editing else "Nueva categoría",
        description=(
            "Modifica el nombre o el color de la categoría."
            if editing
            else "Crea una categoría para organizar tus tareas y eventos."
        ),
        icon="●",
        submit_label="Guardar cambios" if editing else "Guardar categoría",
        cancel_url=cancel_url,
        hidden_fields=tuple(hidden_fields),
    )


@login_required
def categorias_listado(request):
    """Muestra las categorías pertenecientes al usuario."""

    categories = (
        Categoria.objects.filter(usuario=request.user)
        .annotate(cantidad_tareas=Count("tareas"))
        .order_by("-activa", "nombre")
    )
    context = {
        "categorias": categories,
        "cantidad_categorias": categories.count(),
        "cantidad_activas": categories.filter(activa=True).count(),
        "cantidad_inactivas": categories.filter(activa=False).count(),
    }
    return render(request, "agenda/categorias_listado.html", context)


@login_required
def categoria_crear(request):
    """Crea una categoría mediante modal AJAX o página completa."""

    return_url = get_return_url(request, reverse("agenda:categorias_listado"))
    hidden_fields = ({"name": "return_url", "value": return_url},)

    if request.method == "POST":
        form = CategoriaForm(request.POST, usuario=request.user)

        if form.is_valid():
            category = form.save(commit=False)
            category.usuario = request.user
            category.save()
            return saved_response(
                request,
                message="La categoría se creó correctamente.",
                redirect_url=return_url,
                created=True,
            )

        return form_response(
            request,
            form,
            _category_form_config(
                editing=False,
                cancel_url=return_url,
                hidden_fields=hidden_fields,
            ),
            invalid=True,
        )

    form = CategoriaForm(usuario=request.user)
    return form_response(
        request,
        form,
        _category_form_config(
            editing=False,
            cancel_url=return_url,
            hidden_fields=hidden_fields,
        ),
    )


@login_required
def categoria_editar(request, categoria_id):
    """Edita una categoría perteneciente al usuario."""

    category = get_object_or_404(
        Categoria,
        id=categoria_id,
        usuario=request.user,
    )
    return_url = get_return_url(request, reverse("agenda:categorias_listado"))
    hidden_fields = ({"name": "return_url", "value": return_url},)

    if request.method == "POST":
        form = CategoriaForm(
            request.POST,
            instance=category,
            usuario=request.user,
        )

        if form.is_valid():
            form.save()
            return saved_response(
                request,
                message="La categoría se actualizó correctamente.",
                redirect_url=return_url,
            )

        return form_response(
            request,
            form,
            _category_form_config(
                editing=True,
                cancel_url=return_url,
                hidden_fields=hidden_fields,
            ),
            invalid=True,
        )

    form = CategoriaForm(instance=category, usuario=request.user)
    return form_response(
        request,
        form,
        _category_form_config(
            editing=True,
            cancel_url=return_url,
            hidden_fields=hidden_fields,
        ),
    )


@login_required
@require_POST
def categoria_cambiar_estado(request, categoria_id):
    """Activa o desactiva una categoría."""

    category = get_object_or_404(
        Categoria,
        id=categoria_id,
        usuario=request.user,
    )
    category.activa = not category.activa
    category.save(update_fields=["activa", "actualizada_en"])

    return_url = get_return_url(request, reverse("agenda:categorias_listado"))
    message = "La categoría se activó." if category.activa else "La categoría se desactivó."
    return saved_response(
        request,
        message=message,
        redirect_url=return_url,
    )


@login_required
@require_http_methods(["GET", "POST"])
def categoria_eliminar(request, categoria_id):
    """Elimina una categoría sin eliminar sus tareas ni sus eventos."""

    category = get_object_or_404(
        Categoria,
        id=categoria_id,
        usuario=request.user,
    )
    fallback = reverse("agenda:categorias_listado")
    return_url = get_return_url(request, fallback)

    if request.method == "POST":
        name = category.nombre
        category.delete()
        return saved_response(
            request,
            message=f'La categoría "{name}" se eliminó correctamente.',
            redirect_url=return_url,
        )

    task_count = category.tareas.count()
    event_count = category.eventos.count()
    config = ConfirmationViewConfig(
        eyebrow="Eliminar categoría",
        title=f'¿Eliminar "{category.nombre}"?',
        description=(
            "Las tareas y los eventos asociados no se eliminarán; quedarán "
            "guardados como elementos sin categoría."
        ),
        icon="!",
        confirm_label="Eliminar categoría",
        cancel_url=return_url,
        action_url=reverse("agenda:categoria_eliminar", args=[category.id]),
        details=(
            f"{task_count} tarea{'s' if task_count != 1 else ''} perderán esta categoría.",
            f"{event_count} evento{'s' if event_count != 1 else ''} perderán esta categoría.",
        ),
        hidden_fields=({"name": "return_url", "value": return_url},),
    )
    return confirmation_response(request, config)
