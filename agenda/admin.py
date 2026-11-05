from django.contrib import admin

from .models import (
    Categoria,
    ConfiguracionAutomatizacion,
    EntregaNotificacion,
    Evento,
    PreferenciasUsuario,
    SuscripcionPush,
    Tarea,
)


@admin.register(ConfiguracionAutomatizacion)
class ConfiguracionAutomatizacionAdmin(admin.ModelAdmin):
    list_display = (
        "endpoint_url",
        "activa",
        "ultima_ejecucion_en",
        "ultimo_estado",
        "ultimo_enviados",
        "ultimo_fallidos",
    )
    readonly_fields = (
        "endpoint_url",
        "dispatch_token",
        "activa",
        "actualizada_en",
        "ultima_ejecucion_en",
        "ultimo_exito_en",
        "ultimo_estado",
        "ultimo_error",
        "ultimo_enviados",
        "ultimo_fallidos",
        "ultimo_omitidos",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SuscripcionPush)
class SuscripcionPushAdmin(admin.ModelAdmin):
    list_display = (
        "usuario",
        "activa",
        "actualizada_en",
        "ultimo_envio_correcto_en",
    )
    list_filter = ("activa",)
    readonly_fields = (
        "usuario",
        "endpoint",
        "clave_p256dh",
        "clave_auth",
        "expiracion_milisegundos",
        "agente_usuario",
        "creada_en",
        "actualizada_en",
        "ultimo_envio_correcto_en",
    )

    def get_queryset(self, request):
        return super().get_queryset(request).filter(usuario=request.user)


@admin.register(EntregaNotificacion)
class EntregaNotificacionAdmin(admin.ModelAdmin):
    list_display = (
        "etiqueta",
        "suscripcion",
        "intentos",
        "ultimo_intento_en",
        "entregada_en",
    )
    readonly_fields = (
        "suscripcion",
        "etiqueta",
        "intentos",
        "ultimo_intento_en",
        "entregada_en",
        "ultimo_error",
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .filter(suscripcion__usuario=request.user)
        )


@admin.register(PreferenciasUsuario)
class PreferenciasUsuarioAdmin(admin.ModelAdmin):
    list_display = (
        "usuario",
        "tema_interfaz",
        "vista_calendario",
        "hora_inicio_evento",
        "duracion_evento_minutos",
        "avisos_sin_fecha_activos",
        "dias_aviso_sin_fecha",
    )

    exclude = ("usuario",)

    def get_queryset(self, request):
        return super().get_queryset(request).filter(usuario=request.user)

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.usuario = request.user

        super().save_model(request, obj, form, change)


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = (
        "nombre",
        "color",
        "activa",
        "creada_en",
    )

    list_filter = (
        "activa",
    )

    search_fields = (
        "nombre",
    )

    exclude = (
        "usuario",
    )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)

        return queryset.filter(
            usuario=request.user,
        )

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.usuario = request.user

        super().save_model(
            request,
            obj,
            form,
            change,
        )


@admin.register(Tarea)
class TareaAdmin(admin.ModelAdmin):
    list_display = (
        "titulo",
        "estado",
        "prioridad",
        "fecha_limite",
        "categoria",
        "actualizada_en",
    )

    list_filter = (
        "estado",
        "prioridad",
        "fecha_limite",
        "categoria",
    )

    search_fields = (
        "titulo",
        "descripcion",
    )

    autocomplete_fields = (
        "categoria",
    )

    exclude = (
        "usuario",
    )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)

        return queryset.filter(
            usuario=request.user,
        )

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.usuario = request.user

        super().save_model(
            request,
            obj,
            form,
            change,
        )


@admin.register(Evento)
class EventoAdmin(admin.ModelAdmin):
    list_display = (
        "titulo",
        "inicio",
        "fin",
        "todo_el_dia",
        "estado",
        "categoria",
    )

    list_filter = (
        "estado",
        "todo_el_dia",
        "inicio",
        "categoria",
    )

    search_fields = (
        "titulo",
        "descripcion",
        "ubicacion",
        "ical_uid",
    )

    autocomplete_fields = (
        "categoria",
    )

    exclude = (
        "usuario",
    )

    readonly_fields = (
        "ical_uid",
    )

    date_hierarchy = "inicio"

    def get_queryset(self, request):
        queryset = super().get_queryset(request)

        return queryset.filter(
            usuario=request.user,
        )

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.usuario = request.user

        super().save_model(
            request,
            obj,
            form,
            change,
        )
