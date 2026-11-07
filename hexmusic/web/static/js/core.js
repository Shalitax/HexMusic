// Núcleo del panel: estado, DOM seguro, API, iconos, diálogos y formato.
"use strict";

export const state = {
  public: { name: "HexMusic", color: "#8b5cf6", avatar: null, version: "" },
  me: null,
  lang: "es",
  languages: [],
  strings: {},
  guildId: null,
  guilds: new Map(), // id → detalles del servidor (GET /api/guilds/:id)
  players: new Map(), // id → { data, at }
  playlists: null,
};

// ───── Almacenamiento local (preferencias de este navegador) ─────

export const store = {
  get(key, fallback = null) {
    try {
      const value = localStorage.getItem(`hexmusic.${key}`);
      return value === null ? fallback : value;
    } catch {
      return fallback;
    }
  },
  set(key, value) {
    try {
      if (value === null || value === undefined) localStorage.removeItem(`hexmusic.${key}`);
      else localStorage.setItem(`hexmusic.${key}`, String(value));
    } catch {
      /* sin almacenamiento local */
    }
  },
};

// ───── DOM ─────

/** Crea elementos sin interpretar nunca texto como HTML. */
export function h(tag, props, ...children) {
  const el = document.createElement(tag);
  const later = {};
  for (const [key, value] of Object.entries(props || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "style" && typeof value === "object") {
      for (const [name, style] of Object.entries(value)) {
        if (name.startsWith("--")) el.style.setProperty(name, style);
        else el.style[name] = style;
      }
    } else if (key === "dataset") Object.assign(el.dataset, value);
    else if (key === "ref") later.ref = value;
    else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2).toLowerCase(), value);
    else if (["value", "checked", "disabled", "selected", "indeterminate"].includes(key)) later[key] = value;
    else el.setAttribute(key, value === true ? "" : String(value));
  }
  append(el, children);
  for (const [key, value] of Object.entries(later)) {
    if (key === "ref") value(el);
    else el[key] = value;
  }
  return el;
}

/** Sustituye el contenido de un elemento ignorando null/false (replaceChildren los escribiría como texto). */
export function fill(el, ...children) {
  el.replaceChildren();
  return append(el, children);
}

export function append(el, children) {
  for (const child of [children].flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

const SVG_NS = "http://www.w3.org/2000/svg";

export function svg(tag, attrs, ...children) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined) continue;
    if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2).toLowerCase(), value);
    else el.setAttribute(key, String(value));
  }
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

