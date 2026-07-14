# Runbook: Aprovisionamiento de servidor Odoo desde cero

## Cuándo usar esto
Cuando se necesita levantar el stack de Odoo en un servidor nuevo, ya sea por reemplazo de hardware o recuperación ante desastre.

## Tiempo estimado: 30-45 minutos

## Prerequisitos
- Servidor con linux
- Acceso SSH con usuario sudo
- Acceso al repositorio en GitHub
- Archivo `.env` con credenciales disponible

---

## Pasos

### 1. Instalar dependencias del sistema
Instalamos Docker y Git, que son los únicos requisitos del stack.

    sudo apt update
    sudo apt install -y docker.io docker-compose-plugin git

Agregamos nuestro usuario al grupo docker para no requerir sudo en cada comando:

    sudo usermod -aG docker $USER
    newgrp docker

### 2. Clonar el repositorio
El repositorio contiene toda la configuración del stack. Lo clonamos en `/opt/odoo-server` que es la ruta de trabajo del servidor.

    sudo git clone https://github.com/Emilianole6312/odoo-selfhosted.git \
        /opt/odoo-server
    sudo chown -R $USER:$USER /opt/odoo-server
    cd /opt/odoo-server

### 3. Configurar credenciales
El archivo `.env` contiene las credenciales reales y nunca está en git.
Hay que crearlo manualmente a partir del ejemplo:

    cp infra/.env.example infra/.env
    vim infra/.env

Llenar los valores:

    ODOO_DB_USER=odoo
    ODOO_DB_PASSWORD=<contraseña segura>

### 4. Alistar directorios para montar
El directorio de Odoo necesita ser propiedad del UID 101 (usuario odoo dentro del contenedor):

    sudo chown -R 101:101 infra/volumes/odoo/data
    sudo chown -R 101:101 infra/volumes/odoo/addons

Vaciar el directorio infra/volumes/postgres/

    rm infra/volumes/postgres/.gitkeep \
        infra/volumes/odoo/data/.gitkeep \
        infra/volumes/odoo/addons/.gitkeep

### 5. Levantar el stack
    cd infra
    docker compose up -d

Verificar que los tres contenedores están corriendo:

    docker compose ps

Deberías ver db, odoo y nginx con estado `running`.

### 6. Verificar que Odoo responde
    curl -I http://localhost

Debe responder `HTTP/1.1 200 OK`. Si responde 500 revisar logs:

    docker compose logs odoo --tail=50

### 7. Inicializar la base de datos
Abrir en el navegador `http://<ip-del-servidor>` y completar el
formulario de creación de base de datos:

    Database name: odoo
    Email:         admin@ejemplo.com
    Password:      <contraseña de admin>
    Language:      Spanish
    Country:       Mexico

Este paso tarda entre 3 y 5 minutos mientras Odoo inicializa el esquema.

### 8. Verificar funcionamiento
- Confirmar que el login funciona
- Ir a Punto de Venta y verificar que el módulo está disponible
- Hacer una venta de prueba

---

## Si algo sale mal

**Contenedor db no levanta:**

    docker compose logs db --tail=30
    # Si dice "permission denied" en el volumen:
    sudo chown -R 101:101 infra/volumes/postgres/

**Odoo devuelve 500:**

    docker compose logs odoo --tail=50
    # Si dice "database odoo does not exist", limpiar volumen y reiniciar:
    docker compose down
    sudo rm -rf infra/volumes/postgres/*
    docker compose up -d

**Nginx no responde:**

    docker compose logs nginx --tail=20
