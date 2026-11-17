# Odoo Self-Hosted Infrastructure

Implementación completa de Odoo 17 Community en servidor propio
para la gestión de una tienda minorista, incluyendo migración de
datos desde un sistema Punto de Venta anterior y estrategia de operaciones.

## Objetivo

Documentar el proceso completo de adoptar Odoo como sistema central
de gestión, desde la infraestructura hasta la continuidad del negocio,
como proyecto de referencia para prácticas de SRE/DevOps.

## Alcance

- **Infraestructura**: Despliegue con Docker Compose en servidor Debian
- **Migración**: Scripts Python para transformar datos del POS anterior a Odoo
- **Monitoreo**: Stack Telegraf + InfluxDB + Grafana
- **Operaciones**: Políticas de backup, RTO/RPO definidos, runbooks y BCP

## Stack

| Componente     | Tecnología              |
|----------------|-------------------------|
| Aplicación     | Odoo 17 Community       |
| Base de datos  | PostgreSQL 16           |
| Contenedores   | Docker / Docker Compose |
| Monitoreo      | Telegraf + InfluxDB + Grafana |
| Servidor       | Bare metal on-premise (mixtli), Debian 12, hardware repropuesto |
| IaC            |                          |
| CI             | GitHub Actions          |

## Migración

Script de transformación del catálogo del POS anteriori (Tiendatek) a formato Odoo 17.

### Uso

Para ejecutar el script de migración es necesario tener pandas instalado (`sudo apt install python3-pandas`).

```bash
python3 ./migration/inventario_odoo.py inventario.csv
```

El script recibe un único CSV con las columnas `Codigo barras`, `Nombre`, `Presentacion`, `Precio` y `Costo` (las existencias se ignoran) y lo procesa en este orden:

1. **Códigos de barras:** los UPC-A de 12 dígitos se normalizan a EAN-13 y se valida el dígito verificador de los EAN-13 y EAN-8. Los códigos internos de 4 dígitos se aceptan tal cual. Los dígitos verificadores **no se corrigen**: los códigos vacíos, con formato desconocido o con dígito verificador inválido se importan sin modificar y se listan en un reporte para revisarlos contra el producto físico.
2. **Duplicados:** se buscan códigos de barras repetidos, ya normalizados. Los registros con precio de venta o costo en cero se descartan automáticamente. Si queda una sola opción válida se conserva; si quedan varias, el script pregunta cuál conservar.
3. **Precio de paquete y de pieza** (`$24.00($6.00)`): por cada producto, el script pregunta qué versión conservar (`1` unidad, `2` paquete, `3` eliminar). Si el costo también viene en formato doble, se toma el de la versión elegida. Si los precios de paquete y de unidad son iguales, se conserva el producto sin preguntar.
4. **Exportación:** la unidad de medida es `Unidades`, salvo los productos con precio por kilo (`$30.00/kg`), que usan `kg`.

### Modo automático

Para evitar las preguntas interactivas:

```bash
python3 ./migration/inventario_odoo.py inventario.csv --keep-policy first --variant-policy unidad
```

| Argumento | Valores | Efecto |
|---|---|---|
| `--keep-policy` | `first`, `last` | Conserva el primer o el último registro de cada código de barras duplicado |
| `--variant-policy` | `unidad`, `paquete`, `eliminar` | Aplica la misma opción a todos los productos con precio doble |

Si se interrumpe el script con `Ctrl+C`, no se genera ningún archivo.

### Archivos generados

Se crean en el mismo directorio que el CSV de entrada:

- `<nombre>_odoo.csv` — importar directamente en Odoo
- `<nombre>_barcodes_a_revisar.csv` — códigos vacíos, con formato inválido o dígito verificador incorrecto, con el motivo y la fila de origen
- `<nombre>_descartados.csv` — registros descartados (duplicados y productos eliminados) con la fila de origen y el motivo

## Backups automáticos

Los backups corren automáticamente cada día a las 23:59.

Para configurar en un servidor nuevo:

```bash
crontab -e
# Agregar: 
# 59 23 * * * /opt/odoo-server/infra/scripts/backup.sh >> /opt/odoo-server/infra/logs/backup.cron.log 2>&1
# 59 23 * * 0 /opt/odoo-server/infra/scripts/backup-semanal.sh >> /opt/odoo-server/infra/logs/backup.cron.log 2>&1
```

Para logs: `tail -f /opt/odoo-server/infra/logs/backup.cron.log`

## Estado

Cargando...