// Iconos propios (24×24, trazo). [etiqueta, atributos, relleno?]
const P = (d, fill) => ["path", { d }, fill];
const C = (cx, cy, r, fill) => ["circle", { cx, cy, r }, fill];
const R = (x, y, width, height, rx, fill) => ["rect", { x, y, width, height, rx }, fill];
const ICONS = {
  home: [P("M3 10.5 12 3l9 7.5"), P("M5 9.5V21h14V9.5"), P("M10 21v-6h4v6")],
  music: [P("M9 18V5l11-2v13"), C(6, 18, 3), C(17, 16, 3)],
  play: [P("M7 4.5v15l12.5-7.5z", true)],
  pause: [R(6, 4.5, 4, 15, 1, true), R(14, 4.5, 4, 15, 1, true)],
  next: [P("M5 5.5v13l10-6.5z", true), P("M18.5 5v14")],
  prev: [P("M19 5.5v13L9 12z", true), P("M5.5 5v14")],
  stop: [R(6, 6, 12, 12, 2, true)],
  replay: [P("M3 12a9 9 0 1 0 3-6.7L3 8"), P("M3 3v5h5")],
  repeat: [P("M17 2l4 4-4 4"), P("M3 11V9a3 3 0 0 1 3-3h15"), P("M7 22l-4-4 4-4"), P("M21 13v2a3 3 0 0 1-3 3H3")],
  repeat1: [P("M17 2l4 4-4 4"), P("M3 11V9a3 3 0 0 1 3-3h15"), P("M7 22l-4-4 4-4"), P("M21 13v2a3 3 0 0 1-3 3H3"), P("M11 10.5l1.5-1v5")],
  shuffle: [P("M16 3h5v5"), P("M4 20 21 3"), P("M21 16v5h-5"), P("M15 15l6 6"), P("M4 4l5 5")],
  volume: [P("M11 5 6 9H2v6h4l5 4z"), P("M15.5 8.5a5 5 0 0 1 0 7"), P("M19 5a10 10 0 0 1 0 14")],
  mute: [P("M11 5 6 9H2v6h4l5 4z"), P("M22 9l-6 6"), P("M16 9l6 6")],
  search: [C(11, 11, 7), P("M21 21l-4.3-4.3")],
  library: [P("M4 4v16"), P("M8.5 4v16"), P("M13 4v16"), P("M16.5 4.7l4 15.3")],
  history: [P("M3 12a9 9 0 1 0 3-6.7L3 8"), P("M3 3v5h5"), P("M12 7v5l3 2")],
  settings: [P("M4 6h9"), P("M17 6h3"), C(15, 6, 2), P("M4 12h3"), P("M11 12h9"), C(9, 12, 2), P("M4 18h11"), P("M19 18h1"), C(17, 18, 2)],
  shield: [P("M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z")],
  list: [P("M9 6h12"), P("M9 12h12"), P("M9 18h12"), P("M4 6h.01"), P("M4 12h.01"), P("M4 18h.01")],
  queueNext: [P("M4 6h12"), P("M4 12h8"), P("M4 18h8"), P("M18 13v8"), P("M14 17h8")],
  plus: [P("M12 5v14"), P("M5 12h14")],
  x: [P("M6 6l12 12"), P("M18 6 6 18")],
  trash: [P("M4 7h16"), P("M9 7V4h6v3"), P("M6 7l1 13h10l1-13"), P("M10 11v5"), P("M14 11v5")],
  edit: [P("M4 20h4L19 9l-4-4L4 16z"), P("M13.5 6.5l4 4")],
  upload: [P("M12 16V4"), P("M7 9l5-5 5 5"), P("M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3")],
  logout: [P("M15 4h4a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-4"), P("M10 17l5-5-5-5"), P("M15 12H3")],
  sun: [C(12, 12, 4), P("M12 2v2"), P("M12 20v2"), P("M4.9 4.9l1.4 1.4"), P("M17.7 17.7l1.4 1.4"), P("M2 12h2"), P("M20 12h2"), P("M4.9 19.1l1.4-1.4"), P("M17.7 6.3l1.4-1.4")],
  moon: [P("M20 14.5A8 8 0 1 1 9.5 4 6.5 6.5 0 0 0 20 14.5z")],
  monitor: [R(3, 4, 18, 12, 2), P("M8 20h8"), P("M12 16v4")],
  menu: [P("M4 6h16"), P("M4 12h16"), P("M4 18h16")],
  chevronDown: [P("M6 9l6 6 6-6")],
  chevronRight: [P("M9 6l6 6-6 6")],
  chevronLeft: [P("M15 6l-6 6 6 6")],
  updown: [P("M8 9l4-4 4 4"), P("M8 15l4 4 4-4")],
  grip: [C(9, 6, 1.2, true), C(15, 6, 1.2, true), C(9, 12, 1.2, true), C(15, 12, 1.2, true), C(9, 18, 1.2, true), C(15, 18, 1.2, true)],
  mic: [R(9, 3, 6, 11, 3), P("M5 11a7 7 0 0 0 14 0"), P("M12 18v3")],
  users: [C(9, 8, 3.5), P("M2.5 20a6.5 6.5 0 0 1 13 0"), P("M16 4.5a3.5 3.5 0 0 1 0 7"), P("M18 14.5a6.5 6.5 0 0 1 3.5 5.5")],
  server: [R(3, 4, 18, 7, 2), R(3, 13, 18, 7, 2), P("M7 7.5h.01"), P("M7 16.5h.01")],
  activity: [P("M3 12h4l3-8 4 16 3-8h4")],
  terminal: [R(3, 4, 18, 16, 2), P("M7 9l3 3-3 3"), P("M12 15h5")],
  palette: [P("M12 21a9 9 0 1 1 9-9c0 2-1.5 3-3.5 3H15a2 2 0 0 0-1.5 3.3A1.6 1.6 0 0 1 12 21z"), P("M7.5 11h.01"), P("M10 7.5h.01"), P("M14.5 7.5h.01")],
  smile: [C(12, 12, 9), P("M8.5 14.5a4.5 4.5 0 0 0 7 0"), P("M9 9.5h.01"), P("M15 9.5h.01")],
  gauge: [P("M4 18a8 8 0 1 1 16 0"), P("M12 18l4-5")],
  toggle: [R(2, 7, 20, 10, 5), C(16, 12, 2.5)],
  globe: [C(12, 12, 9), P("M3 12h18"), P("M12 3a14 14 0 0 1 0 18"), P("M12 3a14 14 0 0 0 0 18")],
  refresh: [P("M20 11a8 8 0 0 0-14.5-4.5L4 8"), P("M4 3v5h5"), P("M4 13a8 8 0 0 0 14.5 4.5L20 16"), P("M20 21v-5h-5")],
  external: [P("M14 4h6v6"), P("M20 4l-9 9"), P("M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5")],
  check: [P("M5 12l5 5 9-10")],
  alert: [P("M12 3 2 20h20z"), P("M12 10v4"), P("M12 17h.01")],
  info: [C(12, 12, 9), P("M12 11v5"), P("M12 8h.01")],
  infinity: [P("M6.5 8a4 4 0 1 0 0 8c3 0 8-8 11-8a4 4 0 1 1 0 8c-3 0-8-8-11-8z")],
  hash: [P("M5 9h14"), P("M5 15h14"), P("M10 4 8 20"), P("M16 4l-2 16")],
  headphones: [P("M4 15v-3a8 8 0 0 1 16 0v3"), R(3, 14, 4, 7, 1.5), R(17, 14, 4, 7, 1.5)],
  disc: [C(12, 12, 9), C(12, 12, 2.5)],
  crown: [P("M3 8l4 4 5-7 5 7 4-4-2 11H5z")],
  door: [P("M14 4H6a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h8"), P("M18 8l4 4-4 4"), P("M22 12H10")],
  save: [P("M5 4h11l3 3v12a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1z"), P("M8 4v5h7V4"), R(8, 13, 8, 7, 1)],
  folder: [P("M3 7a1 1 0 0 1 1-1h5l2 2h9a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z")],
  radio: [C(12, 12, 2), P("M8.5 15.5a5 5 0 0 1 0-7"), P("M15.5 8.5a5 5 0 0 1 0 7"), P("M5.5 18.5a9 9 0 0 1 0-13"), P("M18.5 5.5a9 9 0 0 1 0 13")],
  inbox: [P("M3 13h5l1.5 3h5L16 13h5"), P("M5.5 5h13L21 13v6H3v-6z")],
  clock: [C(12, 12, 9), P("M12 7v5l3 2")],
  copy: [R(8, 8, 12, 12, 2), P("M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3")],
  dots: [C(5, 12, 1.4, true), C(12, 12, 1.4, true), C(19, 12, 1.4, true)],
  chart: [P("M4 20h16"), P("M7 16v-5"), P("M12 16V6"), P("M17 16v-8")],
  sliders: [P("M4 21v-7"), P("M4 10V3"), P("M12 21v-9"), P("M12 8V3"), P("M20 21v-5"), P("M20 12V3"), P("M1.5 14h5"), P("M9.5 8h5"), P("M17.5 16h5")],
  user: [C(12, 8, 4), P("M4 21a8 8 0 0 1 16 0")],
  link: [P("M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"), P("M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1")],
  pin: [P("M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11z"), C(12, 10, 2.5)],
  bolt: [P("M13 2 4 14h7l-1 8 9-12h-7z")],
  database: [P("M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3z"), P("M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6"), P("M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3")],
  youtube: [R(2.5, 5.5, 19, 13, 4), P("M10 9.5v5l4.5-2.5z", true)],
  plug: [P("M9 2v6"), P("M15 2v6"), P("M6 8h12v3a6 6 0 0 1-12 0z"), P("M12 17v5")],
};

