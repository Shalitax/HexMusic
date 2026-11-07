// Arranque del panel: sesión, rutas, estructura (menú, barra superior, mini reproductor) e inicio de sesión.
"use strict";

import { fill,
  ApiError, Scope, api, avatar, bus, card, cover, emptyState, guildIcon, h, icon, iconButton, loading, popover,
  safeUrl, select, state, store, t, toast,
} from "./core.js";
import { estimatePosition, getPlayer, playerAction, realtime } from "./realtime.js";
import * as admin from "./views/admin.js";
import * as historyView from "./views/history.js";
import * as home from "./views/home.js";
import * as library from "./views/library.js";
import * as player from "./views/player.js";
import * as playlists from "./views/playlists.js";
import * as search from "./views/search.js";
import * as settings from "./views/settings.js";

const app = document.getElementById("app");
const GUILD_TABS = ["player", "search", "library", "history", "settings"];
const ADMIN_TABS = ["overview", "config", "guilds", "logs"];
const THEMES = ["system", "light", "dark"];
const THEME_ICONS = { system: "monitor", light: "sun", dark: "moon" };

let route = { name: "home", query: {} };
let scope = null;
let leaveGuard = null;
let lastHash = location.hash;
const shell = {};

// ───── Tema e idioma ─────

function applyTheme(theme) {
  document.documentElement.dataset.theme = THEMES.includes(theme) ? theme : "system";
}

function applyPublic() {
  document.documentElement.style.setProperty("--accent", state.public.color || "#8b5cf6");
}

async function loadStrings(lang) {
  const data = await api("GET", `/api/i18n?lang=${encodeURIComponent(lang || "")}`);
  state.lang = data.lang;
  state.languages = data.languages;
  state.strings = data.strings;
  document.documentElement.lang = data.lang;
  store.set("lang", data.lang);
}

// ───── Rutas ─────

