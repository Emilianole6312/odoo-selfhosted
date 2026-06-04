# Volume Layout

Descripción de la estructura de directorios del stack en el host (`mixtli`). Los directorios bajo `infra/volumes/` son bind mounts — Docker no los gestiona, viven directamente en el sistema de archivos del host.

## Estructura

```
infra/
├── docker-compose.yml        → definición del stack
├── .env                      → credenciales reales (nunca en git)
├── .env.example              → plantilla de variables de entorno
├── nginx/
│   └── odoo.conf             → configuración del reverse proxy
└── volumes/
    ├── postgres/             → datos de PostgreSQL
    ├── odoo/
    │   ├── data/             → filestore de Odoo
    │   └── addons/           → módulos extra
```

## Descripción de cada directorio

### `volumes/postgres/`
Datos binarios de PostgreSQL. Bind mount hacia `/var/lib/postgresql/data`
dentro del contenedor `db`.

> No respaldar copiando estos archivos directamente. Usar `pg_dump`
> para obtener un backup consistente. Ver runbook de backup.

### `volumes/odoo/data/`
Filestore de Odoo. Contiene archivos binarios referenciados desde la base
de datos: imágenes de productos, documentos adjuntos, PDFs generados, sesiones.

Bind mount hacia `/var/lib/odoo` dentro del contenedor `odoo`.

> Debe respaldarse junto con el dump de PostgreSQL. Ambos deben
> corresponder al mismo punto en el tiempo.

### `volumes/odoo/addons/`
Módulos extra de Odoo. En esta instalación se mantiene vacío — todos los
módulos en uso son parte de Odoo 17 Community.

Bind mount hacia `/mnt/extra-addons` dentro del contenedor `odoo`.

### `nginx/odoo.conf`
Configuración de Nginx como reverse proxy hacia Odoo. Montado como archivo individual hacia `/etc/nginx/conf.d/default.conf` dentro del contenedor `nginx`.

## Permisos requeridos

El directorio `volumes/odoo/` debe ser propiedad del UID 101, que corresponde al usuario `odoo` dentro del contenedor:

```bash
sudo chown -R 101:101 ./infra/volumes/odoo/
```

El directorio `volumes/postgres/` es inicializado y gestionado por PostgreSQL al primer arranque. No requiere ajuste manual de permisos.

## Archivos `.gitkeep`

Los directorios de volúmenes se mantienen en el repositorio mediante archivos `.gitkeep` para preservar la estructura sin incluir datos. Estos archivos son ignorados por Odoo y PostgreSQL en tiempo de ejecución.

## Pendiente

- `volumes/backups/` — directorio para backups locales antes de transferir a almacenamiento externo. Por definir junto con la estrategia de backup.
