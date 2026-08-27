from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.template.loader import render_to_string

from agenda.services.search import (
    MODAL_RESULTS_PER_GROUP,
    PAGE_RESULTS_PER_GROUP,
    global_search,
)

from .common import is_ajax


@login_required
def busqueda(request):
    """Busca tareas, eventos y categorías del usuario autenticado."""

    partial = request.GET.get("partial") == "resultados"
    page_mode = request.GET.get("mode") == "page"
    limit = (
        PAGE_RESULTS_PER_GROUP
        if page_mode or not is_ajax(request)
        else MODAL_RESULTS_PER_GROUP
    )
    context = global_search(
        request.user,
        request.GET.get("q"),
        search_type=request.GET.get("tipo"),
        limit=limit,
    )
    context["url_busqueda"] = request.path

    if is_ajax(request):
        template_name = (
            "agenda/componentes/resultados_busqueda.html"
            if partial
            else "agenda/modales/busqueda_global.html"
        )
        html = render_to_string(template_name, context, request=request)
        return JsonResponse({"ok": True, "html": html})

    return render(request, "agenda/busqueda.html", context)
