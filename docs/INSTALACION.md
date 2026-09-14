# 📦 Instalación

Esta guía te lleva de cero a tener HexMusic sonando en tu servidor de Discord.

- [1. Requisitos](#1-requisitos)
- [2. Crear la aplicación en Discord](#2-crear-la-aplicación-en-discord)
- [3. Invitar el bot](#3-invitar-el-bot)
- [4. Opción A — Docker (recomendada)](#4-opción-a--docker-recomendada)
- [5. Opción B — Instalación manual (sin Docker)](#5-opción-b--instalación-manual-sin-docker)
- [6. Primeros pasos en Discord](#6-primeros-pasos-en-discord)
- [7. Producción y 24/7](#7-producción-y-247)
- [8. Actualizar](#8-actualizar)

---

## 1. Requisitos

HexMusic tiene **dos piezas**:

| Pieza | Qué hace | Requisitos |
|---|---|---|
| **Lavalink** | Descarga, decodifica y codifica el audio y lo envía a Discord | Java 17+ · 1 GB de RAM recomendado |
| **Bot (Python)** | Comandos, botones, colas, base de datos | Python 3.10+ · ~100 MB de RAM |

Con **Docker** no necesitas instalar ni Java ni Python: solo [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows/macOS) o Docker Engine + Compose (Linux).

**Hardware orientativo**

| Uso | CPU | RAM |
|---|---|---|
| Hasta ~50 reproductores | 1 vCPU | 1,5 GB |
| Hasta ~250 reproductores | 2 vCPU dedicadas | 3 GB |
| Más | Varios nodos de Lavalink ([ver Personalización](PERSONALIZACION.md#varios-nodos-de-lavalink)) | — |

> Los filtros de audio y los volúmenes distintos de 100 % consumen bastante más CPU, porque obligan a recodificar el audio.

---

## 2. Crear la aplicación en Discord

1. Entra en <https://discord.com/developers/applications> y pulsa **New Application**. Ponle de nombre `HexMusic`.
2. En **General Information** sube el avatar y la descripción. Apunta el **Application ID**: lo necesitarás para invitar el bot.
3. Ve a **Bot**:
   - Pulsa **Reset Token**, copia el token y guárdalo para el archivo `.env`. **No lo compartas nunca.**
   - En **Privileged Gateway Intents** activa **Message Content Intent**. Es necesario para los comandos con prefijo (`hm!play`) y para el canal de peticiones.
     > Si solo vas a usar comandos slash, puedes dejarlo desactivado y poner `message_content_intent: false` en `config.yml`.
   - Si quieres que solo tú puedas invitarlo, desactiva **Public Bot**.

---

## 3. Invitar el bot

Sustituye `TU_APPLICATION_ID` y abre este enlace:

```
https://discord.com/oauth2/authorize?client_id=TU_APPLICATION_ID&scope=bot+applications.commands&permissions=3533904
```

El número `3533904` incluye justo los permisos que usa HexMusic:

| Permiso | Para qué |
|---|---|
| Ver canales, Enviar mensajes, Insertar enlaces, Adjuntar archivos, Leer el historial | Responder a los comandos y mostrar paneles |
| Usar emojis externos, Añadir reacciones | Emojis personalizados en los botones y embeds |
| Gestionar mensajes | Limpiar el canal de peticiones |
| Gestionar canales | Crear el canal de peticiones con `/setup` |
| Conectar, Hablar | Reproducir música |

Cuando el bot esté en marcha, el comando `/invite` te dará este mismo enlace.

---

## 4. Opción A — Docker (recomendada)

### 4.1 Preparar los archivos

```bash
cd HexMusic
cp .env.example .env
```

En Windows (PowerShell) usa `Copy-Item .env.example .env`.

Abre `.env` y rellena como mínimo:

```env
DISCORD_TOKEN=el_token_que_copiaste
LAVALINK_PASSWORD=una_contraseña_larga_y_aleatoria
```

> Opcional: pon en `DEV_GUILD_ID` el ID de tu servidor de pruebas. Así los comandos slash aparecen al instante ahí. Para copiar IDs, activa el Modo desarrollador en Discord: Ajustes → Avanzado.

**Solo en Linux:** Lavalink se ejecuta con el usuario `322` y necesita poder escribir en la carpeta de plugins:

```bash
mkdir -p lavalink/plugins
sudo chown -R 322:322 lavalink/plugins
```

### 4.2 Arrancar

```bash
docker compose up -d --build
```

La primera vez tarda uno o dos minutos: Docker construye la imagen del bot y Lavalink descarga sus plugins.

### 4.3 Comprobar

```bash
docker compose logs -f lavalink   # espera a: "Lavalink is ready to accept connections."
docker compose logs -f bot        # espera a: "Nodo Lavalink 'main' listo"
```

Comandos útiles:

| Acción | Comando |
|---|---|
| Ver estado | `docker compose ps` |
| Reiniciar el bot (tras cambiar `config.yml` o los idiomas) | `docker compose restart bot` |
| Reiniciar Lavalink (tras cambiar `.env` o `application.yml`) | `docker compose up -d --force-recreate lavalink` |
| Parar todo | `docker compose down` |

> La base de datos vive en el volumen `hexmusic-data` y **no se borra** con `docker compose down`. Solo se elimina con `docker compose down -v`.

---

## 5. Opción B — Instalación manual (sin Docker)

### 5.1 Lavalink

1. Instala **Java 17 o superior**. Recomendado: [Eclipse Temurin 21](https://adoptium.net/). Compruébalo con `java -version`.
2. Descarga `Lavalink.jar` **4.2.2** desde <https://github.com/lavalink-devs/Lavalink/releases> y guárdalo en la carpeta `lavalink/`, junto a `application.yml`.
3. Lavalink lee las variables de entorno (contraseña, credenciales de Spotify…), pero **no lee el archivo `.env` por sí solo**. Arráncalo cargándolas antes:

**Linux / macOS**

```bash
cd lavalink
set -a; source ../.env; set +a
java -Xmx1G -jar Lavalink.jar
```

**Windows (PowerShell)**

```powershell
cd lavalink
Get-Content ..\.env | Where-Object { $_ -match '^\s*[A-Za-z_]+=.*' } | ForEach-Object {
    $name, $value = $_ -split '=', 2
    Set-Item -Path "env:$($name.Trim())" -Value $value.Trim()
}
java -Xmx1G -jar Lavalink.jar
```

Espera al mensaje `Lavalink is ready to accept connections.`

### 5.2 Bot

En otra terminal, desde la carpeta `HexMusic`:

```bash
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

pip install -r requirements.txt
```

Comprueba que `.env` tiene `LAVALINK_URI=http://localhost:2333` y arranca:

```bash
python -m hexmusic
```

---

## 6. Primeros pasos en Discord

1. Entra en un canal de voz y usa `/play <canción o enlace>`.
2. *(Recomendado)* `/setup` crea el canal de peticiones con el panel de control.
3. `/settings language es` o `en` cambia el idioma del servidor.
4. *(Opcional)* `/settings djrole @DJ` limita los comandos sensibles al rol DJ.
5. `/help` muestra todos los comandos.

---

## 7. Producción y 24/7

### Docker

`restart: unless-stopped` ya está configurado: los contenedores se reinician solos si fallan o si se reinicia el servidor. Solo tienes que activar Docker al arrancar el sistema con `sudo systemctl enable docker`.

### systemd (instalación manual en Linux)

`/etc/systemd/system/hexmusic-lavalink.service`

```ini
[Unit]
Description=HexMusic Lavalink
After=network-online.target

[Service]
User=hexmusic
WorkingDirectory=/opt/HexMusic/lavalink
EnvironmentFile=/opt/HexMusic/.env
ExecStart=/usr/bin/java -Xmx1G -jar Lavalink.jar
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/hexmusic-bot.service`

```ini
[Unit]
Description=HexMusic Bot
After=hexmusic-lavalink.service
Wants=hexmusic-lavalink.service

[Service]
User=hexmusic
WorkingDirectory=/opt/HexMusic
ExecStart=/opt/HexMusic/.venv/bin/python -m hexmusic
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now hexmusic-lavalink hexmusic-bot
journalctl -u hexmusic-bot -f
```

### Pterodactyl (egg de HexServers)

Hay un **egg propio** en `Pterodactyl eggs/HexMusic`. Hace todo en **un único servidor**:

- Imagen con Python 3.12 y Java 21.
- Lavalink interno escuchando solo en `127.0.0.1`, con reinicio automático.
- Panel web en el puerto principal.
- Dependencias de Python que solo se reinstalan cuando cambian.
- Actualización del bot sin tocar la configuración ni la base de datos.
- Consola con comandos y todas las opciones en la pestaña Startup, en español.

Resumen:

1. Publica esta carpeta en un repositorio Git (puede ser privado).
2. Importa `egg-hexmusic.json` en el panel.
3. Crea el servidor con 1 GB de RAM o más y una asignación de puerto.
4. Rellena *Token del bot* y *Repositorio del bot*, instala y arranca.

La guía completa está en el `README.md` del egg.

### Otros paneles (Pelican, etc.)

Si tu panel no puede usar el egg, crea **dos servidores**:

1. **Lavalink**, con un egg de Java (17+). Sube `Lavalink.jar` y `application.yml` y define las variables de `.env`. Arranca con `java -Xmx1G -jar Lavalink.jar --server.port=<puerto asignado>`.
2. **Bot**, con un egg de Python (3.10+). Sube el proyecto, usa `python -m hexmusic` como comando de arranque y define `LAVALINK_URI=http://IP_DEL_NODO:PUERTO` y `LAVALINK_PASSWORD`.

> ⚠️ Si Lavalink queda expuesto a Internet, usa una contraseña larga. Si es posible, permite su puerto solo desde la IP del bot.

---

## 8. Actualizar

1. Guarda una copia de `.env`, `config.yml`, `locales/` y la base de datos (`data/` o el volumen `hexmusic-data`).
2. Sustituye los archivos del proyecto por la nueva versión.
3. Revisa si hay claves nuevas en `config.yml` o `.env.example`. Las que falten usan su valor por defecto.
4. Reinicia:
   - **Docker:** `docker compose pull && docker compose up -d --build`
   - **Manual:** `pip install -r requirements.txt` y reinicia los servicios.

Para actualizar los **plugins de Lavalink**, cambia el número de versión en `lavalink/application.yml` y reinicia Lavalink. Los plugins de YouTube se actualizan con frecuencia para seguir los cambios de la plataforma:

- youtube-source: <https://github.com/lavalink-devs/youtube-source/releases>
- LavaSrc: <https://github.com/topi314/LavaSrc/releases>
