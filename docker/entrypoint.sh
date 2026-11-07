#!/bin/bash
#
# Arranque de la imagen "todo en uno" de HexMusic (Dockerfile de la raíz).
# Es la versión para Docker/Dokploy del entrypoint del egg de Pterodactyl:
#   - comprueba el token y desactiva las fuentes sin credenciales
#   - genera y guarda la contraseña de Lavalink si no se indica
#   - arranca yt-cipher (cifrado de YouTube) y Lavalink en 127.0.0.1, con
#     reinicio automático si se caen
#   - espera a que Lavalink responda y lanza el bot
#   - al parar el contenedor cierra primero el bot (guarda la cola) y luego
#     Lavalink y yt-cipher
#
# Todo lo persistente vive en /app/data (volumen): base de datos, biblioteca,
# token de YouTube, contraseñas generadas, plugins y registros de Lavalink.

# Las rutas se pueden cambiar con variables solo para pruebas.
APP_DIR="${HEXMUSIC_APP_DIR:-/app}"
OPT_DIR="${HEXMUSIC_OPT_DIR:-/opt}"
DATA_DIR="${HEXMUSIC_DATA_DIR:-${APP_DIR}/data}"
STATE_DIR="${DATA_DIR}/.hex"
LOGS_DIR="${DATA_DIR}/logs"
LAVALINK_HOME="${DATA_DIR}/lavalink"
LAVALINK_JAR="${OPT_DIR}/lavalink/Lavalink.jar"
CIPHER_DIR="${OPT_DIR}/yt-cipher"
STOP_FLAG="${TMPDIR:-/tmp}/hexmusic-deteniendo"

cd "${APP_DIR}" || exit 1
rm -f "${STOP_FLAG}"

# ---------------------------------------------------------------------------
# Salida
# ---------------------------------------------------------------------------

C_RESET=$'\033[0m'
C_INFO=$'\033[1;36m'
C_WARN=$'\033[1;33m'
C_ERR=$'\033[1;31m'
C_OK=$'\033[1;32m'
C_DIM=$'\033[1;30m'

log_info()  { printf '%s\n' "${C_INFO}[i]${C_RESET} $*"; }
log_warn()  { printf '%s\n' "${C_WARN}[!]${C_RESET} $*"; }
log_error() { printf '%s\n' "${C_ERR}[x]${C_RESET} $*"; }
log_ok()    { printf '%s\n' "${C_OK}[+]${C_RESET} $*"; }
linea()     { printf '%s\n' "${C_DIM}------------------------------------------------------------${C_RESET}"; }

# Acepta "true", "1", "si", "activado"... sin importar tildes ni mayúsculas.
normalize_value() {
    printf '%s' "${1}" \
        | sed -e 's/[ÁÀ]/A/g' -e 's/[áà]/a/g' -e 's/É/E/g' -e 's/é/e/g' -e 's/Í/I/g' -e 's/í/i/g' \
              -e 's/Ó/O/g' -e 's/ó/o/g' -e 's/[ÚÜ]/U/g' -e 's/[úü]/u/g' -e 's/Ñ/N/g' -e 's/ñ/n/g' \
        | tr '[:upper:]' '[:lower:]'
}

is_true() {
    case "$(normalize_value "${1}")" in
        1|true|yes|on|enabled|si|activado|activada) return 0 ;;
        *) return 1 ;;
    esac
}

# Devuelve el contenido de un archivo de secreto; si no existe, lo genera.
secreto_persistente() {
    local archivo="$1" valor=""
    [ -s "${archivo}" ] && valor=$(cat "${archivo}" 2>/dev/null)
    if [ -z "${valor}" ]; then
        valor=$(tr -dc 'A-Za-z0-9' < /dev/urandom 2>/dev/null | head -c 32)
        [ -n "${valor}" ] || valor="hex$(date +%s%N)"
        printf '%s' "${valor}" > "${archivo}"
        chmod 600 "${archivo}" 2>/dev/null
    fi
    printf '%s' "${valor}"
}