function parseRoute() {
  const [path, queryString] = location.hash.replace(/^#\/?/, "").split("?");
  const parts = path.split("/").filter(Boolean);
  const query = Object.fromEntries(new URLSearchParams(queryString || ""));
  if (parts[0] === "g" && /^\d+$/.test(parts[1] || "")) {
    return { name: "guild", guildId: parts[1], tab: GUILD_TABS.includes(parts[2]) ? parts[2] : "player", query };
  }
  if (parts[0] === "playlists") {
    return /^\d+$/.test(parts[1] || "") ? { name: "playlist", id: parts[1], query } : { name: "playlists", query };
  }
  if (parts[0] === "admin" && state.me && state.me.owner) {
    return { name: "admin", tab: ADMIN_TABS.includes(parts[1]) ? parts[1] : "overview", query };
  }
  return { name: "home", query };
}

function pickGuild(current) {
  if (current.name === "guild") return current.guildId;
  const present = state.me.guilds.filter((guild) => guild.bot_present);
  const stored = store.get("guild");
  if (stored && present.some((guild) => guild.id === stored)) return stored;
  if (state.guildId && present.some((guild) => guild.id === state.guildId)) return state.guildId;
  return present.length ? present[0].id : null;
}

function guildSummary(id) {
  return state.me.guilds.find((guild) => guild.id === id) || (state.guilds.get(id) ? { id, ...state.guilds.get(id) } : { id, name: id });
}

// ───── Barra lateral ─────

function navLink(href, iconName, label, active, extra) {
  return h("a", { class: `nav-item${active ? " active" : ""}`, href, "aria-current": active ? "page" : null }, icon(iconName), h("span", { class: "grow ellipsis" }, label), extra || null);
}

function guildMenu(anchor) {
  popover(anchor, (el, close) => {
    const filter = h("input", { class: "input sm", type: "search", placeholder: t("nav.find_server") });
    const list = h("div");
    const draw = () => {
      const text = filter.value.trim().toLowerCase();
      fill(list, ...state.me.guilds.filter((guild) => !text || guild.name.toLowerCase().includes(text)).map((guild) => (guild.bot_present
        ? h("button", { class: `popover-item${guild.id === state.guildId ? " active" : ""}`, role: "menuitem",
          onClick: () => { close(); location.hash = `#/g/${guild.id}/${route.name === "guild" ? route.tab : "player"}`; } },
        guildIcon(guild, "sm"), h("span", { class: "grow ellipsis" }, guild.name), guild.id === state.guildId ? icon("check", "icon-sm") : null)
        : h("div", { class: "popover-item disabled" }, guildIcon(guild, "sm"), h("span", { class: "grow ellipsis" }, guild.name),
          safeUrl(guild.invite_url) ? h("a", { class: "btn btn-xs", href: guild.invite_url, target: "_blank", rel: "noopener noreferrer" }, t("nav.invite")) : null))));
    };
    filter.addEventListener("input", draw);
    draw();
    fill(el, state.me.guilds.length > 6 ? h("div", { class: "search" }, filter) : null, list);
  });
}

function drawSidebar() {
  const me = state.me;
  const gid = state.guildId;
  const g = gid ? guildSummary(gid) : null;
  const p = gid ? getPlayer(gid) : null;
  const playing = Boolean(p && p.connected && p.current && !p.paused);
  const tab = route.name === "guild" ? route.tab : null;

  const switcher = me.guilds.length
    ? h("button", { class: "guild-switch", onClick: (event) => guildMenu(event.currentTarget), "aria-haspopup": "menu" },
      g ? guildIcon(g) : h("div", { class: "guild-icon" }, icon("server", "icon-sm")),
      h("div", { class: "names" }, h("span", { class: "label" }, t("nav.server")), h("span", { class: "strong ellipsis" }, g ? g.name : t("nav.choose_server"))),
      icon("updown", "icon-sm"))
    : null;

  fill(shell.sidebar, 
    h("div", { class: "brand" }, avatar(state.public.avatar, "avatar"), h("span", { class: "ellipsis" }, state.public.name),
      state.public.version ? h("span", { class: "badge version" }, `v${state.public.version}`) : null),
    switcher,
    h("nav", { class: "nav-group" },
      h("div", { class: "nav-title" }, t("nav.general")),
      navLink("#/", "home", t("nav.home"), route.name === "home"),
      navLink("#/playlists", "folder", t("nav.playlists"), route.name === "playlists" || route.name === "playlist")),
    g ? h("nav", { class: "nav-group" },
      h("div", { class: "nav-title" }, h("span", { class: "ellipsis" }, g.name)),
      navLink(`#/g/${gid}/player`, "headphones", t("nav.player"), tab === "player", playing ? h("span", { class: "live-dot", title: t("player.now_playing") }) : null),
      navLink(`#/g/${gid}/search`, "search", t("nav.search"), tab === "search"),
      me.features.library ? navLink(`#/g/${gid}/library`, "library", t("nav.library"), tab === "library") : null,
      me.features.history ? navLink(`#/g/${gid}/history`, "history", t("nav.history"), tab === "history") : null,
      navLink(`#/g/${gid}/settings`, "settings", t("nav.settings"), tab === "settings")) : null,
    me.owner ? h("nav", { class: "nav-group" },
      h("div", { class: "nav-title" }, icon("crown", "icon-sm"), t("nav.admin")),
      navLink("#/admin/overview", "activity", t("admin.overview"), route.name === "admin" && route.tab === "overview"),
      navLink("#/admin/config", "sliders", t("admin.config"), route.name === "admin" && route.tab === "config"),
      navLink("#/admin/guilds", "server", t("admin.guilds"), route.name === "admin" && route.tab === "guilds"),
      navLink("#/admin/logs", "terminal", t("admin.logs"), route.name === "admin" && route.tab === "logs")) : null,
    h("div", { class: "sidebar-footer muted tiny" }, t("nav.footer", { name: state.public.name })));
  shell.sidebarPlaying = playing;
}

// ───── Barra superior ─────

function drawRtStatus() {
  const status = realtime.status;
  const tone = status === "live" ? "ok" : status === "polling" ? "warn" : "";
  fill(shell.rt, h("span", { class: `dot ${tone}` }), h("span", { class: "label" }, t(`nav.rt_${status}`)));
  shell.rt.title = t(`nav.rt_${status}_hint`);
}

function userMenu(anchor) {
  popover(anchor, (el, close) => {
    const theme = store.get("theme", "system");
    fill(el,
      h("div", { class: "row", style: { padding: "8px 10px" } }, avatar(state.me.user.avatar, "avatar lg"),
        h("div", { class: "grow" }, h("div", { class: "strong ellipsis" }, state.me.user.name),
          state.me.owner ? h("span", { class: "badge accent" }, icon("crown", "icon-sm"), t("nav.owner")) : h("span", { class: "muted small" }, t("nav.member")))),
      h("div", { class: "nav-title", style: { padding: "8px 10px 4px" } }, t("nav.theme")),
      THEMES.map((name) => h("button", { class: `popover-item${theme === name ? " active" : ""}`, onClick: () => {
        store.set("theme", name);
        applyTheme(name);
        drawTopbarIcons();
        close();
      } }, icon(THEME_ICONS[name]), h("span", { class: "grow" }, t(`nav.theme_${name}`)), theme === name ? icon("check", "icon-sm") : null)),
      state.languages.length > 1 ? [
        h("div", { class: "nav-title", style: { padding: "8px 10px 4px" } }, t("login.language")),
        state.languages.map((item) => h("button", { class: `popover-item${item.code === state.lang ? " active" : ""}`, onClick: async () => {
          close();
          await loadStrings(item.code);
          renderShell();
        } }, icon("globe"), h("span", { class: "grow" }, item.name), item.code === state.lang ? icon("check", "icon-sm") : null)),
      ] : null,
      h("div", { style: { borderTop: "1px solid var(--border)", margin: "6px 0" } }),
      h("button", { class: "popover-item", onClick: () => { close(); logout(); } }, icon("logout"), t("nav.logout")));
  });
}

function drawTopbarIcons() {
  const theme = store.get("theme", "system");
  fill(shell.themeBtn, icon(THEME_ICONS[theme] || "monitor"));
  shell.themeBtn.title = t(`nav.theme_${theme}`);
}

function setTitle(title, crumb) {
  fill(shell.heading, crumb ? h("span", { class: "crumb ellipsis" }, crumb) : null, h("h1", null, title));
  document.title = `${title} · ${state.public.name}`;
}

// ───── Mini reproductor ─────

let miniSig = "";

function drawMini(force = false) {
  const gid = state.guildId;
  const p = gid ? getPlayer(gid) : null;
  const show = Boolean(p && p.connected && p.current && !(route.name === "guild" && route.tab === "player"));
  document.body.classList.toggle("has-mini", show);
  shell.mini.hidden = !show;
  if (!show) {
    miniSig = "";
    return;
  }
  const track = p.current;
  const sig = JSON.stringify([gid, track.uri, track.title, p.paused, p.volume, p.queue_length]);
  if (sig === miniSig && !force) return;
  miniSig = sig;
  const volume = h("input", { type: "range", min: 0, max: (state.guilds.get(gid) || {}).max_volume || 150, value: p.volume, "aria-label": t("player.volume"),
    onChange: (event) => playerAction(gid, { action: "volume", value: Number(event.target.value) }) });
  shell.miniBar = h("span", { style: { width: "0%" } });
  fill(shell.mini, 
    h("div", { class: "info", role: "link", tabindex: 0, title: t("nav.open_player"),
      onClick: () => { location.hash = `#/g/${gid}/player`; },
      onKeydown: (event) => { if (event.key === "Enter") location.hash = `#/g/${gid}/player`; } },
    cover(track.artwork),
    h("div", { class: "text", style: { display: "grid", minWidth: 0 } },
      h("span", { class: "strong ellipsis" }, track.title),
      h("span", { class: "muted small ellipsis" }, `${track.author || ""} · ${guildSummary(gid).name}`))),
    h("div", { class: "center" },
      h("div", { class: "controls" },
        iconButton("prev", t("player.previous"), () => playerAction(gid, { action: "previous" }), "sm"),
        iconButton(p.paused ? "play" : "pause", p.paused ? t("player.resume") : t("player.pause"),
          () => playerAction(gid, { action: "pause", paused: !p.paused }), "play"),
        iconButton("next", t("player.skip"), () => playerAction(gid, { action: "skip" }), "sm")),
      track.is_stream ? h("span", { class: "live-pill" }, t("player.live")) : h("div", { class: "bar" }, shell.miniBar)),
    h("div", { class: "right" }, icon("volume", "icon-sm"), volume,
      h("a", { class: "btn btn-sm btn-ghost", href: `#/g/${gid}/player`, title: t("nav.open_player") }, icon("list", "icon-sm"),
        p.queue_length ? h("span", { class: "badge" }, p.queue_length) : null)));
  tickMini();
}

function tickMini() {
  const gid = state.guildId;
  const p = gid ? getPlayer(gid) : null;
  if (!shell.miniBar || !p || !p.current || p.current.is_stream || shell.mini.hidden) return;
  const pct = p.current.length ? Math.min(100, (estimatePosition(gid) / p.current.length) * 100) : 0;
  shell.miniBar.style.width = `${pct}%`;
}

// ───── Vistas ─────

async function loadGuild(id) {
  const guild = await api("GET", `/api/guilds/${id}`);
  state.guilds.set(id, guild);
  return guild;
}

async function refreshPublic() {
  try {
    state.public = await api("GET", "/api/public");
    applyPublic();
    drawSidebar();
  } catch {
    /* se mantiene lo anterior */
  }
}

async function renderView() {
  if (scope) scope.dispose();
  scope = new Scope();
  const current = scope;
  leaveGuard = null;
  route = parseRoute();
  state.guildId = pickGuild(route);
  if (state.guildId) {
    store.set("guild", state.guildId);
    realtime.subscribe(state.guildId);
  }
  document.body.classList.remove("nav-open");
  drawSidebar();
  drawMini(true);
  fill(shell.main, loading());
  window.scrollTo(0, 0);

  const ctx = {
    root: shell.main,
    route,
    scope: current,
    setTitle,
    refreshPublic,
    beforeLeave: (fn) => { leaveGuard = fn; },
  };
  try {
    if (route.name === "guild") {
      ctx.guild = await loadGuild(route.guildId);
      if (!current.alive) return;
      drawSidebar();
      const view = { player, search, library, history: historyView, settings }[route.tab];
      await view.render(ctx);
    } else if (route.name === "playlists") await playlists.renderList(ctx);
    else if (route.name === "playlist") await playlists.renderDetail(ctx);
    else if (route.name === "admin") await admin.render(ctx);
    else await home.render(ctx);
  } catch (err) {
    if (!current.alive) return;
    if (err instanceof ApiError && err.status === 401) return;
    setTitle(t("errors.title"));
    fill(shell.main, card({}, emptyState("alert", err.message || t("errors.generic"), null,
      h("a", { class: "btn btn-primary", href: "#/" }, icon("home", "icon-sm"), t("nav.home")))));
  }
}

function onHashChange() {
  if (leaveGuard) {
    const message = leaveGuard();
    if (message && !window.confirm(message)) {
      history.replaceState(null, "", lastHash);
      return;
    }
  }
  lastHash = location.hash;
  if (state.me) renderView();
}

function renderShell() {
  shell.sidebar = h("aside", { class: "sidebar", "aria-label": t("nav.menu") });
  shell.heading = h("div", { class: "page-heading" });
  shell.rt = h("span", { class: "rt-status", role: "status" });
  shell.themeBtn = h("button", { class: "icon-btn", type: "button", onClick: () => {
    const next = THEMES[(THEMES.indexOf(store.get("theme", "system")) + 1) % THEMES.length];
    store.set("theme", next);
    applyTheme(next);
    drawTopbarIcons();
  } });
  const lang = select(state.languages.map((item) => ({ value: item.code, label: item.name })), state.lang, async (value) => {
    await loadStrings(value);
    renderShell();
  }, "select sm");
  lang.setAttribute("aria-label", t("login.language"));
  lang.classList.add("lang-select");
  lang.style.width = "auto";
  shell.main = h("main", { class: "content", id: "main" });
  shell.mini = h("div", { class: "mini", hidden: true, role: "region", "aria-label": t("nav.mini_player") });

  fill(app, h("div", { class: "layout" },
    shell.sidebar,
    h("div", { class: "overlay", onClick: () => document.body.classList.remove("nav-open") }),
    h("div", { class: "main-area" },
      h("header", { class: "topbar" },
        h("button", { class: "icon-btn menu-btn", type: "button", "aria-label": t("nav.menu"), onClick: () => document.body.classList.toggle("nav-open") }, icon("menu")),
        shell.heading,
        h("div", { class: "topbar-actions" },
          shell.rt,
          shell.themeBtn,
          state.languages.length > 1 ? lang : null,
          h("button", { class: "user-btn", type: "button", "aria-haspopup": "menu", onClick: (event) => userMenu(event.currentTarget) },
            avatar(state.me.user.avatar), h("span", { class: "name small strong" }, state.me.user.name), icon("chevronDown", "icon-sm")))),
      shell.main),
    shell.mini));
  drawRtStatus();
  drawTopbarIcons();
  renderView();
}

// ───── Sesión ─────

async function logout() {
  try {
    await api("POST", "/auth/logout");
  } catch {
    /* la sesión ya no existía */
  }
  state.me = null;
  realtime.stop();
  renderLogin();
}

function renderLogin() {
  if (scope) scope.dispose();
  document.body.classList.remove("has-mini");
  document.title = state.public.name;
  const reason = new URLSearchParams(location.search).get("login_error");
  if (reason !== null) history.replaceState(null, "", location.pathname + location.hash);
  const failed = reason === null ? null : (state.strings.login && state.strings.login.errors && state.strings.login.errors[reason]) || t("login.error");
  const lang = select(state.languages.map((item) => ({ value: item.code, label: item.name })), state.lang, async (value) => {
    await loadStrings(value);
    renderLogin();
  }, "select sm");
  lang.style.width = "auto";
  fill(app, h("div", { class: "login" }, h("div", { class: "login-card" },
    avatar(state.public.avatar, "login-avatar"),
    h("h1", null, state.public.name),
    h("p", { class: "muted" }, t("login.subtitle")),
    failed ? h("div", { class: "alert" }, icon("alert"), h("div", null, failed)) : null,
    h("div", { class: "login-features" },
      h("div", null, icon("headphones"), t("login.feature_player")),
      h("div", null, icon("library"), t("login.feature_library")),
      h("div", null, icon("chart"), t("login.feature_stats"))),
    h("a", { class: "btn btn-discord btn-block", href: "/auth/login" }, t("login.button")),
    h("div", { class: "login-footer" }, state.languages.length > 1 ? lang : null))));
}

// ───── Arranque ─────

async function boot() {
  applyTheme(store.get("theme", "system"));
  try {
    state.public = await api("GET", "/api/public");
    applyPublic();
    await loadStrings(store.get("lang") || (navigator.language || "").split("-")[0]);
  } catch (err) {
    fill(app, h("div", { class: "login" }, h("div", { class: "login-card" }, h("p", null, err.message))));
    return;
  }
  try {
    state.me = await api("GET", "/api/me");
  } catch (err) {
    state.me = null;
    if (err.status !== 401) {
      fill(app, h("div", { class: "login" }, h("div", { class: "login-card" },
        avatar(state.public.avatar, "login-avatar"),
        h("div", { class: "alert" }, icon("alert"), h("div", null, err.message)),
        h("button", { class: "btn btn-primary", onClick: () => boot() }, t("login.retry")))));
      return;
    }
  }
  if (!state.me) {
    renderLogin();
    return;
  }
  realtime.start();
  renderShell();
}

bus.on("session-expired", () => {
  if (!state.me) return;
  state.me = null;
  realtime.stop();
  toast(t("errors.session"), "error");
  renderLogin();
});

bus.on("rt-status", () => {
  if (shell.rt) drawRtStatus();
});

bus.on("player", ({ guildId, data }) => {
  if (!state.me || guildId !== state.guildId) return;
  drawMini();
  const playing = Boolean(data.connected && data.current && !data.paused);
  if (playing !== shell.sidebarPlaying) drawSidebar();
});

setInterval(tickMini, 500);
window.addEventListener("hashchange", onHashChange);
window.addEventListener("beforeunload", (event) => {
  if (leaveGuard && leaveGuard()) {
    event.preventDefault();
    event.returnValue = "";
  }
});

// Espacio = pausar / reanudar cuando no se está escribiendo
document.addEventListener("keydown", (event) => {
  if (event.key !== " " || event.target !== document.body || !state.me || !state.guildId) return;
  const p = getPlayer(state.guildId);
  if (!p || !p.connected || !p.current) return;
  event.preventDefault();
  playerAction(state.guildId, { action: "pause", paused: !p.paused });
});

boot();

