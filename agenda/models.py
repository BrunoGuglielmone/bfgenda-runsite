from datetime import time

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class PreferenciasUsuario(models.Model):
    """Preferencias personales que modifican el comportamiento de BFGenda."""

    class TemaInterfaz(models.TextChoices):
        SISTEMA = "sistema", "Automático (según el sistema)"
        CLARO = "claro", "Claro"
        OSCURO = "oscuro", "Oscuro"

    class VistaCalendario(models.TextChoices):
        DIA = "dia", "Día"
        SEMANA = "semana", "Semana"
        MES = "mes", "Mes"

    DURACIONES_EVENTO = (
        (30, "30 minutos"),
        (60, "1 hora"),
        (90, "1 hora y 30 minutos"),
        (120, "2 horas"),
    )

    DIAS_AVISO_SIN_FECHA = (
        (1, "Después de 1 día"),
        (3, "Después de 3 días"),
        (7, "Después de 7 días"),
        (14, "Después de 14 días"),
        (30, "Después de 30 días"),
    )

    ANTICIPACIONES_RECORDATORIO = (
        (0, "A la hora indicada"),
        (5, "5 minutos antes"),
        (10, "10 minutos antes"),
        (15, "15 minutos antes"),
        (30, "30 minutos antes"),
        (60, "1 hora antes"),
        (120, "2 horas antes"),
        (1440, "1 día antes"),
    )

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="preferencias_agenda",
        verbose_name="usuario",
    )

    tema_interfaz = models.CharField(
        max_length=10,
        choices=TemaInterfaz.choices,
        default=TemaInterfaz.SISTEMA,
        verbose_name="tema de la interfaz",
    )

    vista_calendario = models.CharField(
        max_length=10,
        choices=VistaCalendario.choices,
        default=VistaCalendario.MES,
        verbose_name="vista inicial del calendario",
    )

    hora_inicio_evento = models.TimeField(
        default=time(hour=9),
        verbose_name="hora inicial de eventos",
    )

    duracion_evento_minutos = models.PositiveSmallIntegerField(
        choices=DURACIONES_EVENTO,
        default=60,
        verbose_name="duración inicial de eventos",
    )

    avisos_sin_fecha_activos = models.BooleanField(
        default=True,
        verbose_name="avisar por tareas sin fecha",
    )

    dias_aviso_sin_fecha = models.PositiveSmallIntegerField(
        choices=DIAS_AVISO_SIN_FECHA,
        default=7,
        verbose_name="antigüedad para el aviso",
    )

    recordatorios_tareas_activos = models.BooleanField(
        default=True,
        verbose_name="recordatorios de tareas activos",
    )

    recordatorios_eventos_activos = models.BooleanField(
        default=True,
        verbose_name="recordatorios de eventos activos",
    )

    anticipacion_recordatorios_minutos = models.PositiveSmallIntegerField(
        choices=ANTICIPACIONES_RECORDATORIO,
        default=15,
        verbose_name="anticipación de recordatorios de tareas",
    )

    anticipacion_eventos_minutos = models.PositiveSmallIntegerField(
        choices=ANTICIPACIONES_RECORDATORIO,
        default=60,
        verbose_name="anticipación de recordatorios de eventos",
    )

    hora_recordatorios_sin_hora = models.TimeField(
        default=time(hour=9),
        verbose_name="hora de recordatorios sin hora especifica",
    )

    actualizada_en = models.DateTimeField(
        auto_now=True,
        verbose_name="actualizada en",
    )

    class Meta:
        verbose_name = "preferencias del usuario"
        verbose_name_plural = "preferencias de los usuarios"

    def __str__(self):
        return f"Preferencias de {self.usuario}"


