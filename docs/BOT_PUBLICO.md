# 🌍 HexMusic como bot público

Esta guía prepara HexMusic para que **cualquiera pueda añadirlo a su servidor**: un solo bot y un solo panel (`musica.hexservers.com`) para todos.

**Qué ve cada persona en el panel:** cualquiera puede iniciar sesión con Discord, pero solo gestiona el bot en los servidores donde tiene *Gestionar servidor*, además de sus propias playlists. La administración (configuración global, servidores, registros, cuenta de YouTube) es solo para los dueños del bot.

---

## 1. Discord

1. <https://discord.com/developers/applications> → tu aplicación → **Bot** → activa **Public Bot**. Sin esto, solo tú puedes añadirlo a servidores.
2. En **General Information** rellena la descripción y los enlaces de **Terms of Service** y **Privacy Policy**. Discord los pide para verificar el bot.
3. **Verificación:** a partir de 75 servidores Discord pide verificar el bot y no podrá entrar en más de 100 sin ella. Se solicita desde la pestaña **App Verification**.
4. **Message Content:** con más de 100 servidores, este intent necesita aprobación de Discord, que rara vez la concede a bots de música. Sin ella:
   - Siguen funcionando todos los comandos slash (`/play`…) y los de prefijo **mencionando al bot** (`@HexMusic play …`).
   - El **canal de peticiones** se desactiva solo, porque necesita leer los mensajes.
   - Si Discord rechaza el intent, HexMusic arranca sin él y lo explica en el log, en lugar de reiniciarse en bucle. Para quitar el aviso, pon *Leer el contenido de los mensajes* en **Desactivado** (Panel → Administración → Configuración → General).

## 2. Panel web

En **Administración → Configuración**:

| Ajuste | Recomendado | Por qué |
|---|---|---|
| General → Enlace del servidor de soporte | Invitación a tu Discord | Aparece en la página de entrada y en el menú |
| General → Términos / Privacidad | Tus páginas legales | Se enlazan desde la página de entrada (Discord las exige) |
| Límites → Espacio total de la biblioteca | p. ej. `20000` (20 GB) | Con muchos servidores, 500 MB por servidor pueden llenar el disco |
| Límites → Espacio por servidor | `100`–`200` | Reparte mejor el espacio |
| Reproductor → Tamaño máximo de la cola | `500` | Limita el consumo de memoria |
| Funciones → Días que se guarda el historial | `30`–`90` | La base de datos crece con cada canción |

La página de entrada del panel (`musica.hexservers.com`) muestra el botón **Añadir a tu servidor** a cualquier visitante.

## 3. Capacidad

- **Lavalink:** 1 GB de memoria aguanta unos 100 reproductores a la vez. Con `LAVALINK_MEMORY=auto` usa el 55 % de la memoria del contenedor: dale 2–4 GB en Dokploy (Advanced → Resources) a medida que crezca.
- **Más de un nodo:** cuando un solo Lavalink no baste, añade más nodos en `lavalink.nodes` de `config.yml`; los reproductores se reparten entre ellos.
- **Shards:** el bot usa *AutoShardedBot*, así que reparte la conexión con Discord solo cuando crece.
- **YouTube:** cuanto más tráfico, más probable es que YouTube bloquee la IP del servidor. Vincula una cuenta secundaria (Administración → Resumen → Cuenta de YouTube) y deja activado el cifrado interno (`YOUTUBE_CIPHER=true`). Ver [Fuentes](FUENTES.md).

## 4. Responsabilidad

- La base de datos guarda los tokens de sesión de Discord de quien inicia sesión en el panel y el historial de reproducción de cada servidor: menciónalo en tu política de privacidad y haz copias del volumen `hexmusic-data`.
- Reproducir contenido de YouTube u otras plataformas en un servicio público puede ir contra sus términos de uso. Revísalo antes de anunciar el bot.
