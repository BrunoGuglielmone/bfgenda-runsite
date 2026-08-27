# BFGenda en Runsite Free

Este despliegue conserva SQLite, sirve la PWA por HTTPS y ejecuta Web Push
desde la única instancia del servicio. No necesita tarjeta ni una base de
datos externa: usa el almacenamiento S3 incluido en Runsite Free.

## Servicio

- Tipo: Web Service desde Git.
- Plan: Free, una única instancia.
- Puerto: `8080`.
- Build command: se toma del `Dockerfile`.
- Start command: se toma del `Dockerfile`.
- Health check: `/sistema/estado/`.
- Disco persistente pago: desactivado.
- Almacenamiento efímero: `/data`.
- Persistencia real: bucket S3 privado de Runsite mediante Litestream.

Runsite vacía `/data` al reiniciar el contenedor. Antes de iniciar Django,
Litestream restaura la última versión de SQLite desde S3; mientras la
aplicación está activa replica cada cambio y hace una sincronización final al
apagarse correctamente.

La replicación es asíncrona: un corte brusco puede perder cambios todavía no
enviados a S3. Las copias descargables y los registros de `/data` también son
efímeros; conviene descargar periódicamente una copia independiente. No usar
datos reales hasta comprobar una restauración después de reiniciar el host.

## Variables privadas

Copiar las claves de `deployment/runsite.env.example` a Environment y guardar
como secretas al menos:

- `AGENDE_SECRET_KEY`;
- `AGENDE_VAPID_PRIVATE_KEY`;
- `LITESTREAM_ACCESS_KEY_ID`;
- `LITESTREAM_SECRET_ACCESS_KEY`.

El bucket debe ser privado. La clave S3 definitiva necesita lectura,
escritura y borrado de objetos para limpiar réplicas vencidas, y se limita
exclusivamente al bucket de BFGenda, sin administración global. Si el panel
exige una clave inicial para crear el bucket, usar una temporal y revocarla
después. Ningún secreto se publica en Git.

La redirección HTTPS queda desactivada en Django porque Runsite finaliza TLS
en su proxy. Las cookies seguras siguen activas.

## Inicio del contenedor

`scripts/iniciar_runsite_con_litestream.py` crea los directorios efímeros y
lanza Litestream. Litestream restaura SQLite si falta, supervisa el proceso y
ejecuta `scripts/iniciar_runsite.py`; éste aplica las migraciones e inicia
Waitress en `0.0.0.0:8080`. El programador Web Push corre cada minuto dentro
del mismo proceso y garantiza una copia diaria cuando
`AGENDE_PUSH_SCHEDULER_ENABLED=1`.

Esta modalidad requiere mantener una sola instancia. Si en el futuro se
escala horizontalmente, el programador debe moverse a un worker o cron único.

## Claves Web Push

La pareja VAPID se genera una sola vez. La clave pública se guarda en
`AGENDE_VAPID_PUBLIC_KEY` y la clave privada DER en base64url se guarda como
secret en `AGENDE_VAPID_PRIVATE_KEY`. Al vivir en Environment no desaparece
cuando Runsite reemplaza el contenedor.

## Migración de la base real

El primer despliegue se valida con una base nueva. Después, con el servicio
detenido para evitar dos escritores:

1. crear una copia local desde BFGenda;
2. verificar la integridad de la copia;
3. cargarla como snapshot inicial de Litestream en el bucket privado;
4. iniciar la única instancia;
5. comprobar que el arranque la restaura y aplica migraciones.

La transferencia de la base contiene información personal y se realiza sólo
después de una confirmación explícita del propietario.

## Validación del corte

1. comprobar `/sistema/estado/` y el login por HTTPS;
2. crear una tarea y un evento de prueba;
3. instalar la PWA en Android y activar las notificaciones;
4. enviar la prueba Push con la aplicación cerrada;
5. reiniciar el servicio y confirmar que SQLite conserva los datos;
6. crear y descargar una copia de seguridad;
7. desinstalar Tailscale únicamente después de completar todo lo anterior.

El plan gratuito puede detener la instancia por inactividad. La siguiente
visita la reactiva y Litestream recupera SQLite desde S3; mientras la instancia
está detenida no puede despachar recordatorios.
