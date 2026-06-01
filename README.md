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

## Estado

Cargando...
