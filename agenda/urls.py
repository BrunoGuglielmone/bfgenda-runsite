from django.urls import path

from . import views


app_name = "agenda"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path(
        "sistema/cerrar-sesion/",
        views.cerrar_sesion,
        name="cerrar_sesion",
    ),
    path(
        "sistema/detener/",
        views.detener_agende,
        name="detener_agende",
    ),
    path(
        "sistema/estado/",
        views.estado_agende,
        name="estado_agende",
    ),
    path("buscar/", views.busqueda, name="busqueda"),
    path(
        "notificaciones/pendientes/",
        views.recordatorios_pendientes,
        name="recordatorios_pendientes",
    ),
    path(
        "notificaciones/push/suscripcion/",
        views.suscripcion_push_guardar,
        name="suscripcion_push_guardar",
    ),
    path(
        "notificaciones/push/desactivar/",
        views.suscripcion_push_eliminar,
        name="suscripcion_push_eliminar",
    ),
    path(
        "notificaciones/push/probar/",
        views.suscripcion_push_probar,
        name="suscripcion_push_probar",
    ),
    path("configuracion/", views.configuracion, name="configuracion"),
    path(
        "configuracion/editar/",
        views.configuracion_editar,
        name="configuracion_editar",
    ),
    path(
        "configuracion/copias/crear/",
        views.backup_crear,
        name="backup_crear",
    ),
    path(
        "configuracion/copias/<str:backup_name>/descargar/",
        views.backup_descargar,
        name="backup_descargar",
    ),
    path(
        "configuracion/copias/<str:backup_name>/restaurar/",
        views.backup_restaurar,
        name="backup_restaurar",
    ),
    path(
        "configuracion/exportar/json/",
        views.exportar_json,
        name="exportar_json",
    ),
    path(
        "configuracion/exportar/csv/",
        views.exportar_csv,
        name="exportar_csv",
    ),
    path(
        "configuracion/calendario/exportar/",
        views.exportar_ics,
        name="exportar_ics",
    ),
    path(
        "configuracion/calendario/importar/",
        views.importar_ics,
        name="importar_ics",
    ),
    path("calendario/", views.calendario, name="calendario"),
    path(
        "calendario/dia/",
        views.calendario_dia_resumen,
        name="calendario_dia_resumen",
    ),
    path("eventos/", views.eventos_listado, name="eventos_listado"),
    path("eventos/resumen/", views.eventos_resumen, name="eventos_resumen"),
    path(
        "eventos/pasados/pendiente/",
        views.evento_pasado_pendiente,
        name="evento_pasado_pendiente",
    ),
    path(
        "eventos/<int:evento_id>/pasado/aviso/",
        views.evento_pasado_aviso,
        name="evento_pasado_aviso",
    ),
    path("eventos/nuevo/", views.evento_crear, name="evento_crear"),
    path(
        "eventos/<int:evento_id>/editar/",
        views.evento_editar,
        name="evento_editar",
    ),
    path(
        "eventos/<int:evento_id>/cancelar/",
        views.evento_cancelar,
        name="evento_cancelar",
    ),
    path(
        "eventos/<int:evento_id>/restaurar/",
        views.evento_restaurar,
        name="evento_restaurar",
    ),
    path(
        "eventos/<int:evento_id>/eliminar/",
        views.evento_eliminar,
        name="evento_eliminar",
    ),
    path(
        "eventos/<int:evento_id>/serie/eliminar/",
        views.evento_serie_eliminar,
        name="evento_serie_eliminar",
    ),
    path("tareas/", views.tareas_listado, name="tareas_listado"),
    path("tareas/resumen/", views.tareas_resumen, name="tareas_resumen"),
    path("tareas/nueva/", views.tarea_crear, name="tarea_crear"),
    path(
        "tareas/<int:tarea_id>/editar/",
        views.tarea_editar,
        name="tarea_editar",
    ),
    path(
        "tareas/<int:tarea_id>/eliminar/",
        views.tarea_eliminar,
        name="tarea_eliminar",
    ),
    path(
        "tareas/<int:tarea_id>/serie/eliminar/",
        views.tarea_serie_eliminar,
        name="tarea_serie_eliminar",
    ),
    path(
        "tareas/<int:tarea_id>/completar/",
        views.tarea_completar,
        name="tarea_completar",
    ),
    path(
        "tareas/<int:tarea_id>/restaurar/",
        views.tarea_restaurar,
        name="tarea_restaurar",
    ),
    path("categorias/", views.categorias_listado, name="categorias_listado"),
    path("categorias/nueva/", views.categoria_crear, name="categoria_crear"),
    path(
        "categorias/<int:categoria_id>/editar/",
        views.categoria_editar,
        name="categoria_editar",
    ),
    path(
        "categorias/<int:categoria_id>/eliminar/",
        views.categoria_eliminar,
        name="categoria_eliminar",
    ),
    path(
        "categorias/<int:categoria_id>/estado/",
        views.categoria_cambiar_estado,
        name="categoria_cambiar_estado",
    ),
]