# Límite de memoria del contenedor en MB (0 = sin límite).
memoria_limite_mb() {
    local valor=""
    if [ -r /sys/fs/cgroup/memory.max ]; then
        valor=$(cat /sys/fs/cgroup/memory.max 2>/dev/null)
    elif [ -r /sys/fs/cgroup/memory/memory.limit_in_bytes ]; then
        valor=$(cat /sys/fs/cgroup/memory/memory.limit_in_bytes 2>/dev/null)
    fi
    case "${valor}" in ''|*[!0-9]*) echo 0; return ;; esac
    # cgroup v1 indica "sin límite" con un número enorme.
    [ "${#valor}" -ge 15 ] && { echo 0; return; }
    echo $((valor / 1048576))
}

# ---------------------------------------------------------------------------
# Comprobaciones previas
# ---------------------------------------------------------------------------

linea
log_info "HexMusic — imagen todo en uno (bot + Lavalink + cifrado de YouTube)"
linea

if [ -z "${DISCORD_TOKEN:-}" ]; then
    log_error "Falta DISCORD_TOKEN. Añádelo en las variables de entorno (en Dokploy: pestaña Environment)."
    exit 1
fi

if ! mkdir -p "${STATE_DIR}" "${LOGS_DIR}" "${LAVALINK_HOME}/plugins" 2>/dev/null || [ ! -w "${DATA_DIR}" ]; then
    log_error "No se puede escribir en ${DATA_DIR} (usuario $(id -u))."
    log_error "El volumen de datos debe pertenecer al UID 1000. Arréglalo con:"
    log_error "  docker run --rm -v <volumen>:/data alpine chown -R 1000:1000 /data"
    exit 1
fi

# Registros antiguos (Lavalink escribe además en ${LAVALINK_HOME}/logs).
LOG_RETENTION_DAYS="${LOG_RETENTION_DAYS:-7}"
case "${LOG_RETENTION_DAYS}" in ''|*[!0-9]*) LOG_RETENTION_DAYS=7 ;; esac
if [ "${LOG_RETENTION_DAYS}" -gt 0 ]; then
    find "${LOGS_DIR}" "${LAVALINK_HOME}/logs" -type f -mtime +"${LOG_RETENTION_DAYS}" -delete 2>/dev/null
fi

# ---------------------------------------------------------------------------
# Fuentes de música
# ---------------------------------------------------------------------------
# Una fuente activada sin credenciales hace fallar a LavaSrc y Lavalink no
# arranca: se desactiva con un aviso.

FUENTES="YouTube, SoundCloud, Bandcamp, Twitch"

fuente() {
    local interruptor="$1" nombre="$2" faltan=""
    shift 2
    if ! is_true "${!interruptor:-0}"; then
        export "${interruptor}=false"
        return 0
    fi
    while [ $# -gt 0 ]; do
        [ -n "${!1:-}" ] || faltan="${faltan} ${1}"
        shift
    done
    if [ -n "${faltan}" ]; then
        log_warn "${nombre} está activado pero faltan credenciales (${faltan# }); se desactiva."
        export "${interruptor}=false"
    else
        export "${interruptor}=true"
        FUENTES="${FUENTES}, ${nombre}"
    fi
}

fuente SPOTIFY_ENABLED "Spotify" SPOTIFY_CLIENT_ID SPOTIFY_CLIENT_SECRET
fuente APPLEMUSIC_ENABLED "Apple Music" APPLEMUSIC_MEDIA_API_TOKEN
fuente DEEZER_ENABLED "Deezer" DEEZER_ARL DEEZER_MASTER_KEY
fuente TIDAL_ENABLED "Tidal" TIDAL_TOKEN
fuente QOBUZ_ENABLED "Qobuz" QOBUZ_USER_OAUTH_TOKEN

# La cuenta de YouTube la gestiona el bot (muestra el código en el log y en el
# panel web, guarda el token en data/ y se lo entrega a Lavalink).
if is_true "${YOUTUBE_OAUTH_ENABLED:-0}"; then
    export YOUTUBE_OAUTH_ENABLED=true
    if [ -n "${YOUTUBE_OAUTH_REFRESH_TOKEN:-}" ]; then
        RESUMEN_YOUTUBE="token de la variable YOUTUBE_OAUTH_REFRESH_TOKEN"
    elif [ -s "${DATA_DIR}/youtube-refresh-token.txt" ]; then
        RESUMEN_YOUTUBE="vinculada (token guardado)"
    else
        RESUMEN_YOUTUBE="pendiente: el enlace y el código aparecerán en el log del bot"
    fi
else
    export YOUTUBE_OAUTH_ENABLED=false
    export YOUTUBE_OAUTH_REFRESH_TOKEN=""
fi

# ---------------------------------------------------------------------------
# Lavalink
# ---------------------------------------------------------------------------

LAVALINK_MODE=$(normalize_value "${LAVALINK_MODE:-interno}")
case "${LAVALINK_MODE}" in
    externo|external) LAVALINK_MODE="externo" ;;
    interno|internal|"") LAVALINK_MODE="interno" ;;
    *)
        log_warn "LAVALINK_MODE='${LAVALINK_MODE}' no reconocido; se usa interno."
        LAVALINK_MODE="interno"
        ;;
