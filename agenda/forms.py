from datetime import timedelta

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q

from .models import Categoria, Evento, PreferenciasUsuario, Tarea
from .services.icalendar_io import MAX_ICS_FILE_BYTES
from .services.recurrence import (
    MAX_REPEAT_DAYS,
    REPEAT_MONTHLY,
    REPEAT_WEEKLY,
    normalize_repeat_mode,
)


FORM_CONTROL = "form-control"
WEEKDAY_NAMES = (
    "lunes",
    "martes",
    "miércoles",
    "jueves",
    "viernes",
    "sábado",
    "domingo",
)


CATEGORY_NEUTRAL_COLOR = "#9A9EAD"


def normalize_category_color(value) -> str:
    """Devuelve solamente colores hexadecimales seguros para la interfaz."""
    color = str(value or "").strip()

    if (
        len(color) == 7
        and color.startswith("#")
        and all(character in "0123456789abcdefABCDEF" for character in color[1:])
    ):
        return color

    return CATEGORY_NEUTRAL_COLOR


class CategorySelect(forms.Select):
    """Selector nativo que expone el color de cada categoría a la interfaz."""

    def __init__(self, attrs=None, choices=()):
        default_attrs = {
            "class": FORM_CONTROL,
            "data-category-select-input": "",
        }
        default_attrs.update(attrs or {})
        super().__init__(attrs=default_attrs, choices=choices)
        self.category_colors = {}

    def configure_colors(self, queryset) -> None:
        self.category_colors = {
            str(category_id): normalize_category_color(color)
            for category_id, color in queryset.values_list("pk", "color")
        }

    def create_option(
        self,
        name,
        value,
        label,
        selected,
        index,
        subindex=None,
        attrs=None,
    ):
        option = super().create_option(
            name,
            value,
            label,
            selected,
            index,
            subindex=subindex,
            attrs=attrs,
        )
        normalized_value = getattr(value, "value", value)
        option["attrs"]["data-category-color"] = self.category_colors.get(
            str(normalized_value),
            CATEGORY_NEUTRAL_COLOR,
        )
        return option


class RepeatUntilMixin:
    """Agrega una fecha final cuando el formulario crea una serie."""

    def configure_repeat(self, *, repeat_mode=None, start_date=None) -> None:
        self.repeat_mode = normalize_repeat_mode(repeat_mode)

        if self.repeat_mode is None:
            return

        field = forms.DateField(
            required=True,
            label="Repetir hasta",
            input_formats=("%Y-%m-%d", "%d/%m/%Y"),
            widget=forms.DateInput(
                format="%Y-%m-%d",
                attrs={"class": FORM_CONTROL, "type": "date"},
            ),
        )
        self.fields["repetir_hasta"] = field
        self.layout = (*self.layout, ("repetir_hasta",))

        if start_date is None:
            return

        if self.repeat_mode == REPEAT_WEEKLY:
            field.label = (
                f"Repetir todos los {WEEKDAY_NAMES[start_date.weekday()]} hasta"
            )
            field.initial = start_date + timedelta(weeks=8)
        else:
            field.label = f"Repetir el día {start_date.day} de cada mes hasta"
            field.help_text = (
                "Los meses que no tengan ese número de día se omitirán."
            )
            field.initial = start_date + timedelta(days=MAX_REPEAT_DAYS)

    def validate_repeat(self, start_date) -> None:
        if self.repeat_mode is None:
            return

        end_date = self.cleaned_data.get("repetir_hasta")

        if start_date is None:
            self.add_error(
                "repetir_hasta",
                "Primero debes indicar la fecha inicial de la serie.",
            )
            return

        if end_date is None:
            return

        if end_date < start_date:
            self.add_error(
                "repetir_hasta",
                "La fecha final no puede ser anterior a la primera fecha.",
            )
        elif end_date > start_date + timedelta(days=MAX_REPEAT_DAYS):
            self.add_error(
                "repetir_hasta",
                "La repetición puede abarcar como máximo un año.",
            )


