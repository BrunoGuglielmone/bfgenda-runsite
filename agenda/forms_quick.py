"""Formularios compactos y seguros para el acceso rápido público."""

from django import forms


PIN_WIDGET_ATTRS = {
    "class": "quick-access-input quick-access-pin",
    "inputmode": "numeric",
    "autocomplete": "one-time-code",
    "pattern": "[0-9]{4}",
    "maxlength": "4",
    "placeholder": "••••",
}


def validate_pin(value: str) -> str:
    pin = str(value or "").strip()

    if len(pin) != 4 or not pin.isdigit():
        raise forms.ValidationError("El PIN debe contener exactamente 4 números.")

    return pin


class QuickCredentialsForm(forms.Form):
    """Agrega usuario y PIN con los mismos nombres y validaciones."""

    username = forms.CharField(
        label="Usuario",
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "class": "quick-access-input",
                "autocomplete": "username",
                "placeholder": "Tu usuario",
                "data-remembered-username": "",
            }
        ),
    )
    pin = forms.CharField(
        label="PIN de 4 dígitos",
        min_length=4,
        max_length=4,
        validators=(validate_pin,),
        widget=forms.PasswordInput(attrs=PIN_WIDGET_ATTRS, render_value=True),
    )


class QuickTaskForm(QuickCredentialsForm):
    titulo = forms.CharField(
        label="Tarea",
        max_length=180,
        widget=forms.TextInput(
            attrs={
                "class": "quick-access-input",
                "placeholder": "Ejemplo: Comprar materiales",
                "data-quick-autofocus": "",
            }
        ),
    )
    fecha_limite = forms.DateField(
        label="Fecha opcional",
        required=False,
        input_formats=("%Y-%m-%d",),
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={"class": "quick-access-input", "type": "date"},
        ),
    )
    hora_limite = forms.TimeField(
        label="Hora opcional",
        required=False,
        input_formats=("%H:%M", "%H:%M:%S"),
        widget=forms.TimeInput(
            format="%H:%M",
            attrs={"class": "quick-access-input", "type": "time"},
        ),
    )

    def clean(self):
        cleaned_data = super().clean()

        if cleaned_data.get("hora_limite") and not cleaned_data.get("fecha_limite"):
            self.add_error(
                "hora_limite",
                "Selecciona una fecha para poder indicar una hora.",
            )

        return cleaned_data


class QuickEventForm(QuickCredentialsForm):
    DURATIONS = (
        (30, "30 minutos"),
        (60, "1 hora"),
        (90, "1 hora y 30 minutos"),
        (120, "2 horas"),
    )

    titulo = forms.CharField(
        label="Evento",
        max_length=180,
        widget=forms.TextInput(
            attrs={
                "class": "quick-access-input",
                "placeholder": "Ejemplo: Reunión de equipo",
                "data-quick-autofocus": "",
            }
        ),
    )
    inicio = forms.DateTimeField(
        label="Fecha y hora",
        input_formats=("%Y-%m-%dT%H:%M",),
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"class": "quick-access-input", "type": "datetime-local"},
        ),
    )
    duracion_minutos = forms.TypedChoiceField(
        label="Duración",
        choices=DURATIONS,
        coerce=int,
        initial=60,
        widget=forms.Select(attrs={"class": "quick-access-input"}),
    )


class QuickPinConfigurationForm(forms.Form):
    current_password = forms.CharField(
        label="Contraseña actual",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "autocomplete": "current-password",
            }
        ),
    )
    pin = forms.CharField(
        label="Nuevo PIN",
        min_length=4,
        max_length=4,
        validators=(validate_pin,),
        help_text="Utiliza cuatro números que puedas recordar.",
        widget=forms.PasswordInput(
            attrs={**PIN_WIDGET_ATTRS, "class": "form-control"},
            render_value=True,
        ),
    )
    pin_confirmation = forms.CharField(
        label="Repetir PIN",
        min_length=4,
        max_length=4,
        validators=(validate_pin,),
        widget=forms.PasswordInput(
            attrs={**PIN_WIDGET_ATTRS, "class": "form-control"},
            render_value=True,
        ),
    )

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario

    def clean_current_password(self):
        password = self.cleaned_data["current_password"]

        if self.usuario is None or not self.usuario.check_password(password):
            raise forms.ValidationError("La contraseña actual no es correcta.")

        return password

    def clean(self):
        cleaned_data = super().clean()
        pin = cleaned_data.get("pin")
        confirmation = cleaned_data.get("pin_confirmation")

        if pin and confirmation and pin != confirmation:
            self.add_error("pin_confirmation", "Los dos PIN no coinciden.")

        return cleaned_data


class QuickPinRecoveryForm(forms.Form):
    username = forms.CharField(
        label="Usuario",
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "class": "quick-access-input",
                "autocomplete": "username",
                "placeholder": "Tu usuario",
                "data-remembered-username": "",
            }
        ),
    )
    password = forms.CharField(
        label="Contraseña de la cuenta",
        widget=forms.PasswordInput(
            attrs={
                "class": "quick-access-input",
                "autocomplete": "current-password",
                "placeholder": "Tu contraseña",
            }
        ),
    )
    pin = forms.CharField(
        label="Nuevo PIN",
        min_length=4,
        max_length=4,
        validators=(validate_pin,),
        widget=forms.PasswordInput(attrs=PIN_WIDGET_ATTRS, render_value=True),
    )
    pin_confirmation = forms.CharField(
        label="Repetir PIN",
        min_length=4,
        max_length=4,
        validators=(validate_pin,),
        widget=forms.PasswordInput(attrs=PIN_WIDGET_ATTRS, render_value=True),
    )

    def clean(self):
        cleaned_data = super().clean()
        pin = cleaned_data.get("pin")
        confirmation = cleaned_data.get("pin_confirmation")

        if pin and confirmation and pin != confirmation:
            self.add_error("pin_confirmation", "Los dos PIN no coinciden.")

        return cleaned_data