esac

if [ "${LAVALINK_MODE}" = "externo" ]; then
    case "${LAVALINK_URI:-}" in
        http://*|https://*) ;;
        *)
            log_error "Con LAVALINK_MODE=externo indica LAVALINK_URI (http://host:puerto) y LAVALINK_PASSWORD."
            exit 1
            ;;
    esac
    if [ -z "${LAVALINK_PASSWORD:-}" ]; then
        log_error "Con LAVALINK_MODE=externo hace falta LAVALINK_PASSWORD (la del servidor Lavalink)."
        exit 1
    fi
    LAVALINK_URI="${LAVALINK_URI%/}"
    RESUMEN_LAVALINK="externo (${LAVALINK_URI})"

    # Un Lavalink externo solo puede leer la biblioteca si se le indica cómo llegar al bot.
    if [ -n "${LIBRARY_PUBLIC_URL:-}" ]; then
        export LIBRARY_HOST="${LIBRARY_HOST:-0.0.0.0}"
        RESUMEN_BIBLIOTECA="activada (Lavalink la lee desde ${LIBRARY_PUBLIC_URL})"
    else
        export HEXMUSIC__FEATURES__LIBRARY=0
        RESUMEN_BIBLIOTECA="desactivada (con Lavalink externo indica LIBRARY_PUBLIC_URL)"
    fi
else
    LAVALINK_PORT="${LAVALINK_PORT:-2333}"
    case "${LAVALINK_PORT}" in ''|*[!0-9]*) LAVALINK_PORT=2333 ;; esac
    CIPHER_PORT="${CIPHER_PORT:-2334}"
    case "${CIPHER_PORT}" in ''|*[!0-9]*) CIPHER_PORT=2334 ;; esac

    # Contraseña automática y persistente si no se indica. Nunca se imprime.
    if [ -z "${LAVALINK_PASSWORD:-}" ]; then
        LAVALINK_PASSWORD=$(secreto_persistente "${STATE_DIR}/lavalink-password.txt")
    fi

    # Memoria: "auto" (55 % del límite del contenedor, o 1 GB si no tiene),
    # un número en MB (1024) o el formato de Java (1G, 768m).
    MEMORIA=$(normalize_value "${LAVALINK_MEMORY:-auto}")
    if [ -z "${MEMORIA}" ] || [ "${MEMORIA}" = "auto" ]; then
        LIMITE=$(memoria_limite_mb)
        if [ "${LIMITE}" -gt 0 ]; then
            MB=$((LIMITE * 55 / 100))
            [ "${MB}" -lt 256 ] && MB=256
            LAVALINK_XMX="${MB}m"
            [ "${LIMITE}" -lt 1024 ] && log_warn "El contenedor tiene ${LIMITE} MB: se recomiendan al menos 1024 MB para Lavalink y el bot."
        else
            LAVALINK_XMX="1g"
        fi
    elif [[ "${MEMORIA}" =~ ^[0-9]+$ ]]; then
        LAVALINK_XMX="${MEMORIA}m"
    elif [[ "${MEMORIA}" =~ ^[0-9]+[kmg]$ ]]; then
        LAVALINK_XMX="${MEMORIA}"
    else
        log_warn "LAVALINK_MEMORY='${LAVALINK_MEMORY}' no es válido; se usa 1G."
        LAVALINK_XMX="1g"
    fi

    # Siempre local: aunque Environment traiga un LAVALINK_URI antiguo
    # (p. ej. http://lavalink:2333) aquí no hay otro contenedor.
    LAVALINK_URI="http://127.0.0.1:${LAVALINK_PORT}"
    LAVALINK_VERSION=$(cat "${OPT_DIR}/lavalink/VERSION" 2>/dev/null)
    RESUMEN_LAVALINK="interno ${LAVALINK_VERSION:-} | memoria ${LAVALINK_XMX} | 127.0.0.1:${LAVALINK_PORT}"

    # Biblioteca (/upload): Lavalink descarga los archivos del bot por 127.0.0.1.
    export LIBRARY_HOST=127.0.0.1
    export LIBRARY_PORT="${LIBRARY_PORT:-2340}"
    export LIBRARY_PUBLIC_URL=""
    RESUMEN_BIBLIOTECA="activada (/upload)"
