# Política de Copias de Seguridad

## 1. Objetivo
Establecer los lineamientos para la creación, almacenamiento y verificación de copias de seguridad del sistema de punto de venta, con el fin de garantizar la disponibilidad y recuperación de los datos operacionales y transaccionales ante fallas de hardware, errores humanos o cualquier evento que comprometa la integridad del sistema.

Esta política define los procedimientos mínimos necesarios para que el negocio pueda continuar operando dentro de los tiempos de recuperación establecidos en caso de desastre.

## 2. Alcance
Esta política aplica al sistema ERP Odoo 17 Community alojado en el
servidor `mixtli` (bare metal on-premise, Debian 12) y cubre los
siguientes activos:
| Activo | Ruta en el host | Descripción | 
| --- | --- | --- |
| Base de datos | 'pg_dump' dentro del contenedor | Datos transaccionales de Odoo (inventario, ventas, configuración etc...) | 
| Filestore | 'infra/volumes/odoo/data' | Archivos binarios referenciados desde la BD (imágenes, PDFs, etc..)

Queda fuera del alcance de esta política: 
- La imagen de Odoo (disponible en Docker Hub: `odoo:17`)
- El código de configuración e infraestructura (gestionado en GitHub)
- Los módulos de Odoo Community (parte de la imagen oficial)

## 3. Definiciones
**RPO (Recovery Point Objective)**: Máxima perdida de datos aceptable medida en tiempo. Define hasta que punto en el pasado se puede restaurar el sistema tras un incidente.

**RTO (Recovery Time Objective)**: Tiempo máximo aceptable para restaurar el sistema a un estado operacional tras un incidente.

**Backup completo**: Copia integra de todos los activos definidos en el
alcance en un momento dado.

**Offsite**: Almacenamiento de copias de seguridad en una ubicación física o lógica distinta al servidor de producción.

**Regla 3-2-1**: Estrategia que establece mantener 3 copias de los datos, en 2 medios distintos, con 1 copia fuera del sitio.

**Retención**: Período durante el cual una copia de seguridad se conserva antes de ser eliminada.

**Verificación de integridad**: Proceso de confirmar que una copia de seguridad puede ser restaurada exitosamente.

## 4. Activos a proteger    
Los activos a proteger en esta política son: 
| Activo | Descripción | Importancia | Justificación | 
| --- | --- | --- | --- |
| BD PostgreeSQL |  Datos transaccionales y operacionales de Odoo: ventas, inventario, productos, configuración | Crítico |  Su perdida impide completamente la operación del PV y del ERP |
| Filestore de Odoo |  Archivos binarios referenciados desde la base de datos: imágenes de productos, PDFs de facturas, documentos adjuntos | Alto | Su pérdida no detiene el POS pero genera inconsistencias en reportes y documentos |


## 5. Clasificación de datos
| Dato | Clasificación | Justificación | 
| --- | --- | --- | 
| Historial de ventas y transacciones | Confidencial |  Contiene información financiera del negocio | 
| Catálogo de productos y precios | Interno |  Información operacional sensible para el negocio |
| Configuración del sistema | Interno | Acceso restringido a administradores |

## 6. Objetivos de recuperación
| Métrica | Valor | Justificación |
| --- | --- | --- |
| RPO | 24 Horas |  Una jornada de ventas es la pérdida máxima aceptable | 
| RTO | 1 hora | Tiempo necesario para seguir los pasos del runbook 'docs/runbooks/backup-restore.md' |

## 7. Procedimiento de backup
### Frecuencia y tipo
| Tipo | Frecuencia | Retención | Descripción | 
| --- | --- | --- | --- |
| Completo diario | Cada día a las 23:59 | 3 días | Backup de todos los activos | 
| Completo semanal | Cada domingo a las 23:59 | 4 semanas | Punto de restauración extendido | 

Todos los backups son de tipo completo — no se usan backups
incrementales dado el volumen de datos manejado y la simplicidad
de restauración que ofrece un backup completo.

### Procedimiento

El backup se ejecuta en dos pasos secuenciales:

**Paso 1 — Dump de PostgreeSQL**

Se detiene el contenedor de Odoo para evitar escrituras durante
el dump, garantizando consistencia entre la base de datos y el
filestore:

    docker compose stop odoo
    docker compose exec db pg_dump -U ${ODOO_DB_USER} odoo \
        | gzip > /opt/odoo-server/infra/volumes/backups/db_$(date +%F).sql.gz
    docker compose start odoo

**Paso 2 — Compresión del filestore**

    tar -czf \
        /opt/odoo-server/infra/volumes/backups/filestore_$(date +%F).tar.gz \
        /opt/odoo-server/infra/volumes/odoo/data/

### Destinos
| Destino | Tipo | Que se almacena |
| --- | --- | --- | 
| `infra/volumes/backups/` | Local en mixtli | Backups diarios y semanales | 
| Servidor secundario | on-premise | Copia offsite local | 
| Nube | Offsite remote | Copia offsite geográficamente separada | 

Los backups se transfieren automáticamente al servidor secundario y a la nube

**[TBD - Definir en implementación]**
- Automatización del procedimiento mediante script.
- Uso de cron para ejecutar el script automáticamente.
- Notificación al administrador en caso de errores, o inconsistencias.

