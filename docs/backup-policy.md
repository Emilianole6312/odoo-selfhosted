# Política de Copias de Seguridad

## 1. Objetivo
Establecer los lineamientos para la creación, almacenamiento y verificación de copias de seguridad del sistema de punto de venta, con el fin de garantizar la disponibilidad y recuperación de los datos operacionales y transaccionales ante fallas de hardware, errores humanos o cualquier evento que comprometa la integridad del sistema.

Esta política define los procedimientos mínimos necesarios para que el negocio pueda continuar operando dentro de los tiempos de recuperación establecidos en caso de desastre.

## 2. Alcance
Esta política aplica al sistema ERP Odoo 17 Community alojado en el
servidor `mixtli` (bare metal on-premise, Debian 12) y cubre los
siguientes activos:

| Activo | Ubicación | Descripción |
| --- | --- | --- |
| Base de datos | `pg_dump` dentro del contenedor `db` | Datos transaccionales de Odoo (inventario, ventas, configuración, etc.) |
| Filestore | `/var/lib/odoo/filestore` dentro del contenedor `odoo` (bind mount en `infra/volumes/odoo/data`) | Archivos binarios referenciados desde la BD (imágenes, PDFs, etc.) |

Queda fuera del alcance de esta política:
- La imagen de Odoo (disponible en Docker Hub: `odoo:17`)
- El código de configuración e infraestructura (gestionado en GitHub)
- Los módulos de Odoo Community (parte de la imagen oficial)

## 3. Definiciones
**RPO (Recovery Point Objective)**: Máxima perdida de datos aceptable medida en tiempo. Define hasta que punto en el pasado se puede restaurar el sistema tras un incidente.

**RTO (Recovery Time Objective)**: Tiempo máximo aceptable para restaurar el sistema a un estado operacional tras un incidente.

**Backup completo**: Copia íntegra de todos los activos definidos en el alcance en un momento dado.

**Offsite**: Almacenamiento de copias de seguridad en una ubicación física o lógica distinta al servidor de producción.

**Regla 3-2-1**: Estrategia que establece mantener 3 copias de los datos, en 2 medios distintos, con 1 copia fuera del sitio.

**Retención**: Criterio que determina cuántas copias de seguridad se conservan antes de eliminar las más antiguas. En esta política se define por **cantidad** de backups, no por antigüedad.

**Verificación de integridad**: Proceso de confirmar que una copia de seguridad puede ser restaurada exitosamente.

## 4. Activos a proteger
Los activos a proteger en esta política son:

| Activo | Descripción | Importancia | Justificación |
| --- | --- | --- | --- |
| BD PostgreSQL | Datos transaccionales y operacionales de Odoo: ventas, inventario, productos, configuración | Crítico | Su pérdida impide completamente la operación del PV y del ERP |
| Filestore de Odoo | Archivos binarios referenciados desde la base de datos: imágenes de productos, PDFs de facturas, documentos adjuntos | Alto | Su pérdida no detiene el POS pero genera inconsistencias en reportes y documentos |

## 5. Clasificación de datos
| Dato | Clasificación | Justificación |
| --- | --- | --- |
| Historial de ventas y transacciones | Confidencial | Contiene información financiera del negocio |
| Catálogo de productos y precios | Interno | Información operacional sensible para el negocio |
| Configuración del sistema | Interno | Acceso restringido a administradores |

> **Nota de riesgo aceptado:** el historial de ventas está clasificado como Confidencial y los backups se almacenan **sin cifrado a nivel de archivo** (ver sección 11, "Cifrado (diferido)", y ADR-006). Esta decisión se compensa con controles de acceso sobre el bucket y el token de la nube, y se reevalúa según los criterios de la sección 11.

## 6. Objetivos de recuperación
| Métrica | Valor | Justificación |
| --- | --- | --- |
| RPO | 24 horas | Una jornada de ventas es la pérdida máxima aceptable |
x| RTO | 1 hora | Tiempo necesario para seguir los pasos del runbook `docs/runbooks/backup-restore.md` |

## 7. Procedimiento de backup

### Frecuencia y tipo
| Tipo | Frecuencia | Retención | Descripción |
| --- | --- | --- | --- |
| Completo diario | Cada día a las 23:59 | Últimos 3 backups | Backup de todos los activos |
| Completo semanal | Cada domingo a las 23:59 | Últimos 4 backups | Punto de restauración extendido |

Todos los backups son de tipo completo: no se usan backups incrementales dado el volumen de datos manejado y la simplicidad de restauración que ofrece un backup completo.

### Procedimiento

Un único script (`backup.sh`) genera el backup en pasos secuenciales.
**No se detiene el contenedor de Odoo** durante el proceso.