export function icon(name, cls = "") {
  const parts = ICONS[name] || ICONS.info;
  return svg("svg", { class: `icon ${cls}`.trim(), viewBox: "0 0 24 24", "aria-hidden": "true", focusable: "false" },
    parts.map(([tag, attrs, fill]) => svg(tag, fill ? { ...attrs, fill: "currentColor", stroke: "none" } : attrs)));
}

// ───── Traducción ─────

export function t(key, params) {
  let node = state.strings;
  for (const part of key.split(".")) node = node && typeof node === "object" ? node[part] : undefined;
  if (typeof node !== "string") return key;
  if (!params) return node;
  return node.replace(/\{(\w+)\}/g, (match, name) => (name in params ? String(params[name]) : match));
}

/** Traducción opcional: devuelve null si la clave no existe. */
export function tryT(key, params) {
  const value = t(key, params);
  return value === key ? null : value;
}

// ───── Eventos ─────

const listeners = new Map();
export const bus = {
  on(event, fn) {
    if (!listeners.has(event)) listeners.set(event, new Set());
    listeners.get(event).add(fn);
    return () => listeners.get(event).delete(fn);
  },
  emit(event, data) {
    for (const fn of [...(listeners.get(event) || [])]) {
      try {
        fn(data);
      } catch (err) {
        console.error(err);
      }
    }
  },
};

