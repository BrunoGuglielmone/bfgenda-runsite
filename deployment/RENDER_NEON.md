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

## Supervisión

Cada llamada autorizada actualiza `agenda_automatizacion_host` con:

- fecha de la última ejecución;
- fecha del último éxito;
- resultado y error controlado;
- cantidad de envíos, fallos y omisiones del último ciclo.

El estado se muestra en Configuración, debajo de los controles de
notificaciones. Un valor reciente con estado `correcto` confirma que la Neon
Function y Render se comunican.

## Copias de seguridad

Producción no utiliza las copias de archivo SQLite. La estrategia actual es:

1. recuperación inmediata de Neon dentro de la ventana del plan;
2. snapshot manual antes de migraciones o cambios importantes;
3. descarga periódica del `Respaldo restaurable` desde Configuración.

La programación nativa de snapshots requiere un plan compatible. En el plan
gratuito se crea un snapshot manual antes de cada cierre relevante. El
respaldo lógico incluye la cuenta, categorías, tareas, eventos y preferencias,
pero excluye sesiones, endpoints Push y tokens de infraestructura.

Para una recuperación lógica, crear primero una base vacía, aplicar las
migraciones y recién después ejecutar:

```powershell
python manage.py loaddata bfgenda-respaldo-logico-AAAAMMDD-HHMMSS.json
```

No cargar la fixture directamente sobre una base poblada porque conserva las
claves primarias originales. Para incidentes recientes, preferir Restaurar en
Neon y revisar el estado antes de finalizar el reemplazo.

## Operación estable

Antes de publicar cambios con migraciones:

1. ejecutar pruebas específicas y la suite completa;
2. crear un snapshot manual de Neon;
3. publicar el commit limpio en `bfgenda-runsite`;
4. desplegar ese commit en Render;
5. verificar `/sistema/estado/` y la tarjeta de supervisión.