class SuscripcionPush(models.Model):
    """Dispositivo autorizado por un usuario para recibir Web Push."""

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="suscripciones_push",
        verbose_name="usuario",
    )
    endpoint = models.TextField(
        unique=True,
        verbose_name="endpoint",
    )
    clave_p256dh = models.CharField(
        max_length=255,
        verbose_name="clave p256dh",
    )
    clave_auth = models.CharField(
        max_length=255,
        verbose_name="clave auth",
    )
    expiracion_milisegundos = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="expiración en milisegundos",
    )
    agente_usuario = models.CharField(
        max_length=300,
        blank=True,
        verbose_name="navegador",
    )
    activa = models.BooleanField(
        default=True,
        verbose_name="activa",
    )
    creada_en = models.DateTimeField(
        auto_now_add=True,
        verbose_name="creada en",
    )
    actualizada_en = models.DateTimeField(
        auto_now=True,
        verbose_name="actualizada en",
    )
    ultimo_envio_correcto_en = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="último envío correcto",
    )

    class Meta:
        verbose_name = "suscripción push"
        verbose_name_plural = "suscripciones push"
        ordering = ["-actualizada_en"]

    def __str__(self):
        estado = "activa" if self.activa else "inactiva"
        return f"Push de {self.usuario} ({estado})"


class EntregaNotificacion(models.Model):
    """Registro servidor de un recordatorio enviado a un dispositivo."""

    suscripcion = models.ForeignKey(
        SuscripcionPush,
        on_delete=models.CASCADE,
        related_name="entregas",
        verbose_name="suscripción",
    )
    etiqueta = models.CharField(
        max_length=220,
        verbose_name="etiqueta",
    )
    intentos = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="intentos",
    )
    ultimo_intento_en = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="último intento",
    )
    entregada_en = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="entregada en",
    )
    ultimo_error = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="último error",
    )

    class Meta:
        verbose_name = "entrega de notificación"
        verbose_name_plural = "entregas de notificaciones"
        ordering = ["-ultimo_intento_en", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["suscripcion", "etiqueta"],
                name="entrega_push_unica_por_suscripcion",
            ),
        ]

    def __str__(self):
        return f"{self.etiqueta} → {self.suscripcion_id}"


class ConfiguracionAutomatizacion(models.Model):
    """Conecta un programador externo sin publicar sus credenciales."""

    endpoint_url = models.URLField(
        max_length=500,
        verbose_name="URL del despachador",
    )
    dispatch_token = models.CharField(
        max_length=128,
        verbose_name="token del despachador",
    )
    activa = models.BooleanField(
        default=True,
        verbose_name="activa",
    )
    actualizada_en = models.DateTimeField(
        auto_now=True,
        verbose_name="actualizada en",
    )
    ultima_ejecucion_en = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="última ejecución",
    )
    ultimo_exito_en = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="último éxito",
    )
    ultimo_estado = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="último estado",
    )
    ultimo_error = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="último error",
    )
    ultimo_enviados = models.PositiveIntegerField(
        default=0,
        verbose_name="últimos enviados",
    )
    ultimo_fallidos = models.PositiveIntegerField(
        default=0,
        verbose_name="últimos fallidos",
    )
    ultimo_omitidos = models.PositiveIntegerField(
        default=0,
        verbose_name="últimos omitidos",
    )

    class Meta:
        db_table = "agenda_automatizacion_host"
        verbose_name = "automatización del host"
        verbose_name_plural = "automatizaciones del host"

    def __str__(self):
        return self.endpoint_url


class Categoria(models.Model):
    """
    Categoría personal utilizada para organizar tareas y eventos.
    """

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="categorias",
        verbose_name="usuario",
    )

    nombre = models.CharField(
        max_length=60,
        verbose_name="nombre",
    )

    color = models.CharField(
        max_length=7,
        default="#6657D9",
        verbose_name="color",
        help_text="Color hexadecimal. Ejemplo: #6657D9",
    )

    activa = models.BooleanField(
        default=True,
        verbose_name="activa",
    )

    creada_en = models.DateTimeField(
        auto_now_add=True,
        verbose_name="creada en",
    )

    actualizada_en = models.DateTimeField(
        auto_now=True,
        verbose_name="actualizada en",
    )

    class Meta:
        verbose_name = "categoría"
        verbose_name_plural = "categorías"
        ordering = ["nombre"]

        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "nombre"],
                name="categoria_nombre_unico_por_usuario",
            ),
        ]

    def __str__(self):
        return self.nombre