**Paso 1 — Carpeta del backup**

Se crea una carpeta con nombre `backup_AAAA-MM-DD_HH-MM-SS` dentro de
`$BACKUPS_DIR`. Esta carpeta es temporal y se identifica en el script como `$BACKUP_DIR`.

**Paso 2 — Dump de PostgreSQL**

El dump se escribe directamente a archivo, sin pipe, para que un fallo de
`pg_dump` aborte el script (`set -euo pipefail`):

```bash
docker compose exec -T db pg_dump -U "$BACKUP_DB_USER" "$BACKUP_DB_NAME" > "$BACKUP_DIR/db.sql"
```

**Paso 3 — Copia del filestore**

Se copia desde el contenedor con `docker compose cp`, lo que evita problemas de
permisos con el usuario interno de Odoo (UID 101):

```bash
docker compose cp odoo:/var/lib/odoo/filestore "$BACKUP_DIR/filestore"
```

**Paso 4 — Compresión y verificación**

La carpeta completa se comprime una sola vez, se verifica y se genera su checksum:

```bash
tar -C "$BACKUPS_DIR" -czf "$ARCHIVE" "$BACKUP_NAME"
tar -tzf "$ARCHIVE" > /dev/null
sha256sum "$BACKUP_NAME.tar.gz" > "$BACKUP_NAME.tar.gz.sha256"
```

Después se elimina la carpeta sin comprimir.

**Paso 5 — Almacenamiento local y subida a la nube**

El archivo se guarda en `daily/`. Si la ejecución inició en domingo, también
se registra como backup semanal en `weekly/` (enlace duro en local, subida
adicional en la nube). El día de la semana se determina **al inicio** de la
ejecución, para que un script que termine pasada la medianoche no cambie de tipo.

**Paso 6 — Retención**

Solo si todos los pasos anteriores (incluida la subida) terminaron con éxito,
se eliminan los backups que excedan la cantidad a conservar (ver sección 8).

#### Consistencia sin detener Odoo

`pg_dump` obtiene un snapshot consistente de la base de datos sin detenerla. El filestore se copia después del dump, por lo que puede contener archivos creados entre ambos pasos (extras inofensivos). La inconsistencia posible es inversa: que la limpieza periódica de adjuntos huérfanos de Odoo elimine un archivo entre el dump y la copia, dejando una referencia en la BD sin archivo. Se acepta este riesgo residual por su bajo impacto y porque el backup corre a las 23:59, en horario sin actividad. El nivel 3 de verificación (sección 10) detecta este tipo de problema.

### Destinos
| Destino | Tipo | Qué se almacena |
| --- | --- | --- |
| `$BACKUPS_DIR` (`daily/`, `weekly/`) | Local en `mixtli` | Backups diarios y semanales |
| Cloudflare R2 (`daily/`, `weekly/`) | Offsite remoto | Backups diarios y semanales |

Los backups se transfieren automáticamente a la nube al terminar cada ejecución.

### Automatización

Los backups se ejecutan automáticamente mediante cron en `mixtli`. Un único registro cubre ambos tipos, ya que el backup semanal se resuelve dentro del
script:

```bash
# Editar
crontab -e

# Agregar la línea
# Backup diario (los domingos también genera el semanal)
59 23 * * * /opt/odoo-server/infra/scripts/backup.sh >> /opt/odoo-server/infra/logs/backup.cron.log 2>&1
```

- Ejecución: todos los días a las 23:59
- Script: `/opt/odoo-server/infra/scripts/backup.sh`
- Log del script: `LOG_FILE` definido en `backup.conf` (`infra/logs/backup.log`)
- Log de cron: `/opt/odoo-server/infra/logs/backup.cron.log` (stdout y stderr redirigidos con `2>&1`)

**Pendiente:** definir un mecanismo de aviso ante fallos (por ejemplo `MAILTO` de cron o un ping a un servicio de monitoreo al terminar con éxito). Sin esto, un backup que falle no avisa y los backups existentes envejecen sin que nadie lo note.

## 8. Retención
| Backup | Cantidad conservada | Variable en `backup.conf` |
| --- | --- | --- |
| Diario | 3 backups | `RETENTION_DIARIO` |
| Semanal | 4 backups | `RETENTION_SEMANAL` |

Las variables representan **cantidad de backups**, no días. Debe ser un entero mayor o igual a 1; el script lo valida antes de eliminar nada.

La retención se aplica tanto en local como en la nube, siempre **después** de que el backup nuevo se generó, verificó y subió con éxito. Si una ejecución falla, no se elimina ningún backup anterior: nunca se queda por debajo de la cantidad conservada por culpa de un fallo.

