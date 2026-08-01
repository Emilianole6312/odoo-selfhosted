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

# Migration

Script de transformación del catálogo del POS anterior a formato Odoo 17.

## Uso

```bash
uv run --with=pandas ./importarodoo.py inventario.csv 
```

Para procesar productos con precio de paquete y de pieza de forma interactiva:

```bash
uv run --with=pandas ./procesarvariantes.py inventario_variantes.csv
```

El script pregunta por cada producto si se elimina, se conserva una
presentación o se conservan ambas. Cuando se conservan ambas, genera un
EAN-13 para la presentación que no conserve el código original.

## Archivos generados

- `<nombre>_odoo.csv` — importar directamente en Odoo
- `<nombre>_variantes.csv` — productos con presentación múltiple, requiere procesamiento manual
- `<nombre>_barcodes_a_revisar.csv` — barcodes con dígito verificador inválido
- `<nombre>_barcodes_generados.csv` — códigos generados por `procesarvariantes.py`


## Estado

Cargando...