fi

export LAVALINK_URI LAVALINK_PASSWORD

# ---------------------------------------------------------------------------
# Panel web
# ---------------------------------------------------------------------------

RESUMEN_WEB="desactivado"
if is_true "${WEB_ENABLED:-0}"; then
    if [ -z "${WEB_CLIENT_SECRET:-}" ]; then
        log_warn "WEB_ENABLED está activado pero falta WEB_CLIENT_SECRET; se arranca sin panel web."
        WEB_ENABLED=false
    else
        WEB_ENABLED=true
        WEB_PUBLIC_URL="${WEB_PUBLIC_URL:-http://localhost:${WEB_PORT:-8080}}"
        WEB_PUBLIC_URL="${WEB_PUBLIC_URL%/}"
        RESUMEN_WEB="${WEB_PUBLIC_URL} (Redirect en Discord: ${WEB_PUBLIC_URL}/auth/callback)"
    fi
else
    WEB_ENABLED=false
fi
export WEB_ENABLED WEB_PUBLIC_URL WEB_CLIENT_SECRET
export WEB_HOST="${WEB_HOST:-0.0.0.0}"
export WEB_PORT="${WEB_PORT:-8080}"

# ---------------------------------------------------------------------------
# Procesos en segundo plano
# ---------------------------------------------------------------------------

LAVALINK_SUPERVISOR=""
CIPHER_SUPERVISOR=""
BOT_PID=""
DETENIENDO=0

# Añade el bloque remoteCipher a la copia de application.yml (como el egg).
insertar_remote_cipher() {
    local yaml="${LAVALINK_HOME}/application.yml" bloque
    if grep -Eq '^[[:space:]]*remoteCipher:' "${yaml}"; then
        log_info "application.yml ya define remoteCipher; se respeta."
        return 0
    fi
    bloque=$(printf '    # inicio-cifrado-hexmusic (no editar)\n    remoteCipher:\n      url: "http://127.0.0.1:%s"\n      password: "%s"\n      userAgent: "hexmusic"\n    # fin-cifrado-hexmusic' "${CIPHER_PORT}" "${CIPHER_TOKEN}")
    awk -v bloque="${bloque}" '/^  lavasrc:$/ { print bloque } { print }' "${yaml}" > "${yaml}.tmp" || return 1
    if ! grep -q 'inicio-cifrado-hexmusic' "${yaml}.tmp"; then
        rm -f "${yaml}.tmp"
        log_warn "No se encontró dónde insertar remoteCipher en application.yml; se sigue sin cifrado."
        return 1
    fi
    mv "${yaml}.tmp" "${yaml}"
}