/** Recursos de una vista (intervalos, suscripciones) que se liberan al salir de ella. */
export class Scope {
  constructor() {
    this.disposers = [];
    this.alive = true;
  }
  add(fn) {
    if (this.alive) this.disposers.push(fn);
    else fn();
  }
  on(event, fn) {
    this.add(bus.on(event, fn));
  }
  every(ms, fn) {
    const id = setInterval(fn, ms);
    this.add(() => clearInterval(id));
  }
  listen(target, event, fn, options) {
    target.addEventListener(event, fn, options);
    this.add(() => target.removeEventListener(event, fn, options));
  }
  dispose() {
    this.alive = false;
    for (const fn of this.disposers.splice(0)) {
      try {
        fn();
      } catch {
        /* nada que limpiar */
      }
    }
  }
}

// ───── API ─────

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

export async function api(method, path, body) {
  const headers = { Accept: "application/json", "X-Lang": state.lang };
  const options = { method, headers, credentials: "same-origin" };
  if (method !== "GET") {
    headers["X-CSRF-Token"] = state.me ? state.me.csrf : "";
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
  }
  let response;
  try {
    response = await fetch(path, options);
  } catch {
    throw new ApiError(t("errors.network"), 0);
  }
  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  if (response.status === 401 && path !== "/api/me" && state.me) bus.emit("session-expired");
  if (!response.ok) throw new ApiError((data && data.error) || t("errors.generic"), response.status);
  return data;
}

/** Subida con progreso (fetch no informa del progreso de envío). */
export function uploadFile(path, form, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", path);
    xhr.setRequestHeader("X-CSRF-Token", state.me ? state.me.csrf : "");
    xhr.setRequestHeader("X-Lang", state.lang);
    xhr.setRequestHeader("Accept", "application/json");
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) onProgress(event.loaded / event.total);
    };
    xhr.onload = () => {
      let data = null;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        data = null;
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data);
      else reject(new ApiError((data && data.error) || t("errors.generic"), xhr.status));
    };
    xhr.onerror = () => reject(new ApiError(t("errors.network"), 0));
    xhr.send(form);
  });
}

