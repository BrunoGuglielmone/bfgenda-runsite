# BFGenda

Aplicación web privada para organizar tareas, eventos y categorías personales desde computadora y celular.

## Entorno

- Python 3.13.14
- Django 5.2.16
- SQLite en desarrollo local
- PostgreSQL administrado por Neon en producción
- Waitress 3.0.2
- WhiteNoise 6.12.0
- Web Push con VAPID
- Render como host público
- HTML, CSS y JavaScript sin frameworks externos
- Zona horaria `America/Montevideo`

## Arquitectura

```text
agenda/
├── forms.py
├── models.py
├── services/                     # Consultas y reglas reutilizables
├── utils/                        # Utilidades compartidas
├── views/                        # Vistas separadas por responsabilidad
├── templates/agenda/
└── static/agenda/
config/
├── env.py                        # Lectura mínima del archivo .env
├── settings.py
└── wsgi.py
scripts/
├── servidor_agende.py            # Servidor Waitress
├── iniciar_agende.ps1            # Inicio en segundo plano y navegador
├── detener_agende.ps1            # Detención mediante PID
├── abrir_registros.ps1
└── crear_accesos_directos.ps1
```

## Aplicación publicada

La instancia principal está disponible en:

```text
https://bfgenda.onrender.com
```

Render ejecuta Django y Neon conserva los datos aunque la computadora local
esté apagada. Una Neon Function llama cada minuto al despachador privado de
recordatorios.

## Inicio local

Después de instalar esta actualización, utiliza el acceso directo **BFGenda** del Escritorio.

El acceso directo:

1. comprueba si el servidor ya está funcionando;
2. inicia Waitress en segundo plano cuando sea necesario;
3. espera a que BFGenda responda;
4. abre el navegador automáticamente.

Para detenerla utiliza **Detener BFGenda**.

## Direcciones

Desde la PC:

```text
http://127.0.0.1:8000/
```

El acceso local se conserva para desarrollo y recuperación. Ya no se utiliza
Tailscale ni una dirección privada de la computadora para la aplicación de
producción.

## Configuración privada

El archivo `.env` contiene la clave secreta y las opciones propias del equipo. Está excluido de Git.

```text
AGENDE_SECRET_KEY=...
AGENDE_DEBUG=0
AGENDE_ALLOWED_HOSTS=127.0.0.1,localhost,192.168.1.19
AGENDE_HOST=0.0.0.0
AGENDE_PORT=8000
AGENDE_THREADS=4
AGENDE_BROWSER_URL=http://127.0.0.1:8000/
```

## Registros

Los archivos se guardan en:

```text
logs/bfgenda.log
logs/servidor.log
logs/inicio_error.log
```

Los registros rotan automáticamente para evitar un crecimiento ilimitado. El acceso directo **Registros de BFGenda** abre esa carpeta.

## Comandos de mantenimiento

```powershell
Set-Location "C:\Users\Bruno Guglielmone\Desktop\Proyecto Agenda"

.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test agenda
.\.venv\Scripts\python.exe manage.py collectstatic --noinput
```

El comando `runserver` puede seguir usándose para depuración puntual, pero el inicio habitual se realiza con Waitress.

## Copias y recuperación

- Neon permite recuperación inmediata dentro de la ventana incluida por el
  plan y snapshots manuales antes de cambios importantes.
- Configuración ofrece un respaldo lógico descargable y restaurable en una
  base vacía, compatible con SQLite y PostgreSQL.
- Las copias `.sqlite3` integradas siguen disponibles únicamente en el modo
  local con SQLite.

## Alojamiento administrado

La arquitectura activa, las tareas de recordatorios y la recuperación están
documentadas en `deployment/RENDER_NEON.md`. Los documentos de Runsite y
Northflank se conservan solamente como historial de alternativas evaluadas.

## Compatibilidad interna

Para evitar romper instalaciones anteriores, BFGenda conserva algunos
identificadores t?cnicos hist?ricos:

- la aplicaci?n Django y sus tablas contin?an usando `agenda`;
- las variables privadas conservan el prefijo `AGENDE_*`;
- los scripts mantienen nombres como `iniciar_agende.ps1`;
- el archivo interno de proceso contin?a siendo `runtime/agende.pid`.

Estos nombres no afectan la identidad visible de BFGenda y no deben
renombrarse manualmente.