# Supervisa un proceso: lo relanza si se cae y lo cierra al recibir TERM.
#   supervisar <nombre> <directorio> <archivo de log | -> <comando...>
# Con "-" la salida va al log del contenedor con el prefijo [nombre].
supervisar() {
    local nombre="$1" directorio="$2" archivo_log="$3"
    shift 3
    [ "${archivo_log}" = "-" ] && archivo_log=""
    (
        pid=""
        trap '[ -n "${pid}" ] && kill "${pid}" 2>/dev/null; wait "${pid}" 2>/dev/null; exit 0' TERM INT
        reinicios=0
        while true; do
            cd "${directorio}" || exit 1
            if [ -n "${archivo_log}" ]; then
                printf '\n===== Arranque: %s =====\n' "$(date '+%Y-%m-%d %H:%M:%S')" >> "${archivo_log}"
                "$@" >> "${archivo_log}" 2>&1 &
            else
                "$@" > >(sed -u "s/^/[${nombre}] /") 2>&1 &
            fi
            pid=$!
            wait "${pid}"
            codigo=$?
            [ -f "${STOP_FLAG}" ] && exit 0
            reinicios=$((reinicios + 1))
            espera=$((reinicios * 5))
            [ "${espera}" -gt 60 ] && espera=60
            printf '%s\n' "${C_WARN}[!]${C_RESET} ${nombre} se cerró (código ${codigo}); reinicio ${reinicios} en ${espera} s."
            if [ -n "${archivo_log}" ]; then
                tail -n 15 "${archivo_log}" 2>/dev/null | sed "s/^/[${nombre}] /"
            fi
            # sleep en segundo plano para que TERM no espere a que termine.
            sleep "${espera}" &
            pid=$!
            wait "${pid}"
        done
    ) &
}

detener_servicios() {
    touch "${STOP_FLAG}"
    local pid
    for pid in "${LAVALINK_SUPERVISOR}" "${CIPHER_SUPERVISOR}"; do
        [ -n "${pid}" ] && kill -TERM "${pid}" 2>/dev/null
    done
    for pid in "${LAVALINK_SUPERVISOR}" "${CIPHER_SUPERVISOR}"; do
        [ -n "${pid}" ] && wait "${pid}" 2>/dev/null
    done
}

# Parada del contenedor (docker stop / redeploy): primero el bot, que guarda
# la cola y se despide de Discord; Lavalink se cierra cuando el bot termina.
parar() {
    DETENIENDO=1
    touch "${STOP_FLAG}"
    if [ -n "${BOT_PID}" ]; then
        kill -TERM "${BOT_PID}" 2>/dev/null
    fi
}
trap parar TERM INT

RESUMEN_CIFRADO="no aplica (Lavalink externo)"

if [ "${LAVALINK_MODE}" = "interno" ]; then
    if [ ! -s "${LAVALINK_JAR}" ]; then
        log_error "No se encuentra ${LAVALINK_JAR} en la imagen. Vuelve a construirla."
        exit 1
    fi
    if [ ! -f "${APP_DIR}/lavalink/application.yml" ]; then
        log_error "Falta lavalink/application.yml en la imagen (revisa .dockerignore)."
        exit 1
    fi
    # La configuración viene siempre del repositorio: se copia en cada arranque.
    tr -d '\r' < "${APP_DIR}/lavalink/application.yml" > "${LAVALINK_HOME}/application.yml"

    RESUMEN_CIFRADO="desactivado"
    if is_true "${YOUTUBE_CIPHER:-1}"; then
        if command -v deno > /dev/null 2>&1 && [ -f "${CIPHER_DIR}/server.ts" ]; then
            CIPHER_TOKEN=$(secreto_persistente "${STATE_DIR}/yt-cipher-token.txt")
            if insertar_remote_cipher; then
                # El log de yt-cipher va a un archivo: es muy verboso.
                if [ -f "${LOGS_DIR}/yt-cipher.log" ] && [ "$(wc -c < "${LOGS_DIR}/yt-cipher.log")" -gt 10485760 ]; then
                    mv -f "${LOGS_DIR}/yt-cipher.log" "${LOGS_DIR}/yt-cipher.log.1"
                fi
                supervisar yt-cipher "${CIPHER_DIR}" "${LOGS_DIR}/yt-cipher.log" \
                    env PORT="${CIPHER_PORT}" HOST=127.0.0.1 API_TOKEN="${CIPHER_TOKEN}" \
                        OVERRIDE_PLAYER_VARIANT=IAS MAX_THREADS=1 \
                    deno run --allow-net --allow-read --allow-write --allow-env server.ts
                CIPHER_SUPERVISOR=$!
                RESUMEN_CIFRADO="activado (yt-cipher interno, log en data/logs/yt-cipher.log)"
            fi
        else
            log_warn "yt-cipher no está en la imagen; se sigue sin cifrado de YouTube."
        fi
    fi
