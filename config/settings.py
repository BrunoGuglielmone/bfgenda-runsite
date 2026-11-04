"""Configuración principal de BFGenda."""

from __future__ import annotations

import os
from pathlib import Path

from .database import database_config
from .env import (
    env_bool,
    env_int,
    env_list,
    load_env_file,
    local_ipv4_addresses,
)


BASE_DIR = Path(__file__).resolve().parent.parent
load_env_file(BASE_DIR / ".env")


# -----------------------------------------------------------------------------
# Seguridad y entorno
# -----------------------------------------------------------------------------

# El instalador crea AGENDE_SECRET_KEY dentro del archivo privado .env.
# El valor alternativo conserva compatibilidad con el proyecto de desarrollo
# cuando todavía no se haya ejecutado el instalador estable.
SECRET_KEY = os.getenv(
    "AGENDE_SECRET_KEY",
    "django-insecure-cexrt5(+pry!q!)u^3(154h+n5$hrj0hdikqh7_%0)!vx+vknf",
)

DEBUG = env_bool("AGENDE_DEBUG", True)

ALLOWED_HOSTS = sorted(
    set(
        env_list(
            "AGENDE_ALLOWED_HOSTS",
            default=(
                "127.0.0.1",
                "localhost",
                "192.168.1.19",
            ),
        )
        + local_ipv4_addresses()
    )
)

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True


# -----------------------------------------------------------------------------
# Aplicaciones y middleware
# -----------------------------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "agenda.apps.AgendaConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "agenda.middleware.MaintenanceMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "agenda.middleware.CompletedTaskRetentionMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# -----------------------------------------------------------------------------
# Base de datos
# -----------------------------------------------------------------------------

DATABASES = {"default": database_config(BASE_DIR)}


# -----------------------------------------------------------------------------
# Contraseñas
# -----------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "MinimumLengthValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "CommonPasswordValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "NumericPasswordValidator"
        ),
    },
]


# -----------------------------------------------------------------------------
# Idioma y zona horaria
# -----------------------------------------------------------------------------

LANGUAGE_CODE = "es"
TIME_ZONE = "America/Montevideo"
USE_I18N = True
USE_TZ = True


# -----------------------------------------------------------------------------
# Archivos estáticos
# -----------------------------------------------------------------------------

STATIC_URL = "/static/"
STATIC_ROOT = Path(
    os.getenv("AGENDE_STATIC_ROOT")
    or BASE_DIR / "staticfiles"
)

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage."
            "CompressedManifestStaticFilesStorage"
        ),
    },
}


# -----------------------------------------------------------------------------
# Autenticación
# -----------------------------------------------------------------------------

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "agenda:inicio"
LOGOUT_REDIRECT_URL = "login"


# -----------------------------------------------------------------------------
# Funciones propias de BFGenda
# -----------------------------------------------------------------------------

AGENDE_BACKUP_DIR = Path(
    os.getenv("AGENDE_BACKUP_DIR")
    or BASE_DIR / "backups"
)
AGENDE_AUTOMATIC_BACKUPS = env_bool(
    "AGENDE_AUTOMATIC_BACKUPS",
    DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3",
)
AGENDE_AUTO_BACKUP_LIMIT = 30

# El apagado desde el navegador solo se habilita temporalmente después de
# cerrar una sesión de superusuario desde el mismo computador servidor.
AGENDE_WEB_SHUTDOWN_ENABLED = env_bool(
    "AGENDE_WEB_SHUTDOWN_ENABLED",
    True,
)
AGENDE_WEB_SHUTDOWN_WINDOW_SECONDS = env_int(
    "AGENDE_WEB_SHUTDOWN_WINDOW_SECONDS",
    600,
    minimum=60,
)
AGENDE_WEB_SHUTDOWN_DELAY_SECONDS = env_int(
    "AGENDE_WEB_SHUTDOWN_DELAY_SECONDS",
    3,
    minimum=1,
)