class UserCategoryMixin:
    """Limita el selector de categorías al usuario autenticado."""

    def configure_category_field(self, usuario) -> None:
        field = self.fields["categoria"]
        field.required = False
        field.empty_label = "Sin categoría"

        if usuario is None:
            field.queryset = Categoria.objects.none()
            return

        available = Categoria.objects.filter(usuario=usuario, activa=True)
        current_category_id = getattr(self.instance, "categoria_id", None)

        if self.instance.pk and current_category_id:
            available = Categoria.objects.filter(
                Q(usuario=usuario, activa=True)
                | Q(usuario=usuario, id=current_category_id)
            )

        field.queryset = available.distinct().order_by("nombre")

        if isinstance(field.widget, CategorySelect):
            field.widget.configure_colors(field.queryset)


class TareaForm(RepeatUntilMixin, UserCategoryMixin, forms.ModelForm):
    """Formulario para crear y editar tareas."""

    layout = (
        ("titulo",),
        ("descripcion",),
        ("fecha_limite", "hora_limite"),
        ("prioridad", "categoria"),
    )

    class Meta:
        model = Tarea
        fields = (
            "titulo",
            "descripcion",
            "fecha_limite",
            "hora_limite",
            "prioridad",
            "categoria",
        )
        labels = {
            "titulo": "Título",
            "descripcion": "Descripción",
            "fecha_limite": "Fecha límite",
            "hora_limite": "Hora límite",
            "prioridad": "Prioridad",
            "categoria": "Categoría",
        }
        widgets = {
            "titulo": forms.TextInput(
                attrs={
                    "class": FORM_CONTROL,
                    "placeholder": "Ejemplo: Terminar planificación",
                    "data-autofocus": "true",
                }
            ),
            "descripcion": forms.Textarea(
                attrs={
                    "class": FORM_CONTROL,
                    "placeholder": "Información adicional opcional",
                    "rows": 4,
                }
            ),
            "fecha_limite": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"class": FORM_CONTROL, "type": "date"},
            ),
            "hora_limite": forms.TimeInput(
                format="%H:%M",
                attrs={"class": FORM_CONTROL, "type": "time"},
            ),
            "prioridad": forms.Select(attrs={"class": FORM_CONTROL}),
            "categoria": CategorySelect(),
        }

    def __init__(
        self,
        *args,
        usuario=None,
        modo_repeticion=None,
        fecha_referencia=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.fields["fecha_limite"].input_formats = ("%Y-%m-%d", "%d/%m/%Y")
        self.fields["hora_limite"].input_formats = ("%H:%M", "%H:%M:%S")
        self.configure_category_field(usuario)
        self.configure_repeat(
            repeat_mode=modo_repeticion,
            start_date=fecha_referencia,
        )

        if self.repeat_mode:
            self.fields["fecha_limite"].required = True

    def clean(self):
        cleaned_data = super().clean()

        if cleaned_data.get("hora_limite") and not cleaned_data.get("fecha_limite"):
            self.add_error(
                "hora_limite",
                "Para establecer una hora también debes seleccionar una fecha.",
            )

        self.validate_repeat(cleaned_data.get("fecha_limite"))
        return cleaned_data


class CategoriaForm(forms.ModelForm):
    """Formulario para crear y editar categorías."""

    layout = (("nombre", "color"),)

    class Meta:
        model = Categoria
        fields = ("nombre", "color")
        labels = {"nombre": "Nombre", "color": "Color"}
        widgets = {
            "nombre": forms.TextInput(
                attrs={
                    "class": FORM_CONTROL,
                    "placeholder": "Ejemplo: Estudio",
                    "data-autofocus": "true",
                }
            ),
            "color": forms.TextInput(
                attrs={"class": "color-control", "type": "color"}
            ),
        }

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario

    def clean_nombre(self):
        nombre = self.cleaned_data["nombre"].strip()

        if not nombre:
            raise ValidationError("Debes escribir un nombre para la categoría.")

        if self.usuario is None:
            return nombre

        duplicates = Categoria.objects.filter(
            usuario=self.usuario,
            nombre__iexact=nombre,
        )

        if self.instance.pk:
            duplicates = duplicates.exclude(id=self.instance.id)

        if duplicates.exists():
            raise ValidationError("Ya tienes una categoría con ese nombre.")

        return nombre


class EventoForm(RepeatUntilMixin, UserCategoryMixin, forms.ModelForm):
    """Formulario para crear y editar eventos."""

    layout = (
        ("titulo",),
        ("descripcion",),
        ("inicio", "fin"),
        ("categoria",),
        ("ubicacion",),
        ("todo_el_dia",),
    )

    class Meta:
        model = Evento
        fields = (
            "titulo",
            "descripcion",
            "inicio",
            "fin",
            "todo_el_dia",
            "ubicacion",
            "categoria",
        )
        labels = {
            "titulo": "Título",
            "descripcion": "Descripción",
            "inicio": "Inicio",
            "fin": "Finalización",
            "todo_el_dia": "Evento de todo el día",
            "ubicacion": "Ubicación",
            "categoria": "Categoría",
        }
        widgets = {
            "titulo": forms.TextInput(
                attrs={
                    "class": FORM_CONTROL,
                    "placeholder": "Ejemplo: Reunión de proyecto",
                    "data-autofocus": "true",
                }
            ),
            "descripcion": forms.Textarea(
                attrs={
                    "class": FORM_CONTROL,
                    "placeholder": "Información adicional opcional",
                    "rows": 4,
                }
            ),
            "inicio": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"class": FORM_CONTROL, "type": "datetime-local"},
            ),
            "fin": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"class": FORM_CONTROL, "type": "datetime-local"},
            ),
            "todo_el_dia": forms.CheckboxInput(attrs={"class": "checkbox-control"}),
            "ubicacion": forms.TextInput(
                attrs={
                    "class": FORM_CONTROL,
                    "placeholder": "Ejemplo: Casa, CeRP o videollamada",
                }
            ),
            "categoria": CategorySelect(),
        }

    def __init__(
        self,
        *args,
        usuario=None,
        modo_repeticion=None,
        fecha_referencia=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.fields["inicio"].input_formats = ("%Y-%m-%dT%H:%M",)
        self.fields["fin"].input_formats = ("%Y-%m-%dT%H:%M",)
        self.configure_category_field(usuario)
        self.configure_repeat(
            repeat_mode=modo_repeticion,
            start_date=fecha_referencia,
        )

    def clean(self):
        cleaned_data = super().clean()
        inicio = cleaned_data.get("inicio")
        fin = cleaned_data.get("fin")

        if inicio and fin and fin <= inicio:
            self.add_error(
                "fin",
                "La finalización debe ser posterior al comienzo del evento.",
            )

        self.validate_repeat(inicio.date() if inicio else None)
        return cleaned_data


class ImportarCalendarioForm(forms.Form):
    """Formulario de carga para calendarios iCalendar (.ics)."""

    layout = (
        ("archivo",),
        ("categoria",),
    )

    archivo = forms.FileField(
        label="Archivo iCalendar",
        help_text=(
            "Selecciona un archivo .ics de hasta 2 MB. "
            "Los eventos recurrentes se omitirán para no crear series incompletas."
        ),
        widget=forms.ClearableFileInput(
            attrs={
                "class": FORM_CONTROL,
                "accept": ".ics,text/calendar",
            }
        ),
    )

    categoria = forms.ModelChoiceField(
        label="Categoría para los eventos importados",
        required=False,
        queryset=Categoria.objects.none(),
        empty_label="Sin categoría",
        help_text=(
            "La categoría se aplicará a todos los eventos nuevos del archivo."
        ),
        widget=CategorySelect(),
    )

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)

        if usuario is not None:
            field = self.fields["categoria"]
            field.queryset = Categoria.objects.filter(
                usuario=usuario,
                activa=True,
            ).order_by("nombre")

            if isinstance(field.widget, CategorySelect):
                field.widget.configure_colors(field.queryset)

    def clean_archivo(self):
        archivo = self.cleaned_data["archivo"]
        nombre = (archivo.name or "").lower()

        if not nombre.endswith(".ics"):
            raise ValidationError("El archivo debe tener extensión .ics.")

        if archivo.size > MAX_ICS_FILE_BYTES:
            raise ValidationError("El archivo supera el límite de 2 MB.")

        return archivo


