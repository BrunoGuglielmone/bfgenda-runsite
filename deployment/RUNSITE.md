# BFGenda en Runsite Free

Este despliegue conserva SQLite, sirve la PWA por HTTPS y ejecuta Web Push
desde la única instancia del servicio. No necesita tarjeta ni una base de
datos externa.

## Servicio

- Tipo: Web Service desde Git.
- Plan: Free, una única instancia.
- Puerto: `8080`.
- Build command: se toma del `Dockerfile`.
- Start command: se toma del `Dockerfile`.
- Health check: `/sistema/estado/`.
- Disco persistente: 1 GB montado en `/data`.

El disco es obligatorio. Sin él, SQLite y las copias se perderían al
reiniciar o volver a desplegar el contenedor.

## Variables privadas

Copiar las claves de `deployment/runsite.env.example` a Environment, cambiar
`DOMINIO` por el subdominio asignado y guardar como secretas al menos:

- `AGENDE_SECRET_KEY`.

La clave VAPID privada se conserva como archivo dentro del disco persistente,
fuera del repositorio y del sistema de construcción.

La redirección HTTPS queda desactivada en Django porque Runsite finaliza TLS
en su proxy. Las cookies seguras siguen activas.

## Inicio del contenedor

`scripts/iniciar_runsite.py` crea los directorios persistentes, aplica las
migraciones y luego inicia Waitress en `0.0.0.0:8080`. El programador Web Push
corre cada minuto dentro del mismo proceso y garantiza una copia diaria cuando
`AGENDE_PUSH_SCHEDULER_ENABLED=1`.

Esta modalidad requiere mantener una sola instancia. Si en el futuro se
escala horizontalmente, el programador debe moverse a un worker o cron único.

## Claves Web Push

Después del primer arranque, abrir Shell en Runsite y generar la pareja dentro
del disco persistente:

```bash
python manage.py generar_claves_vapid /data/bfgenda/secrets/vapid-private.pem
```

Copiar la línea `AGENDE_VAPID_PUBLIC_KEY` resultante a Environment y aplicar
`AGENDE_PUSH_SCHEDULER_ENABLED=1` junto con `Save & Deploy`. La clave privada
nunca sale del disco persistente.

## Migración de la base real

El primer despliegue se valida con una base nueva. Después:

1. crear una copia local desde BFGenda;
2. abrir Shell en Runsite;
3. colocar la base validada en `/data/bfgenda/db.sqlite3`;
4. reiniciar la única instancia;
5. ejecutar `python manage.py migrate` si el arranque no lo hizo todavía.

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

El plan gratuito duerme después de 14 días completos sin tráfico. La siguiente
visita lo reactiva y el disco permanece intacto; mientras esté dormido no puede
despachar recordatorios.