La combinación de ambos garantiza cobertura de hasta 4 semanas sin huecos importantes entre puntos de restauración, siempre que las ejecuciones terminen con éxito.

## 9. Almacenamiento y destinos

Los backups se almacenan en dos destinos:

| Destino | Tipo | Ubicación | Qué se almacena |
| --- | --- | --- | --- |
| `$BACKUPS_DIR` | Local | `mixtli` | Backups diarios y semanales |
| Cloudflare R2 | Offsite | Nube, ubicación geográficamente separada | Backups diarios y semanales |

**Relación con la regla 3-2-1:** esta política cumple parcialmente la regla. Se mantienen 2 copias (local y nube) en 2 medios distintos (disco local y almacenamiento de objetos en la nube), con 1 copia fuera del sitio. No se cumple la tercera copia: por decisión consciente se descartó, por ahora, un servidor secundario on-premise.

### Consideraciones de seguridad

- La copia en la nube es la única con separación geográfica real y debe considerarse la copia de último recurso.
- Si `mixtli` se pierde (falla de disco, robo, incendio), la nube es la única copia disponible, y depende de que la cuenta de Cloudflare siga accesible.
- Con solo 2 copias, un fallo silencioso en la subida deja un único backup válido. Por eso la subida fallida aborta el script con error y se define un aviso ante fallos (ver sección 7, "Automatización").

### Transferencia a la nube

- **Herramienta:** `rclone` (disponible en apt) con un remote configurado para Cloudflare R2.
- **Estructura en el bucket:** prefijos `daily/` y `weekly/`; cada backup sube su `.tar.gz` y su `.sha256`.
- **Credenciales:** token de API de R2 con permiso de lectura y escritura limitado al bucket de backups. No se usa un token de administración en el servidor.
- **Almacenamiento de credenciales:** fuera del repositorio (`.env` ignorado por git o configuración de `rclone` con permisos restringidos).
- **Reintentos y timeouts:** usar las opciones de reintento de `rclone`; los valores concretos se ajustan en la implementación.
- **Validación post-transferencia:** `rclone` compara tamaño y hash al subir cuando el backend lo soporta; el `.sha256` permite verificar manualmente cualquier backup descargado.
- **Retención en la nube:** aplicada por el script (por cantidad, tras subida exitosa) y no mediante reglas de ciclo de vida de R2, que solo operan por antigüedad y podrían borrar todos los backups si las subidas dejaran de funcionar.

## 10. Verificación de integridad

### Nivel 1 — Verificación estructural (automática, tras cada backup)

Verifica que el archivo generado no está truncado ni corrupto y registra su checksum:

    tar -tzf <backup>.tar.gz > /dev/null
    sha256sum <backup>.tar.gz > <backup>.tar.gz.sha256

### Nivel 2 — Verificación funcional y reconciliación (automática, semanal)

Script automatizado que:
1. Levanta un stack de prueba aislado en puerto alternativo
2. Extrae y restaura el backup más reciente (`db.sql` y `filestore/`)
3. Verifica que Odoo responde HTTP 200
4. Reconcilia métricas contra el snapshot capturado durante el backup:
   - Número de ventas (`pos_order`)
   - Número de productos (`product_product`)
   - Número de facturas (`account_move`)
   - Fecha de la última venta registrada
5. Notifica si hay inconsistencias entre el backup y el snapshot
6. Registra el tiempo de restauración vs RTO definido (1 hora)
7. Apaga y limpia el stack de prueba
8. Escribe resultado en `infra/logs/verify_backup.log`

### Nivel 3 — Verificación manual (mensual)

Revisión humana que complementa la automatización:
- Navegar el sistema restaurado y confirmar que los datos tienen sentido
- Ejecutar una venta de prueba en el POS restaurado
- Revisar que reportes e historial son coherentes, incluidas imágenes y adjuntos (el backup se genera sin detener Odoo, ver sección 7)

Se registra en `infra/logs/verify_backup.log`:

| Campo | Descripción |
|---|---|
| Fecha | Cuándo se realizó |
| Backup utilizado | Archivo restaurado |
| Tiempo real | Vs RTO de 1 hora |
| Resultado | Exitoso / Fallido |
| Observaciones | Problemas o mejoras identificadas |

- La reconciliación automática detecta pérdida de datos.
- La verificación manual detecta problemas lógicos que ningún script puede identificar por sí solo.

## 11. Seguridad de los backups

### Cifrado (no implementado)

**Estado:** no implementado. Los backups no se cifran a nivel de archivo, ni en local ni en la nube. Decisión registrada en [ADR-005](./adr/ADR-005.md).

