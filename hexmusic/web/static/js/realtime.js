// Estado de los reproductores en tiempo real (WebSocket) con consultas periódicas de respaldo.
"use strict";

import { api, bus, state, t, toast } from "./core.js";

const POLL_MS = 3000;

class Realtime {
  constructor() {
    this.ws = null;
    this.status = "connecting"; // connecting | live | polling | off
    this.subscriptions = new Set();
    this.retry = 0;
    this.pollTimer = null;
    this.retryTimer = null;
    this.stopped = false;
  }

  start() {
    this.stopped = false;
    this.connect();
    if (!this.pollTimer) this.pollTimer = setInterval(() => this.poll(), POLL_MS);
  }

  stop() {
    this.stopped = true;
    clearInterval(this.pollTimer);
    clearTimeout(this.retryTimer);
    this.pollTimer = null;
    if (this.ws) this.ws.close();
    this.ws = null;
  }

  setStatus(status) {
    if (this.status === status) return;
    this.status = status;
    bus.emit("rt-status", status);
  }

  connect() {
    if (this.stopped || (this.ws && this.ws.readyState <= 1)) return;
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    let ws;
    try {
      ws = new WebSocket(`${scheme}://${location.host}/ws`);
    } catch {
      this.setStatus("polling");
      this.scheduleRetry();
      return;
    }
    this.ws = ws;
    ws.onopen = () => {
      this.retry = 0;
      this.setStatus("live");
      for (const id of this.subscriptions) this.send({ op: "subscribe", guild_id: id });
    };
    ws.onmessage = (event) => {
      let message;
      try {
        message = JSON.parse(event.data);
      } catch {
        return;
      }
      if (message.type === "player") setPlayer(message.guild_id, message.data);
    };
    ws.onclose = () => {
      if (this.ws === ws) this.ws = null;
      if (this.stopped) return;
      this.setStatus("polling");
      this.scheduleRetry();
    };
    ws.onerror = () => ws.close();
  }

  scheduleRetry() {
    clearTimeout(this.retryTimer);
    const delay = Math.min(30000, 1000 * 2 ** Math.min(this.retry, 5));
    this.retry++;
    this.retryTimer = setTimeout(() => this.connect(), delay);
  }

  send(message) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(message));
  }

  subscribe(guildId) {
    if (!guildId || this.subscriptions.has(guildId)) return;
    // Solo interesa el servidor que se está viendo (y el del mini reproductor, que es el mismo)
    for (const id of [...this.subscriptions]) this.unsubscribe(id);
    this.subscriptions.add(guildId);
    this.send({ op: "subscribe", guild_id: guildId });
    if (this.status !== "live") refreshPlayer(guildId);
  }

  unsubscribe(guildId) {
    if (!this.subscriptions.delete(guildId)) return;
    this.send({ op: "unsubscribe", guild_id: guildId });
  }

  async poll() {
    if (this.status === "live" || document.hidden) return;
    for (const id of this.subscriptions) await refreshPlayer(id);
  }
}

export const realtime = new Realtime();

export function setPlayer(guildId, data) {
  state.players.set(String(guildId), { data, at: performance.now() });
  bus.emit("player", { guildId: String(guildId), data });
}

export function getPlayer(guildId) {
  const entry = state.players.get(String(guildId));
  return entry ? entry.data : null;
}

/** Posición estimada de la canción actual (avanza entre actualizaciones). */
export function estimatePosition(guildId) {
  const entry = state.players.get(String(guildId));
  if (!entry || !entry.data.connected || !entry.data.current) return 0;
  const { data, at } = entry;
  if (data.paused || data.current.is_stream) return data.position;
  return Math.min(data.current.length, data.position + (performance.now() - at));
}

export async function refreshPlayer(guildId) {
  try {
    setPlayer(guildId, await api("GET", `/api/guilds/${guildId}/player`));
  } catch {
    /* se mantiene el último estado */
  }
}

/** Acción sobre el reproductor; devuelve true si salió bien (los errores se muestran como aviso). */
export async function playerAction(guildId, payload, successMessage) {
  try {
    const data = await api("POST", `/api/guilds/${guildId}/player`, payload);
    setPlayer(guildId, data);
    if (successMessage) toast(successMessage, "success");
    return true;
  } catch (err) {
    toast(err.message || t("errors.generic"), "error");
    return false;
  }
}
