# Runbook: Recuperación de odoo

**Criticidad:** [ALTA]  |  **RTO:** 30 min  |  **RPO:** 24 horas

## Cuándo usar esto
Cuando se pretende levantar una instancia de odoo con datos de un backup.

## 1. Pre-Checks
- [ ] Validar acceso SSH
- [ ] Docker y git instalados
- [ ] Verificar backup existente: `ls -lh /var/backups/odoo/`
- [ ] Verificar que no haya otra instancia de la aplicación activa: `docker ps`

## 2. Pasos
1. Copiar el repositorio de trabajo desde github en `/opt/odoo-server`
```bash
git clone https://github.com/Emilianole6312/odoo-selfhosted.git /opt/odoo-server
```
2. Configurar las variables
```bash
cp /opt/odoo-server/infra/.env.example /opt/odoo-server/infra/.env
vim /opt/odoo-server/infra/.env
```

3. Preparar los volumenes
```bash
cd /opt/odoo-server
rm infra/volumes/postgres/.gitkeep \
   infra/volumes/odoo/data/.gitkeep \
   infra/volumes/odoo/addons/.gitkeep

sudo chown -R 101:101 infra/volumes/odoo/data
sudo chown -R 101:101 infra/volumes/odoo/addons
```

5. Entrar en `infra` y hacer `docker compose`
```bash
cd /opt/odoo-server/infra
docker compose up -d
```

6. Verificar el correcto funcionamiento de odoo: 
```bash
curl http://localhost/web/health
```

Debe devolver:
 
```bash
{"status": "pass"}
```

7. Crear la base de datos `odoo`

```
docker compose exec db createdb -U odoo odoo
```

8. Hacer el dump del backup
```bash
gunzip -c /var/backups/odoo/db_20##-##-##.sql.gz | docker-compose exec -T db psql -U odoo
gunzip -c /var/backups/odoo/filestore_2026-08-22.tar.gz | docker exec -i $(docker-compose ps -q odoo) tar -xC /var/lib/odoo/
```

9. Reiniciar el contenedor de odoo

```bash
docker compose restart odoo
```

## 3. Validación
### Funcional
- `curl http://localhost/health` => debe retornar 200
- Revisar logs: `docker compose logs -f` => no debe haber errores

### Verificar integridad de los datos

- Ir a `http://localhost:PORT/` =>  debe redirigir al login en lugar del database selector

[TBD - Implementación de métricas para verificar la integridad de las copias de seguridad]

## 4. Si falla
Verificar los logs:
```bash
cd /opt/odoo-server/infra
docker compose logs
```
### database odoo does not exist	
En caso de ver:
```
Error: database "odoo" does not exist
```

Crear la bd:
```bash
docker compose exec db createdb -U odoo odoo
```