class PreferenciasUsuarioForm(forms.ModelForm):
    """Formulario reutilizable para las preferencias personales de BFGenda."""

    layout = (
        ("vista_calendario",),
        ("hora_inicio_evento", "duracion_evento_minutos"),
        ("avisos_sin_fecha_activos",),
        ("dias_aviso_sin_fecha",),
        (
            "recordatorios_tareas_activos",
            "recordatorios_eventos_activos",
        ),
        (
            "anticipacion_recordatorios_minutos",
            "anticipacion_eventos_minutos",
        ),
        ("hora_recordatorios_sin_hora",),
    )

    class Meta:
        model = PreferenciasUsuario
        fields = (
            "vista_calendario",
            "hora_inicio_evento",
            "duracion_evento_minutos",
            "avisos_sin_fecha_activos",
            "dias_aviso_sin_fecha",
            "recordatorios_tareas_activos",
            "recordatorios_eventos_activos",
            "anticipacion_recordatorios_minutos",
            "anticipacion_eventos_minutos",
            "hora_recordatorios_sin_hora",
        )
        labels = {
            "vista_calendario": "Vista inicial del calendario",
            "hora_inicio_evento": "Hora inicial para eventos nuevos",
            "duracion_evento_minutos": "Duración inicial del evento",
            "avisos_sin_fecha_activos": "Mostrar recordatorios de tareas sin fecha",
            "dias_aviso_sin_fecha": "Avisar cuando lleven sin fecha",
            "recordatorios_tareas_activos": "Recordatorios de tareas",
            "recordatorios_eventos_activos": "Recordatorios de eventos",
            "anticipacion_recordatorios_minutos": (
                "Anticipación para tareas"
            ),
            "anticipacion_eventos_minutos": (
                "Anticipación para eventos"
            ),
            "hora_recordatorios_sin_hora": (
                "Hora para elementos sin una hora específica"
            ),
        }
        help_texts = {
            "vista_calendario": (
                "Se utilizará cuando abras Calendario sin elegir una vista concreta."
            ),
            "hora_inicio_evento": (
                "Solo completa el valor inicial; puedes cambiarlo al crear cada evento."
            ),
            "duracion_evento_minutos": (
                "Define la finalización inicial calculada para eventos nuevos."
            ),
            "avisos_sin_fecha_activos": (
                "El aviso aparece como máximo una vez por día en Inicio."
            ),
            "dias_aviso_sin_fecha": (
                "Las tareas siguen existiendo aunque desactives el recordatorio."
            ),
            "recordatorios_tareas_activos": (
                "Permite avisos para tareas con fecha límite."
            ),
            "recordatorios_eventos_activos": (
                "Permite avisos para eventos programados."
            ),
            "anticipacion_recordatorios_minutos": (
                "Se aplica a tareas que tienen una hora límite."
            ),
            "anticipacion_eventos_minutos": (
                "Define cuánto antes se avisa sobre un evento con horario."
            ),
            "hora_recordatorios_sin_hora": (
                "Se utiliza para tareas sin hora y eventos de todo el día."
            ),
        }
        widgets = {
            "vista_calendario": forms.Select(attrs={"class": FORM_CONTROL}),
            "hora_inicio_evento": forms.TimeInput(
                format="%H:%M",
                attrs={"class": FORM_CONTROL, "type": "time"},
            ),
            "duracion_evento_minutos": forms.Select(
                attrs={"class": FORM_CONTROL}
            ),
            "avisos_sin_fecha_activos": forms.CheckboxInput(
                attrs={"class": "checkbox-control"}
            ),
            "dias_aviso_sin_fecha": forms.Select(
                attrs={"class": FORM_CONTROL}
            ),
            "recordatorios_tareas_activos": forms.CheckboxInput(
                attrs={"class": "checkbox-control"}
            ),
            "recordatorios_eventos_activos": forms.CheckboxInput(
                attrs={"class": "checkbox-control"}
            ),
            "anticipacion_recordatorios_minutos": forms.Select(
                attrs={"class": FORM_CONTROL}
            ),
            "anticipacion_eventos_minutos": forms.Select(
                attrs={"class": FORM_CONTROL}
            ),
            "hora_recordatorios_sin_hora": forms.TimeInput(
                format="%H:%M",
                attrs={
                    "class": FORM_CONTROL,
                    "type": "time",
                },
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["hora_inicio_evento"].input_formats = ("%H:%M", "%H:%M:%S")
        self.fields["hora_recordatorios_sin_hora"].input_formats = (
            "%H:%M",
            "%H:%M:%S",
        )
