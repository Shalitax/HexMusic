# 🛠️ Solución de problemas

> Primer paso siempre: **mira los logs**.
> Docker: `docker compose logs --tail 100 bot` y `docker compose logs --tail 100 lavalink`.
> Para más detalle, pon `logging.level: DEBUG` en `config.yml`.

---

### El bot no arranca: `Falta DISCORD_TOKEN`

No existe el archivo `.env` o el token está vacío. Copia `.env.example` como `.env` y pega el token.

### `PrivilegedIntentsRequired`

El bot pide el intent de contenido de mensajes, pero no está activado en el portal. Tienes dos opciones:

- Actívalo en <https://discord.com/developers/applications> → tu app → **Bot** → **Message Content Intent**.
- O pon `bot.message_content_intent: false` en `config.yml`. Dejarán de funcionar el prefijo y el canal de peticiones.

### `Error en la configuración: …`

`config.yml` tiene un valor no válido y el mensaje indica cuál. Suele ser un color sin `#` o un número escrito como texto. Si has roto la indentación del YAML, compárala con la del archivo original.

### Los comandos slash no aparecen

- Los comandos **globales** pueden tardar unos minutos. Reinicia Discord con Ctrl+R.
- Para que aparezcan **al instante**, pon el ID de tu servidor en `DEV_GUILD_ID` y reinicia el bot.
- Comprueba que invitaste el bot con el scope `applications.commands`, usando el enlace de [Instalación](INSTALACION.md#3-invitar-el-bot).
- Fuerza el registro con `hm!sync` (solo dueños del bot).
- ¿Aparecen **duplicados**? Usaste `DEV_GUILD_ID` y luego lo quitaste. Ejecuta `hm!sync clear` en ese servidor.

### "El servidor de audio (Lavalink) no está disponible"

El bot no puede conectar con Lavalink. Busca en el log del bot:

| Mensaje | Causa | Solución |
|---|---|---|
| `Failed to authenticate` | Contraseña distinta | `LAVALINK_PASSWORD` debe coincidir en bot y Lavalink |
| `Cannot connect to host` / `retrying websocket connection` | Lavalink apagado, arrancando o dirección incorrecta | Espera a `Lavalink is ready…`; revisa `LAVALINK_URI` |
| `Check that your Lavalink major version is '4'` | Lavalink 3 o puerto equivocado | Usa Lavalink 4.2+ |

Con Docker, la dirección debe ser `http://lavalink:2333`. El `docker-compose.yml` ya la fuerza.

### Lavalink no descarga los plugins (Linux + Docker)

Si ves `AccessDeniedException` en `/opt/Lavalink/plugins`, arregla los permisos:

```bash
sudo chown -R 322:322 lavalink/plugins
docker compose up -d --force-recreate lavalink
```

### El bot entra al canal pero no suena

1. Comprueba que usas **Lavalink ≥ 4.2.0** y **wavelink ≥ 3.5.1**. Discord exige el cifrado de voz **DAVE**; con versiones anteriores la conexión se cierra con el código `4017`.
2. Revisa el log de Lavalink en busca de errores al cargar la pista.
3. El bot necesita los permisos **Conectar** y **Hablar** en ese canal.
4. En un **canal de escenario** (Stage), el bot tiene que ser orador.

### YouTube: *"Sign in to confirm you're not a bot"*, *"This video requires login"*, *"This video is unavailable"*

YouTube está bloqueando la IP del servidor. Sigue [Fuentes → Si YouTube bloquea tu servidor](FUENTES.md#si-youtube-bloquea-tu-servidor): primero actualiza `youtube-source`, después vincula una cuenta con OAuth.

Al vincular, ten en cuenta:

- El **refresh token** debe quedar guardado (en `.env`, en `application.yml` o, con el egg, en `.hex/`): si no, cada reinicio vuelve a pedir el código.
- El código **caduca y solo sirve para el Lavalink en curso**; si validas uno de un arranque anterior, no hace nada.
- La vinculación **solo la usa el cliente `TV`**: si tu lista de clientes no lo incluye, vincular la cuenta no cambia la reproducción.

Si el error es *`Client [TVHTML5] failed: The page needs to be reloaded.`*, no es culpa del token: es un fallo de youtube-source 1.18.2 (YouTube cambió su política de User-Agent el 18/08/2026). Actualiza el bot: HexMusic ya fija la compilación corregida del plugin. Si tras actualizar aparece *`Must find sig function from script`*, YouTube ha cambiado además el sistema de firmas: valora un servidor de cifrado remoto (`remoteCipher`, comentado en `application.yml`) o espera una nueva versión del plugin.

### Los enlaces de Spotify, Apple Music, Deezer o Tidal no funcionan

- Revisa `…_ENABLED=true` y las credenciales en `.env`, y **reinicia Lavalink**.
- Busca errores de LavaSrc en el log de Lavalink: token caducado o credenciales inválidas.
- Spotify, Apple Music y Tidal necesitan además una fuente reproducible en `providers` (YouTube por defecto).

### El audio se corta

Consulta [Calidad de audio → Diagnóstico de cortes](CALIDAD_AUDIO.md#diagnóstico-de-cortes). Resumen: CPU, memoria de la JVM y distancia a Discord.

### El bot se va del canal solo

Es intencionado:

- `player.idle_timeout`: tiempo sin reproducir nada (300 s por defecto).
- `player.empty_channel_timeout`: tiempo con el canal vacío (120 s por defecto).
- Para que no se vaya nunca usa `/247`, o pon esos valores a `0`.

### Los botones dicen "Esta interacción ha fallado"

- El bot estaba apagado o reiniciándose. Vuelve a intentarlo en unos segundos.
- Si ocurre siempre, revisa el log del bot en busca de errores.

### `/lyrics` no encuentra la letra

Las letras vienen de [LRCLIB](https://lrclib.net), una base de datos comunitaria. Para canciones poco conocidas prueba `/lyrics artista canción`.

### El canal de peticiones no responde

- Hace falta el intent de contenido de mensajes (ver arriba).
- El bot necesita **Gestionar mensajes**, **Enviar mensajes** e **Insertar enlaces** en ese canal.
- Si borraste el mensaje del panel, ejecuta `/setup #canal` para regenerarlo.

### Empezar de cero con los ajustes

- **Un servidor:** `/settings reset`.
- **Todo:** para el bot y borra `data/hexmusic.db`. Con Docker: `docker compose down -v`. ⚠️ Esto también borra todas las playlists.

---

¿Sigue sin funcionar? Reúne esta información para pedir ayuda:

1. El log de `bot` y de `lavalink` desde el arranque.
2. Las versiones (`/stats`).
3. Qué comando usaste y qué respondió el bot.
