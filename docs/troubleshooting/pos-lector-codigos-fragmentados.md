# POS: lector de códigos de barras envía códigos incompletos o fragmentados

## Síntoma
El POS recibe el código por partes o incompleto (ej. en tablets Android).

## Causa
El lector emula un teclado. Odoo agrupa las teclas en un mismo escaneo solo si llegan dentro del umbral `barcode.max_time_between_keys_in_ms`. Con el valor por defecto, los lectores lentos fragmentan el código.

## Solución
Parámetro del sistema `barcode.max_time_between_keys_in_ms` = `500` (ms).

Ajustes → Técnico → Parámetros → Parámetros del sistema (modo desarrollador).
Después, recargar la sesión del POS.

## Verificación
Ejecutar: 
```
source .env
docker compose exec db psql -U odoo -d odoo -c \
  "SELECT key, value FROM ir_config_parameter WHERE key = 'barcode.max_time_between_keys_in_ms';"
```
Verificar la existencia del parametro y su valor.

Verificar el correcto funcionaminto del lector de codigos de barras con tableta Android.

## Notas
- Si 500 ms no basta, subir gradualmente. Un valor muy alto puede mezclar
  tecleo manual con escaneos.
- El parámetro vive en la base de datos (`ir_config_parameter`), se restaura con la copia de seguridad.