// ───── Avisos y diálogos ─────

export function toast(message, type = "info") {
  const box = document.getElementById("toasts");
  const iconName = type === "success" ? "check" : type === "error" ? "alert" : "info";
  const el = h("div", { class: `toast toast-${type}`, role: type === "error" ? "alert" : "status" },
    icon(iconName), h("div", { class: "grow" }, message));
  box.append(el);
  setTimeout(() => el.classList.add("hide"), 4200);
  setTimeout(() => el.remove(), 4600);
}

/** Muestra un error de la API como aviso y devuelve false (útil en cadenas). */
export function fail(err) {
  toast(err && err.message ? err.message : t("errors.generic"), "error");
  return false;
}

function modal(build) {
  return new Promise((resolve) => {
    const previous = document.activeElement;
    let backdrop;
    const close = (value) => {
      document.removeEventListener("keydown", onKey, true);
      backdrop.remove();
      if (previous && previous.focus) previous.focus();
      resolve(value);
    };
    const onKey = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        close(null);
      }
    };
    const box = build(close);
    backdrop = h("div", { class: "modal-backdrop", onMousedown: (event) => { if (event.target === backdrop) close(null); } }, box);
    document.body.append(backdrop);
    document.addEventListener("keydown", onKey, true);
    const focusable = box.querySelector("input, textarea, select, .btn-primary, .btn-danger-solid, button");
    if (focusable) focusable.focus();
  });
}

export function confirmDialog({ title, message, confirm, danger = false }) {
  return modal((close) => h("div", { class: "modal", role: "dialog", "aria-modal": "true" },
    h("div", { class: "modal-title" }, icon(danger ? "alert" : "info", "icon-lg"), h("h2", null, title)),
    message ? h("p", { class: "muted" }, message) : null,
    h("div", { class: "row end" },
      h("button", { class: "btn btn-ghost", onClick: () => close(false) }, t("common.cancel")),
      h("button", { class: `btn ${danger ? "btn-danger" : "btn-primary"}`, onClick: () => close(true) }, confirm || t("common.confirm")))))
    .then((value) => value === true);
}

export function promptDialog({ title, label, value = "", maxlength = 100, confirm }) {
  return modal((close) => {
    const input = h("input", { class: "input", value, maxlength });
    const submit = (event) => {
      event.preventDefault();
      const text = input.value.trim();
      if (text) close(text);
    };
    return h("form", { class: "modal", role: "dialog", "aria-modal": "true", onSubmit: submit },
      h("h2", null, title),
      h("label", { class: "field" }, label ? h("span", { class: "field-label" }, label) : null, input),
      h("div", { class: "row end" },
        h("button", { class: "btn btn-ghost", type: "button", onClick: () => close(null) }, t("common.cancel")),
        h("button", { class: "btn btn-primary", type: "submit" }, confirm || t("common.save"))));
  });
}

// ───── Formato ─────

