# 🌐 Fuentes de música

Lavalink obtiene el audio mediante **fuentes** integradas y **plugins**:

| Plataforma | Cómo se reproduce | Configuración necesaria | Plugin |
|---|---|---|---|
| YouTube / YouTube Music | Directo | Ninguna (OAuth opcional) | youtube-source |
| SoundCloud, Bandcamp, Twitch, Vimeo, enlaces HTTP | Directo | Ninguna | Lavalink |
| Spotify | Espejo | Client ID + Secret | LavaSrc |
| Apple Music | Espejo | Media API Token | LavaSrc |
| Tidal | Espejo | Token | LavaSrc |
| Deezer | Directo (hasta FLAC) | ARL + clave de descifrado | LavaSrc |
| Qobuz | Directo (alta fidelidad) | Token de usuario (premium) | LavaSrc |

### ¿Qué es "espejo" (mirroring)?

Spotify, Apple Music y Tidal no permiten descargar su audio. LavaSrc lee la **información** de la canción (título, artista, carátula e **ISRC**) y busca **la misma grabación** en una fuente reproducible. Sigue el orden de `providers` en `lavalink/application.yml`:

```yaml
providers:
  - "ytsearch:\"%ISRC%\""   # 1º: búsqueda por ISRC (identificador único de la grabación)
  - "ytsearch:%QUERY%"      # 2º: búsqueda por "título artista"
```

El ISRC evita versiones equivocadas (en directo, remixes, videoclips con intro). Si configuras Deezer o Qobuz, ponlos **primero** para que el audio salga de una fuente sin pérdida:

```yaml
providers:
  - "dzisrc:%ISRC%"
  - "qbisrc:%ISRC%"
  - "ytsearch:\"%ISRC%\""
  - "ytsearch:%QUERY%"
```

> Después de cambiar `.env` o `application.yml`, reinicia Lavalink: `docker compose up -d --force-recreate lavalink`.

---

## YouTube

Funciona sin configuración. Los clientes definidos en `plugins.youtube.clients` se prueban en orden. `MUSIC` permite las búsquedas de YouTube Music (`ytmsearch`), que HexMusic usa por defecto.

### Si YouTube bloquea tu servidor

Los centros de datos a veces reciben errores como *"Sign in to confirm you're not a bot"*, *"This video requires login"* o *"This video is unavailable"*. Soluciones, de la más sencilla a la más avanzada:

1. **Actualiza el plugin.** Pon la [última versión de youtube-source](https://github.com/lavalink-devs/youtube-source/releases) en `application.yml`. Muchas veces basta con esto.

   > **Caso conocido: `TVHTML5 failed: The page needs to be reloaded.`** Desde el 18/08/2026 YouTube rechaza el User-Agent que usa el cliente `TV` en youtube-source 1.18.2 (justo el único que aprovecha la cuenta; PR [#233](https://github.com/lavalink-devs/youtube-source/pull/233)). HexMusic ya trae fijada la compilación corregida (`f45bbb7…` del repositorio de *snapshots*); cuando salga una versión estable con la corrección, se puede volver a `youtube-plugin:1.18.x` con `snapshot: false`.
2. **OAuth con una cuenta secundaria** (la solución más eficaz). La vinculación la gestiona **el bot**, no Lavalink:
   1. Pon `YOUTUBE_OAUTH_ENABLED=true` en `.env` y reinicia el bot y Lavalink.
   2. En cuanto Lavalink está listo, **la consola del bot** (`docker compose logs -f bot`) muestra el recuadro *YOUTUBE: VINCULAR UNA CUENTA DE GOOGLE* con un enlace y un código. Los dueños del bot también lo ven en el [panel web](PANEL_WEB.md) → *Estadísticas*. Ábrelo e inicia sesión con una **cuenta de Google secundaria**, nunca la personal: existe riesgo de que la bloqueen.
   3. Al completarse, el bot guarda el **refresh token** en `data/youtube-refresh-token.txt` (`YOUTUBE_TOKEN_FILE`) y se lo entrega a Lavalink al momento, sin reiniciar. En cada arranque lo comprueba con Google y se lo vuelve a entregar a cada nodo cuando se conecta (también si Lavalink se reinicia).
   4. Si Google rechaza el token (cuenta bloqueada, contraseña cambiada), el bot lo aparta como `.invalido` y muestra un código nuevo. Lavalink sigue funcionando mientras tanto.

   Comando de consola `youtube` (con `bot.console` activado): `youtube estado`, `youtube vincular` (código nuevo sin reiniciar), `youtube desvincular`, `youtube cancelar` y `youtube token <refresh token>` para usar uno que ya tengas. `YOUTUBE_OAUTH_REFRESH_TOKEN` en `.env` fija un token concreto y tiene prioridad sobre el guardado.

   > **Por qué no va el token en `application.yml`:** youtube-source intenta renovarlo al arrancar y, si Google lo rechaza, lanza una excepción que impide arrancar a Lavalink (se quedaba reiniciándose en bucle). Por eso `application.yml` lleva `oauth.skipInitialization: true` y sin `refreshToken`: el bot se lo pasa por la API del plugin (`POST /youtube`). Funciona igual con un Lavalink externo que tenga el plugin.

   > La cuenta **solo la utiliza el cliente `TV`**, el único que admite OAuth en youtube-source. Ya viene incluido al final de `plugins.youtube.clients`; si lo quitas, la vinculación deja de tener efecto y Lavalink lo avisa con *"OAuth has been enabled without registering any OAuth-compatible clients"*. Si YouTube bloquea casi todo, puedes subir `TV` justo debajo de `MUSIC` para ahorrar los intentos fallidos de los demás clientes.

   > **Con el egg de Pterodactyl no hay que copiar nada:** al activar *YouTube con cuenta*, el código aparece en la consola del servidor y el token se guarda solo en `.hex/youtube-refresh-token.txt`. Rellena *YouTube: refresh token* en Startup solo si quieres fijarlo tú.
3. **Servidor de cifrado remoto (yt-cipher).** Es lo que resuelve las firmas que usa el cliente `TV` cuando aparece *`Must find sig function from script`*. La compilación para Pterodactyl lo instala y conecta solo; con Docker, levanta un [yt-cipher](https://github.com/kikkia/yt-cipher) y descomenta el bloque `remoteCipher` de `application.yml`. Como alternativa más sencilla (solo WEB/WEBEMBEDDED) existe el `poToken`. Consulta la [documentación de youtube-source](https://github.com/lavalink-devs/youtube-source#readme).

---

## Spotify

1. Entra en <https://developer.spotify.com/dashboard> y pulsa **Create app**.
2. Pon cualquier nombre y descripción, `http://127.0.0.1` como *Redirect URI* y marca **Web API**.
3. En **Settings** copia el **Client ID** y el **Client Secret**.
4. En `.env`:
   ```env
   SPOTIFY_ENABLED=true
   SPOTIFY_CLIENT_ID=tu_client_id
   SPOTIFY_CLIENT_SECRET=tu_client_secret
   ```
5. Reinicia Lavalink.

Ahora funcionan los enlaces de canciones, álbumes, playlists y artistas, y la búsqueda `spsearch:` (opción *Spotify* de `/play`).

> Spotify limita algunas APIs para las apps nuevas. Si las recomendaciones de Spotify no están disponibles, el autoplay seguirá funcionando con las mezclas de YouTube Music.

---

## Apple Music

Necesitas un **Media API Token**. LavaSrc documenta dos formas:

- **Sin cuenta de desarrollador:** abre <https://music.apple.com>, abre las DevTools (F12) → pestaña *Debugger/Sources* y busca en los archivos `index-*.js` un token que empiece por `ey…` (un JWT). Cópialo.
- **Con cuenta de desarrollador:** crea una clave MusicKit siguiendo la [guía de Apple](https://developer.apple.com/help/account/configure-app-capabilities/create-a-media-identifier-and-private-key/).

```env
APPLEMUSIC_ENABLED=true
APPLEMUSIC_MEDIA_API_TOKEN=eyJ...
```

> Los tokens caducan. Si los enlaces de Apple Music dejan de funcionar, obtén uno nuevo.

---

## Deezer

Deezer reproduce **directamente** y, con una cuenta premium, en **FLAC**. Por eso es la mejor opción para usarla como `provider`.

LavaSrc necesita dos valores:

- `DEEZER_ARL`: la cookie `arl` de tu sesión en deezer.com.
- `DEEZER_MASTER_KEY`: la clave de descifrado que exige LavaSrc. **HexMusic no la incluye.** Consulta la [documentación de LavaSrc](https://github.com/topi314/LavaSrc#deezer) y asegúrate de que su uso es legal donde operas.

```env
DEEZER_ENABLED=true
DEEZER_ARL=...
DEEZER_MASTER_KEY=...
```

El orden de formatos preferidos está en `application.yml → plugins.lavasrc.deezer.formats`. FLAC va primero.

---

## Tidal

```env
TIDAL_ENABLED=true
TIDAL_TOKEN=...
```

Consulta cómo obtener el token en la [documentación de LavaSrc](https://github.com/topi314/LavaSrc#tidal). Tidal funciona en modo espejo, así que el audio sale del primer `provider` que encuentre la canción.

---

## Qobuz

Qobuz reproduce **directamente** en alta fidelidad. **Requiere una cuenta premium.**

1. Abre <https://play.qobuz.com> e inicia sesión.
2. Abre las DevTools (F12) → pestaña **Network**.
3. Selecciona una petición **POST** (no OPTIONS) y copia el valor de la cabecera `x-user-auth-token`.

```env
QOBUZ_ENABLED=true
QOBUZ_USER_OAUTH_TOKEN=...
```

---

## SoundCloud, Bandcamp, Twitch, Vimeo y radios

Vienen activados en Lavalink. Basta con pegar el enlace en `/play`. Para buscar en SoundCloud elige la plataforma *SoundCloud* o escribe `scsearch:`.

Las **radios y archivos de audio** se reproducen pegando su URL directa (`.mp3`, `.aac`, `.ogg`, streams Icecast/Shoutcast, playlists `.m3u`/`.pls`).

> ⚠️ Con la fuente HTTP activada, cualquiera puede hacer que Lavalink se conecte a una URL y ver así la IP de tu servidor. Si te preocupa, pon `http: false` en `application.yml` o configura un proxy (`httpConfig`).

---

## Prefijos de búsqueda

| Prefijo | Plataforma | Prefijo | Plataforma |
|---|---|---|---|
| `ytsearch:` | YouTube | `dzsearch:` | Deezer |
| `ytmsearch:` | YouTube Music | `dzisrc:` | Deezer por ISRC |
| `scsearch:` | SoundCloud | `tdsearch:` | Tidal |
| `spsearch:` | Spotify | `qbsearch:` | Qobuz |
| `amsearch:` | Apple Music | `qbisrc:` | Qobuz por ISRC |

Se pueden escribir directamente en `/play`, o fijar uno como búsqueda por defecto en `config.yml → lavalink.default_search`.