class Tarea(models.Model):
    """
    Actividad pendiente que puede tener una fecha límite
    o permanecer sin fecha.
    """

    class Prioridad(models.TextChoices):
        SIN_PRIORIDAD = "sin_prioridad", "Sin prioridad"
        BAJA = "baja", "Baja"
        MEDIA = "media", "Media"
        ALTA = "alta", "Alta"

    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        EN_PROGRESO = "en_progreso", "En progreso"
        COMPLETADA = "completada", "Completada"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tareas",
        verbose_name="usuario",
    )

    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tareas",
        verbose_name="categoría",
    )

    titulo = models.CharField(
        max_length=180,
        verbose_name="título",
    )

    descripcion = models.TextField(
        blank=True,
        verbose_name="descripción",
    )

    fecha_limite = models.DateField(
        null=True,
        blank=True,
        verbose_name="fecha límite",
    )

    hora_limite = models.TimeField(
        null=True,
        blank=True,
        verbose_name="hora límite",
    )

    prioridad = models.CharField(
        max_length=20,
        choices=Prioridad.choices,
        default=Prioridad.SIN_PRIORIDAD,
        verbose_name="prioridad",
    )

    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.PENDIENTE,
        verbose_name="estado",
    )

    completada_en = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="completada en",
    )

    serie_recurrencia = models.UUIDField(
        null=True,
        blank=True,
        editable=False,
        db_index=True,
        verbose_name="serie recurrente",
    )

    tipo_recurrencia = models.CharField(
        max_length=10,
        blank=True,
        editable=False,
        choices=(
            ("semanal", "Semanal"),
            ("mensual", "Mensual"),
        ),
        verbose_name="tipo de recurrencia",
    )

    creada_en = models.DateTimeField(
        auto_now_add=True,
        verbose_name="creada en",
    )

    actualizada_en = models.DateTimeField(
        auto_now=True,
        verbose_name="actualizada en",
    )

    class Meta:
        verbose_name = "tarea"
        verbose_name_plural = "tareas"
        ordering = ["-creada_en"]

    def __str__(self):
        return self.titulo


class Evento(models.Model):
    """
    Compromiso o actividad que sucede en un período determinado.
    """

    class Estado(models.TextChoices):
        PROGRAMADO = "programado", "Programado"
        REALIZADO = "realizado", "Realizado"
        CANCELADO = "cancelado", "Cancelado"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="eventos",
        verbose_name="usuario",
    )

    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eventos",
        verbose_name="categoría",
    )

    titulo = models.CharField(
        max_length=180,
        verbose_name="título",
    )

    descripcion = models.TextField(
        blank=True,
        verbose_name="descripción",
    )

    inicio = models.DateTimeField(
        verbose_name="inicio",
    )

    fin = models.DateTimeField(
        verbose_name="finalización",
    )

    todo_el_dia = models.BooleanField(
        default=False,
        verbose_name="todo el día",
    )

    ubicacion = models.CharField(
        max_length=220,
        blank=True,
        verbose_name="ubicación",
    )

    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.PROGRAMADO,
        verbose_name="estado",
    )

    ical_uid = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        editable=False,
        verbose_name="identificador iCalendar",
    )

    serie_recurrencia = models.UUIDField(
        null=True,
        blank=True,
        editable=False,
        db_index=True,
        verbose_name="serie recurrente",
    )

    tipo_recurrencia = models.CharField(
        max_length=10,
        blank=True,
        editable=False,
        choices=(
            ("semanal", "Semanal"),
            ("mensual", "Mensual"),
        ),
        verbose_name="tipo de recurrencia",
    )

    creado_en = models.DateTimeField(
        auto_now_add=True,
        verbose_name="creado en",
    )

    actualizado_en = models.DateTimeField(
        auto_now=True,
        verbose_name="actualizado en",
    )

    class Meta:
        verbose_name = "evento"
        verbose_name_plural = "eventos"
        ordering = ["inicio"]
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "ical_uid"],
                condition=models.Q(ical_uid__isnull=False),
                name="evento_ical_uid_unico_por_usuario",
            ),
        ]

    def clean(self):
        """
        Impide guardar un evento cuya finalización sea
        igual o anterior al inicio.
        """

        super().clean()

        if self.inicio and self.fin and self.fin <= self.inicio:
            raise ValidationError(
                {
                    "fin": (
                        "La fecha y hora de finalización deben ser "
                        "posteriores al inicio."
                    ),
                }
            )

    @property
    def esta_pasado(self):
        """Indica si el evento terminó y no está cancelado."""

        return (
            self.estado != self.Estado.CANCELADO
            and self.fin < timezone.now()
        )

    def __str__(self):
        return self.titulo