**Motivo:** el proyecto es de escala pequeña y el cifrado agrega un riesgo operativo propio (si se pierde la llave o contraseña, los backups de la nube quedan inservibles) y complejidad al flujo de restauración, cuyo RTO es de 1 hora.

**Controles compensatorios vigentes:**
- Bucket de R2 privado, sin acceso ni dominio público.
- Token de API limitado al bucket de backups.
- Token fuera del repositorio.
- Cloudflare cifra en reposo los datos de R2 con llaves administradas por Cloudflare. Esto no protege ante el compromiso de la cuenta o del token.

**Criterios para reactivar el cifrado:**
- Se manejen datos sensibles de terceros (clientes, empleados).
- Cambie el modelo de acceso a la cuenta de Cloudflare o al bucket.
- Cualquier incidente de seguridad relacionado con credenciales.

**Referencia de implementación (para cuando se reactive):**

Se cifraría el `.tar.gz` completo antes de subirlo a la nube. El diseño original contemplaba
`openssl` con AES-256-CBC:

    # Cifrar
    openssl enc -aes-256-cbc -pbkdf2 \
        -in  <backup>.tar.gz \
        -out <backup>.tar.gz.enc \
        -pass env:BACKUP_PASSWORD

    # Descifrar al restaurar
    openssl enc -d -aes-256-cbc -pbkdf2 \
        -in  <backup>.tar.gz.enc \
        -out <backup>.tar.gz \
        -pass env:BACKUP_PASSWORD

La contraseña se almacenaría en la variable de entorno `BACKUP_PASSWORD` dentro del archivo `.env` del servidor `mixtli`, nunca en el repositorio ni en los propios backups.

> Si se pierde la contraseña o llave de cifrado, los backups cifrados son irrecuperables. Debe respaldarse en un lugar seguro independiente del servidor (gestor de contraseñas, sobre físico en lugar seguro). Antes de depender del cifrado, probar al menos una restauración completa (descifrar y extraer).

> Nota: `openssl enc` con AES-CBC cifra pero no autentica el contenido. Al reactivar el cifrado se recomienda evaluar `age` (disponible en apt), que usa llave pública para cifrar, de modo que el servidor no necesita guardar la llave de descifrado.

### Backups locales

Los backups en `$BACKUPS_DIR` heredan los permisos del sistema de archivos de `mixtli`. Solo el usuario administrador tiene acceso de lectura y escritura a ese directorio:

    chmod 700 "$BACKUPS_DIR"

### Control de acceso

| Rol | Acceso | Descripción |
|---|---|---|
| Administrador | Lectura y escritura | Puede crear, restaurar y eliminar backups |
| Token de API de R2 (usado por `mixtli`) | Lectura y escritura sobre el bucket de backups | Sube backups y aplica la retención en la nube; guardado fuera del repositorio |

### Backups en nube

- Los archivos se suben sin cifrado a nivel de archivo (ver "Cifrado (no implementado)").
- El bucket debe permanecer privado, sin acceso público ni dominio público.
- El token de R2 con el que `mixtli` sube backups debe estar limitado a ese bucket. El token de administración (necesario para cambiar la configuración del bucket) no se almacena en el servidor.

## 12. Roles y responsabilidades

| Rol | Responsabilidad |
|---|---|
| Administrador del sistema | Mantenimiento del script de backup, verificación de integridad, ejecución del plan de recuperación, actualización de esta política |

### Procedimiento de escalación

En caso de que el administrador no esté disponible durante un incidente:

1. Localizar las credenciales de acceso al servidor en el gestor de contraseñas
2. Seguir el runbook `docs/runbooks/backup-restore.md`
3. Si hace falta restaurar desde la nube, localizar las credenciales de la cuenta de Cloudflare y del bucket de backups en el gestor de contraseñas
4. Restaurar preferentemente desde la copia local; usar la nube como copia de último recurso

## 13. Revisión de la política

Esta política se revisa y actualiza en los siguientes casos:

**Revisión periódica**
- Cada 6 meses para verificar que los objetivos siguen siendo adecuados para las necesidades del negocio.

**Revisión por evento**
- Cambio de infraestructura (nuevo servidor, proveedor de nube)
- Cambio en el volumen de datos que afecte los tiempos de backup
- Ejecución real del plan de recuperación
- Incorporación de nuevo personal con acceso al sistema
- Cumplimiento de alguno de los criterios para reactivar el cifrado (sección 11)
- Incorporación de una tercera copia (por ejemplo, un servidor secundario)

| Campo | Valor |
|---|---|
| Versión actual | 1.1 |
| Fecha de creación | 2026-06-27 |
| Última revisión | 2026-11-20 |
| Próxima revisión | 2027-05-20 |
| Autor | Elevel |