## 8. Retención
| Backup | Tiempo de retención | 
| --- | --- |
| Diario | 3 días |
| Semanal | 4 semanas |

La combinación de ambos garantiza cobertura continua de hasta 4 semanas sin huecos importantes entre puntos de restauración disponibles.

Los backups expirados se eliminan automáticamente antes de generar la nueva copia como parte del script de backup.

## 9. Almacenamiento y destinos
Los backups se almacenan en tres destinos siguiendo la regla 3-2-1:
3 copias, en 2 medios distintos, con 1 copia fuera del sitio.

| Destino | Tipo | Ubicación | Qué se almacena |
|---|---|---|---|
| `infra/volumes/backups/` | Local | `mixtli` | Backups diarios y semanales |
| Servidor secundario | On-premise | Mismo local que `mixtli` | Backups diarios y semanales |
| Nube | Offsite | Ubicación geográficamente separada | Backups semanales |

### Consideraciones de seguridad

Los destinos local y on-premise comparten ubicación física. Ante un evento que afecte el local (incendio, robo, inundación), ambas copias podrían perderse simultáneamente. El destino en nube es la única copia con separación geográfica real y debe considerarse la copia de último recurso.

### Transferencia a destinos remotos

Los backups se transfieren automáticamente al servidor secundario y a la nube

**[TBD - Definir en implementación]**
- Protocolo de transferencia (rsync/scp/aws s3 cp)
- Credenciales y autenticación
- Timeouts y reintentos
- Validación de integridad post-transferencia

## 10. Verificación de integridad

### Nivel 1 — Verificación estructural (automática, tras cada backup)

Verifica que los archivos generados no están truncados ni corruptos:

    gunzip -t <archivo>.sql.gz
    tar -tzf <archivo>.tar.gz > /dev/null

### Nivel 2 — Verificación funcional y reconciliación (automática, semanal)

Script automatizado que:
1. Levanta un stack de prueba aislado en puerto alternativo
2. Restaura el backup más reciente
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
- Revisar que reportes e historial son coherentes

Se registra en `infra/logs/verify_backup.log`:

| Campo | Descripción |
|---|---|
| Fecha | Cuando se realizo |
| Backup utilizado | Archivo restaurado |
| Tiempo real | Vs RTO de 1 hora |
| Resultado | Exitoso / Fallido |
| Observaciones | Problemas o mejoras identificadas |

- La reconciliación automática detecta perdida de datos.
- La verificación manual detecta problemas lógicos que ningún script puede identificar por si solo.

## 11. Seguridad de los backups

### Cifrado

Los backups se cifran con AES-256-CBC antes de transferirse a
destinos remotos. Se usa `openssl` para cifrar y descifrar:

    # Cifrar
    openssl enc -aes-256-cbc -pbkdf2 \
        -in  <archivo>.gz \
        -out <archivo>.gz.enc \
        -pass env:BACKUP_PASSWORD

    # Descifrar al restaurar
    openssl enc -d -aes-256-cbc -pbkdf2 \
        -in  <archivo>.gz.enc \
        -out <archivo>.gz \
        -pass env:BACKUP_PASSWORD

La contraseña de cifrado se almacena en la variable de entorno
`BACKUP_PASSWORD` dentro del archivo `.env` del servidor `mixtli`.
Nunca debe almacenarse en el repositorio ni en los propios backups.

> Si se pierde la contraseña de cifrado, los backups cifrados son irrecuperables. Debe respaldarse en un lugar seguro independiente del servidor (gestor de contraseñas, sobre físico en lugar seguro).

### Backups locales

Los backups en `infra/volumes/backups/` heredan los permisos del
sistema de archivos de `mixtli`. Solo el usuario administrador
tiene acceso de lectura y escritura a ese directorio:

    chmod 700 infra/volumes/backups/

### Control de acceso

| Rol | Acceso | Descripción |
|---|---|---|
| Administrador | Lectura y escritura | Puede crear, restaurar y eliminar backups |

### Backups en nube

Solo se transfieren a la nube los archivos cifrados (`.enc`).
Nunca se sube un backup sin cifrar a destinos remotos.

## 12. Roles y responsabilidades

| Rol | Responsabilidad |
|---|---|
| Administrador del sistema | Mantenimiento del script de backup, verificación de integridad, ejecución del plan de recuperación, actualización de esta política |

### Procedimiento de escalación

En caso de que el administrador no esté disponible durante un
incidente:

1. Localizar las credenciales de acceso al servidor en el gestor de contraseñas
2. Seguir el runbook `docs/runbooks/backup-restore.md`
3. Las credenciales de cifrado de backups están documentadas en un lugar seguro independiente del servidor


## 13. Revisión de la política

Esta política se revisa y actualiza en los siguientes casos:

**Revisión periódica**
- Cada 6 meses para verificar que los objetivos siguen siendo adecuados para las necesidades del negocio.

**Revisión por evento**
- Cambio de infraestructura (nuevo servidor, proveedor de nube)
- Cambio en el volumen de datos que afecte los tiempos de backup
- Ejecución real del plan de recuperación
- Incorporación de nuevo personal con acceso al sistema

| Campo | Valor |
|---|---|
| Versión actual | 1.0 |
| Fecha de creación | 2026-06-27 |
| Última revisión | 2026-06-27 |
| Próxima revisión | 2026-12-27 |
| Autor | Elevel |