export const fmt = {
  duration(ms) {
    const total = Math.max(0, Math.floor((ms || 0) / 1000));
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const seconds = total % 60;
    const pad = (n) => String(n).padStart(2, "0");
    return hours ? `${hours}:${pad(minutes)}:${pad(seconds)}` : `${minutes}:${pad(seconds)}`;
  },
  long(ms) {
    const minutes = Math.round((ms || 0) / 60000);
    if (minutes < 60) return t("time.minutes", { count: minutes });
    const hours = Math.floor(minutes / 60);
    if (hours < 48) return t("time.hours_minutes", { hours, minutes: minutes % 60 });
    return t("time.days_hours", { days: Math.floor(hours / 24), hours: hours % 24 });
  },
  uptime(seconds) {
    const total = Math.floor(seconds || 0);
    const days = Math.floor(total / 86400);
    const hours = Math.floor((total % 86400) / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    return [days ? `${days}d` : null, days || hours ? `${hours}h` : null, `${minutes}m`].filter(Boolean).join(" ");
  },
  bytes(value) {
    const n = Number(value) || 0;
    if (n < 1024) return `${n} B`;
    const units = ["KB", "MB", "GB", "TB"];
    let size = n / 1024;
    let unit = 0;
    while (size >= 1024 && unit < units.length - 1) {
      size /= 1024;
      unit++;
    }
    return `${size.toFixed(size >= 100 ? 0 : 1)} ${units[unit]}`;
  },
  number(value) {
    return new Intl.NumberFormat(state.lang).format(Number(value) || 0);
  },
  compact(value) {
    return new Intl.NumberFormat(state.lang, { notation: "compact", maximumFractionDigits: 1 }).format(Number(value) || 0);
  },
  date(seconds, withTime = true) {
    const options = withTime ? { dateStyle: "medium", timeStyle: "short" } : { dateStyle: "medium" };
    return new Intl.DateTimeFormat(state.lang, options).format(new Date(seconds * 1000));
  },
  relative(seconds) {
    const diff = seconds - Date.now() / 1000;
    const abs = Math.abs(diff);
    const rtf = new Intl.RelativeTimeFormat(state.lang, { numeric: "auto" });
    if (abs < 60) return rtf.format(Math.round(diff), "second");
    if (abs < 3600) return rtf.format(Math.round(diff / 60), "minute");
    if (abs < 86400) return rtf.format(Math.round(diff / 3600), "hour");
    if (abs < 86400 * 30) return rtf.format(Math.round(diff / 86400), "day");
    return fmt.date(seconds, false);
  },
};

export const safeUrl = (url) => (typeof url === "string" && /^https?:\/\//i.test(url) ? url : null);

const SOURCES = {
  youtube: "YouTube", spotify: "Spotify", applemusic: "Apple Music", deezer: "Deezer", tidal: "Tidal", qobuz: "Qobuz",
  soundcloud: "SoundCloud", bandcamp: "Bandcamp", twitch: "Twitch", http: "HTTP", vimeo: "Vimeo", local: "Local",
};
export const sourceName = (source) => SOURCES[source] || source || "—";

export function cover(url, cls = "thumb") {
  if (safeUrl(url)) return h("img", { class: cls, src: url, alt: "", loading: "lazy", referrerpolicy: "no-referrer" });
  return h("div", { class: cls }, icon("music"));
}

export function avatar(url, cls = "avatar") {
  if (safeUrl(url)) return h("img", { class: cls, src: url, alt: "", loading: "lazy" });
  return h("div", { class: `${cls} placeholder` }, icon("user", "icon-sm"));
}

export function guildIcon(guild, size = "") {
  const cls = `guild-icon ${size}`.trim();
  if (guild && safeUrl(guild.icon)) return h("img", { class: cls, src: guild.icon, alt: "" });
  const name = (guild && guild.name) || "?";
  const initials = name.split(/\s+/).map((word) => word[0] || "").join("").slice(0, 3);
  return h("div", { class: cls }, initials);
}

// ───── Componentes ─────

export function spinner(cls = "") {
  return h("div", { class: `spinner ${cls}`.trim(), role: "status", "aria-label": t("common.loading") });
}

export function loading() {
  return h("div", { class: "loading" }, spinner());
}

export function emptyState(iconName, title, text, action) {
  return h("div", { class: "empty" },
    h("div", { class: "icon-wrap" }, icon(iconName, "icon-lg")),
    title ? h("h3", null, title) : null,
    text ? h("p", null, text) : null,
    action || null);
}

export function card(options, ...children) {
  const { title, iconName, sub, actions, cls } = options || {};
  const header = title || actions
    ? h("div", { class: "card-header" },
      h("div", { class: "title" }, iconName ? icon(iconName) : null, h("h2", null, title), sub ? h("span", { class: "sub" }, sub) : null),
      actions ? h("div", { class: "row tight wrap" }, actions) : null)
    : null;
  return h("section", { class: `card ${cls || ""}`.trim() }, header, children);
}

export function iconButton(name, label, onClick, cls = "", disabled = false) {
  return h("button", { class: `icon-btn ${cls}`.trim(), type: "button", title: label, "aria-label": label, onClick, disabled }, icon(name));
}

export function switchControl(checked, onChange, label, disabled = false) {
  const input = h("input", { type: "checkbox", checked, disabled, role: "switch", "aria-label": label || null,
    onChange: (event) => onChange(event.target.checked, event.target) });
  return h("label", { class: "switch" }, input, h("span", { class: "switch-track" }), label ? h("span", null, label) : null);
}

export function field(label, control, hint, extra) {
  return h("label", { class: "field" },
    h("span", { class: "field-label" }, label, extra || null),
    control,
    hint ? h("span", { class: "field-hint" }, hint) : null);
}

export function select(options, value, onChange, cls = "select") {
  const el = h("select", { class: cls, onChange: onChange ? (event) => onChange(event.target.value) : null },
    options.map((option) => h("option", { value: option.value }, option.label)));
  el.value = value === null || value === undefined ? "" : String(value);
  return el;
}

export function segmented(options, value, onChange) {
  const root = h("div", { class: "segmented", role: "radiogroup" });
  const draw = (current) => {
    root.replaceChildren(...options.map((option) => h("button", {
      type: "button",
      class: option.value === current ? "active" : "",
      role: "radio",
      "aria-checked": option.value === current ? "true" : "false",
      title: option.title || null,
      onClick: () => {
        if (option.value !== current) onChange(option.value);
      },
    }, option.icon ? icon(option.icon, "icon-sm") : null, option.label)));
  };
  draw(value);
  root.update = draw;
  return root;
}

export function tile(iconName, label, value, sub) {
  return h("div", { class: "tile" },
    h("div", { class: "tile-label" }, icon(iconName), label),
    h("div", { class: "tile-value", title: String(value) }, value),
    sub ? h("div", { class: "tile-sub" }, sub) : null);
}

/** Barra de proporción. Con status (uso de espacio) se pone ámbar/roja al acercarse al límite. */
export function meter(fraction, cls = "", status = true) {
  const pct = Math.max(0, Math.min(1, fraction || 0));
  const level = !status ? "" : pct >= 0.95 ? "danger" : pct >= 0.8 ? "warn" : "";
  return h("div", { class: `meter ${level} ${cls}`.trim(), role: "progressbar", "aria-valuemin": 0, "aria-valuemax": 100,
    "aria-valuenow": Math.round(pct * 100) }, h("span", { style: { width: `${pct * 100}%` } }));
}

/** Cierra un menú flotante al hacer clic fuera o pulsar Escape. */
export function popover(anchor, build) {
  const existing = document.querySelector(".popover");
  if (existing) {
    existing.remove();
    if (existing.anchor === anchor) return;
  }
  const el = h("div", { class: "popover", role: "menu" });
  el.anchor = anchor;
  const close = () => {
    el.remove();
    document.removeEventListener("mousedown", outside, true);
    document.removeEventListener("keydown", onKey, true);
  };
  const outside = (event) => {
    if (!el.contains(event.target) && !anchor.contains(event.target)) close();
  };
  const onKey = (event) => {
    if (event.key === "Escape") close();
  };
  build(el, close);
  document.body.append(el);
  const rect = anchor.getBoundingClientRect();
  const width = el.offsetWidth;
  const left = Math.min(Math.max(8, rect.left), window.innerWidth - width - 8);
  const below = rect.bottom + 6;
  const top = below + el.offsetHeight > window.innerHeight - 8 ? Math.max(8, rect.top - el.offsetHeight - 6) : below;
  el.style.left = `${left}px`;
  el.style.top = `${top}px`;
  document.addEventListener("mousedown", outside, true);
  document.addEventListener("keydown", onKey, true);
  const first = el.querySelector("input, button");
  if (first) first.focus();
  return close;
}
