# Render + Neon

Este despliegue mantiene BFGenda disponible fuera del computador local:

- Render construye el `Dockerfile` mediante `render.yaml`.
- Neon conserva PostgreSQL fuera del sistema de archivos efímero del host.
- Una Neon Function programada invoca el despachador privado de Web Push.
- Los secretos permanecen en los paneles de los proveedores y en archivos
  locales ignorados por Git.

## Variables privadas de Render

El Blueprint solicita `DATABASE_URL`, `AGENDE_VAPID_PUBLIC_KEY` y
`AGENDE_VAPID_PRIVATE_KEY`. El resto de las opciones seguras se declara en
`render.yaml`.

## Automatización de recordatorios

La ruta `POST /sistema/recordatorios/despachar/` requiere un token Bearer.
La configuración activa vive en `agenda_automatizacion_host`; no se publica
el token ni se devuelve información personal en la respuesta.

La función programada de Neon debe ejecutarse cada minuto, validar el
encabezado propio de los triggers de Neon y llamar esa ruta con el token
privado. Así los recordatorios no dependen de que la computadora local esté
encendida.

El código desplegable está en `deployment/neon-function/index.mjs`. Sus dos
variables privadas son `RENDER_DISPATCH_URL` y `RENDER_DISPATCH_TOKEN`.
