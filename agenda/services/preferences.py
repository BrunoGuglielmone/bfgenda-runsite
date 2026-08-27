from agenda.models import PreferenciasUsuario


USER_PREFERENCES_CACHE_ATTR = "_agende_preferences_cache"


def get_user_preferences(user) -> PreferenciasUsuario:
    """Obtiene o crea las preferencias del usuario y las cachea en la petición."""

    cached = getattr(user, USER_PREFERENCES_CACHE_ATTR, None)

    if cached is not None:
        return cached

    preferences, _ = PreferenciasUsuario.objects.get_or_create(usuario=user)
    setattr(user, USER_PREFERENCES_CACHE_ATTR, preferences)
    return preferences