fi

linea
log_info "Resumen de arranque"
log_info "Lavalink: ${RESUMEN_LAVALINK}"
log_info "Fuentes: ${FUENTES}"
[ -n "${RESUMEN_YOUTUBE:-}" ] && log_info "YouTube con cuenta: ${RESUMEN_YOUTUBE}"
log_info "Cifrado de YouTube: ${RESUMEN_CIFRADO}"
log_info "Panel web: ${RESUMEN_WEB}"
log_info "Biblioteca de archivos: ${RESUMEN_BIBLIOTECA}"
linea

if [ "${LAVALINK_MODE}" = "interno" ]; then
    supervisar lavalink "${LAVALINK_HOME}" - \
        java -Xmx"${LAVALINK_XMX}" -XX:+UseG1GC -jar "${LAVALINK_JAR}" \
            --server.port="${LAVALINK_PORT}" --server.address=127.0.0.1
    LAVALINK_SUPERVISOR=$!

    log_info "Arrancando Lavalink (la primera vez descarga sus plugins y tarda más)..."
    ESPERA_MAX="${LAVALINK_TIMEOUT:-180}"
    case "${ESPERA_MAX}" in ''|*[!0-9]*) ESPERA_MAX=180 ;; esac
    ESPERADO=0
    LISTO=0
    while [ "${ESPERADO}" -lt "${ESPERA_MAX}" ] && [ "${DETENIENDO}" = "0" ]; do
        if curl -s -o /dev/null --max-time 2 -H "Authorization: ${LAVALINK_PASSWORD}" \
                "http://127.0.0.1:${LAVALINK_PORT}/version"; then
            LISTO=1
            break
        fi
        sleep 2
        ESPERADO=$((ESPERADO + 2))
    done

    if [ "${DETENIENDO}" = "1" ]; then
        detener_servicios
        exit 0
    fi
    if [ "${LISTO}" = "1" ]; then
        log_ok "Lavalink listo."
    else
        log_warn "Lavalink aún no responde tras ${ESPERA_MAX} s; el bot se conectará en cuanto esté listo."
        log_warn "Revisa arriba las líneas [lavalink] para ver el motivo."
    fi

    if [ -n "${CIPHER_SUPERVISOR}" ]; then
        if curl -s -o /dev/null --max-time 2 "http://127.0.0.1:${CIPHER_PORT}/"; then
            log_ok "Cifrado de YouTube listo."
        else
            log_warn "El cifrado de YouTube aún no responde; detalle en data/logs/yt-cipher.log."
        fi
    fi
fi

# ---------------------------------------------------------------------------
# Bot
# ---------------------------------------------------------------------------

python -m hexmusic &
BOT_PID=$!

CODIGO=0
while true; do
    wait "${BOT_PID}"
    CODIGO=$?
    # wait vuelve antes de tiempo cuando llega una señal: se espera de nuevo
    # hasta que el bot termine de cerrarse.
    kill -0 "${BOT_PID}" 2>/dev/null || break
done

detener_servicios

if [ "${DETENIENDO}" = "1" ] || [ "${CODIGO}" -eq 0 ] || [ "${CODIGO}" -eq 130 ] || [ "${CODIGO}" -eq 143 ]; then
    log_ok "HexMusic se detuvo correctamente."
    exit 0
fi

log_error "El bot se cerró de forma inesperada (código ${CODIGO}); Docker lo reiniciará."
exit "${CODIGO}"
