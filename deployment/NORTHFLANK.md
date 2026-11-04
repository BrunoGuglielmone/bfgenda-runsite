# BFGenda en Northflank Sandbox

Esta variante mantiene el servicio y el programador Web Push fuera de la PC.
Usa una única instancia Docker y un addon PostgreSQL persistente. El modo local
sigue usando SQLite; el contenedor selecciona PostgreSQL automáticamente cuando
recibe `POSTGRES_URI` o `DATABASE_URL`.

## Recursos gratuitos

- Un proyecto `bfgenda`.
- Un servicio combinado desde el repositorio público y su `Dockerfile`.
- Una instancia mínima, siempre única, con puerto público HTTP `8080`.
- Un addon PostgreSQL Sandbox interno, sin acceso público.
- Un Secret Group enlazado al servicio y al addon.

El servicio debe conservar una sola instancia porque el programador Web Push se
ejecuta dentro del proceso web. PostgreSQL y el bloqueo de cada entrega reducen
el riesgo durante un despliegue, pero no se habilita escalado horizontal.

## Variables

Importar las opciones de `northflank.env.example`, reemplazando el dominio de
ejemplo por el DNS exacto asignado al servicio. El Secret Group enlaza
`POSTGRES_URI` del addon y almacena, sin publicarlos en Git:

- `AGENDE_SECRET_KEY`;
- `AGENDE_VAPID_PUBLIC_KEY`;
- `AGENDE_VAPID_PRIVATE_KEY`;
- `AGENDE_VAPID_SUBJECT`.

El servicio aplica las migraciones antes de iniciar Waitress. El health check es
`/sistema/estado/` y debe devolver HTTP 200.

## Migración de datos

La base real permanece local hasta obtener confirmación explícita para transferir
usuarios, tareas, eventos, categorías y preferencias. Con PostgreSQL ya activo:

1. crear y verificar una exportación lógica desde SQLite;
2. importarla mediante un job de ejecución única conectado al mismo Secret Group;
3. comprobar cantidades por modelo y acceso con la cuenta existente;
4. eliminar el artefacto temporal del job;
5. registrar nuevamente el teléfono para Web Push, porque cambia el origen web y
   la pareja VAPID.

Las copias SQLite integradas se deshabilitan en PostgreSQL. La persistencia y las
copias pasan a depender del addon administrado; las exportaciones JSON y CSV por
usuario siguen disponibles desde Configuración.