# Web Push. La clave privada puede ser un PEM fuera del repositorio o una
# clave DER codificada, ambos formatos admitidos por pywebpush.
AGENDE_VAPID_PUBLIC_KEY = os.getenv(
    "AGENDE_VAPID_PUBLIC_KEY",
    "",
).strip()
AGENDE_VAPID_PRIVATE_KEY = os.getenv(
    "AGENDE_VAPID_PRIVATE_KEY",
    "",
).strip()
AGENDE_VAPID_SUBJECT = os.getenv(
    "AGENDE_VAPID_SUBJECT",
    "mailto:admin@localhost",
).strip()

# Un host con una única instancia puede ejecutar el despachador dentro del
# proceso web. Se mantiene apagado por defecto para no duplicar envíos en el
# desarrollo local ni en despliegues con más de una réplica.
AGENDE_PUSH_SCHEDULER_ENABLED = env_bool(
    "AGENDE_PUSH_SCHEDULER_ENABLED",
    False,
)
AGENDE_PUSH_SCHEDULER_INTERVAL_SECONDS = env_int(
    "AGENDE_PUSH_SCHEDULER_INTERVAL_SECONDS",
    60,
    minimum=30,
)


# -----------------------------------------------------------------------------
# Registro de actividad y errores
# -----------------------------------------------------------------------------

LOG_DIR = Path(
    os.getenv("AGENDE_LOG_DIR")
    or BASE_DIR / "logs"
)
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "detailed": {
            "format": (
                "{asctime} | {levelname:<8} | {name} | "
                "{message}"
            ),
            "style": "{",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "simple": {
            "format": "{levelname}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
            "level": "INFO",
        },
        "application_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "bfgenda.log",
            "maxBytes": 2 * 1024 * 1024,
            "backupCount": 5,
            "encoding": "utf-8",
            "delay": True,
            "formatter": "detailed",
            "level": "INFO",
        },
        "server_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "servidor.log",
            "maxBytes": 2 * 1024 * 1024,
            "backupCount": 5,
            "encoding": "utf-8",
            "delay": True,
            "formatter": "detailed",
            "level": "INFO",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console", "application_file"],
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console", "application_file"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.db.backends": {
            "handlers": ["application_file"],
            "level": "WARNING",
            "propagate": False,
        },
        "agenda": {
            "handlers": ["console", "application_file"],
            "level": "INFO",
            "propagate": False,
        },
        "waitress": {
            "handlers": ["console", "server_file"],
            "level": "INFO",
            "propagate": False,
        },
    },
}


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Configuracion HTTPS privada mediante Tailscale Serve
CSRF_TRUSTED_ORIGINS = env_list(
    "AGENDE_CSRF_TRUSTED_ORIGINS",
    default=(),
)

# Opciones de producción activadas por el entorno del host. Se mantienen
# deshabilitadas por defecto para no alterar el desarrollo HTTP local.
SESSION_COOKIE_SECURE = env_bool("AGENDE_SESSION_COOKIE_SECURE", False)
CSRF_COOKIE_SECURE = env_bool("AGENDE_CSRF_COOKIE_SECURE", False)
SECURE_SSL_REDIRECT = env_bool("AGENDE_SECURE_SSL_REDIRECT", False)
SECURE_PROXY_SSL_HEADER = (
    ("HTTP_X_FORWARDED_PROTO", "https")
    if env_bool("AGENDE_TRUST_X_FORWARDED_PROTO", False)
    else None
)
SECURE_HSTS_SECONDS = env_int(
    "AGENDE_SECURE_HSTS_SECONDS",
    0,
    minimum=0,
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool(
    "AGENDE_SECURE_HSTS_INCLUDE_SUBDOMAINS",
    False,
)
SECURE_HSTS_PRELOAD = env_bool("AGENDE_SECURE_HSTS_PRELOAD", False)
