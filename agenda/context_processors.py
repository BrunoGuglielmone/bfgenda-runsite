from agenda.models import PreferenciasUsuario
from agenda.services.preferences import get_user_preferences


def interface_theme(request):
    """Expone el tema elegido para aplicarlo antes de pintar cada pantalla."""

    preference = PreferenciasUsuario.TemaInterfaz.SISTEMA

    user = getattr(request, "user", None)

    if user is not None and user.is_authenticated:
        preference = get_user_preferences(user).tema_interfaz

    return {
        "tema_interfaz_preferencia": preference,
    }
