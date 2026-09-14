"use strict";

(() => {
  const app = document.getElementById("app");
  const toastBox = document.getElementById("toasts");
  const LANG_KEY = "hexmusic.lang";

  const state = {
    booted: false,
    renderId: 0,
    public: { name: "HexMusic", color: "#8b5cf6", avatar: null },
    me: null,
    lang: "es",
    languages: [],
    strings: {},
    view: { name: "stats" },
    timers: [],
    player: null,
    playerFetchedAt: 0,
    playerSig: { now: "", queue: "" },
    interacting: false,
    applyPlayer: null,
  };

  // ───── Utilidades ─────

  /** Crea elementos de forma segura (el texto nunca se interpreta como HTML). */
  function h(tag, props, ...children) {
    const el = document.createElement(tag);
    const properties = {};
    for (const [key, value] of Object.entries(props || {})) {
      if (value === null || value === undefined || value === false) continue;
      if (key === "class") el.className = value;
      else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2).toLowerCase(), value);
      else if (key === "value" || key === "checked" || key === "disabled") properties[key] = value;
      else el.setAttribute(key, value === true ? "" : String(value));
    }
    for (const child of children.flat(Infinity)) {
      if (child === null || child === undefined || child === false) continue;
      el.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    Object.assign(el, properties);
    return el;
  }

  function t(key, params) {
    let node = state.strings;
    for (const part of key.split(".")) node = node && typeof node === "object" ? node[part] : undefined;
    if (typeof node !== "string") return key;
    if (!params) return node;
    return node.replace(/\{(\w+)\}/g, (match, name) => (name in params ? String(params[name]) : match));
  }

  const safeUrl = (url) => (typeof url === "string" && /^https?:\/\//i.test(url) ? url : null);

  function duration(ms) {
    const total = Math.max(0, Math.floor((ms || 0) / 1000));
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const seconds = total % 60;
    const pad = (n) => String(n).padStart(2, "0");
    return hours ? `${hours}:${pad(minutes)}:${pad(seconds)}` : `${minutes}:${pad(seconds)}`;
  }

  function uptime(seconds) {
    const total = Math.floor(seconds || 0);
    const days = Math.floor(total / 86400);
    const hours = Math.floor((total % 86400) / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    return [days ? `${days}d` : null, days || hours ? `${hours}h` : null, `${minutes}m`].filter(Boolean).join(" ");
  }

  function toast(message, type = "info") {
    const el = h("div", { class: `toast toast-${type}`, role: "status" }, message);
    toastBox.append(el);
    setTimeout(() => el.classList.add("hide"), 3600);
    setTimeout(() => el.remove(), 4100);
  }

  function every(ms, fn) {
    state.timers.push(setInterval(fn, ms));
  }

  function clearTimers() {
    state.timers.forEach(clearInterval);
    state.timers = [];
  }

  const isCurrent = (token) => token === state.renderId;
  const mainEl = () => document.getElementById("main");

  function setTitle(text) {
    const el = document.getElementById("page-title");
    if (el) el.textContent = text;
    document.title = `${text} · ${state.public.name}`;
  }

  function iconButton(symbol, title, onClick, variants = "", disabled = false) {
    const classes = ["icon-btn", ...variants.split(" ").filter(Boolean).map((v) => `icon-btn-${v}`)].join(" ");
    return h("button", { class: classes, type: "button", title, "aria-label": title, onClick, disabled }, symbol);
  }

  function avatarImg(url, className) {
    return safeUrl(url) ? h("img", { class: className, src: url, alt: "" }) : h("div", { class: `${className} placeholder` }, "🎶");
  }

  function guildIcon(guild, size = "") {
    if (safeUrl(guild.icon)) return h("img", { class: `guild-icon ${size}`, src: guild.icon, alt: "" });
    const initials = guild.name.split(/\s+/).map((word) => word[0] || "").join("").slice(0, 3);
    return h("div", { class: `guild-icon placeholder ${size}` }, initials);
  }

  // ───── API ─────

  async function api(method, path, body) {
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
      throw new Error(t("errors.network"));
    }
    let data = null;
    try {
      data = await response.json();
    } catch {
      data = null;
    }
    if (response.status === 401 && path !== "/api/me" && state.me) {
      state.me = null;
      render();
    }
    if (!response.ok) throw new Error((data && data.error) || t("errors.generic"));
    return data;
  }

  async function loadStrings(lang) {
    const data = await api("GET", `/api/i18n?lang=${encodeURIComponent(lang || "")}`);
    state.lang = data.lang;
    state.languages = data.languages;
    state.strings = data.strings;
    document.documentElement.lang = data.lang;
    try {
      localStorage.setItem(LANG_KEY, data.lang);
    } catch {
      /* sin almacenamiento local */
    }
  }

  // ───── Navegación ─────

  function viewToHash(view) {
    if (view.name === "guild") return `#/guild/${view.id}/${view.tab || "player"}`;
    if (view.name === "playlists") return "#/playlists";
    if (view.name === "playlist") return `#/playlist/${view.id}`;
    return "#/stats";
  }

  function hashToView() {
    const parts = location.hash.replace(/^#\/?/, "").split("/");
    if (parts[0] === "guild" && /^\d+$/.test(parts[1] || "")) {
      return { name: "guild", id: parts[1], tab: parts[2] === "settings" ? "settings" : "player" };
    }
    if (parts[0] === "playlists") return { name: "playlists" };
    if (parts[0] === "playlist" && /^\d+$/.test(parts[1] || "")) return { name: "playlist", id: parts[1] };
    return { name: "stats" };
  }

  function navigate(view) {
    const hash = viewToHash(view);
    if (location.hash === hash) {
      state.view = view;
      renderShell();
    } else {
      location.hash = hash;
    }
  }

  window.addEventListener("hashchange", () => {
    state.view = hashToView();
    if (state.me) renderShell();
  });

  // ───── Render principal ─────

  function render() {
    state.booted = true;
    if (state.me) renderShell();
    else renderLogin();
  }

  function langSelect() {
    return h(
      "select",
      {
        class: "input input-sm",
        "aria-label": t("login.language"),
        value: state.lang,
        onChange: async (event) => {
          await loadStrings(event.target.value);
          render();
        },
      },
      state.languages.map((lang) => h("option", { value: lang.code }, lang.name)),
    );
  }

  function renderLogin() {
    clearTimers();
    state.renderId++;
    document.title = state.public.name;
    const failed = new URLSearchParams(location.search).has("login_error");
    if (failed) history.replaceState(null, "", location.pathname + location.hash);
    app.replaceChildren(
      h("div", { class: "login" },
        h("div", { class: "login-card" },
          avatarImg(state.public.avatar, "login-avatar"),
          h("h1", null, state.public.name),
          h("p", { class: "muted" }, t("login.subtitle")),
          failed ? h("div", { class: "alert" }, t("login.error")) : null,
          h("a", { class: "btn btn-discord", href: "/auth/login" }, t("login.button")),
          h("div", { class: "login-lang" }, langSelect()))),
    );
  }

  function renderShell() {
    const me = state.me;
    const view = state.view;

    const navButton = (name, icon, label) => {
      const active = view.name === name || (name === "playlists" && view.name === "playlist");
      return h("button", { class: `nav-item${active ? " active" : ""}`, onClick: () => navigate({ name }) },
        h("span", { class: "nav-icon" }, icon), label);
    };

    const guildItems = me.guilds.length
      ? me.guilds.map((guild) => (guild.bot_present
        ? h("button", {
          class: `guild-item${view.name === "guild" && view.id === guild.id ? " active" : ""}`,
          onClick: () => navigate({ name: "guild", id: guild.id, tab: "player" }),
        }, guildIcon(guild), h("span", { class: "guild-name" }, guild.name))
        : h("div", { class: "guild-item disabled" }, guildIcon(guild), h("span", { class: "guild-name" }, guild.name),
          safeUrl(guild.invite_url)
            ? h("a", { class: "btn btn-xs", href: guild.invite_url, target: "_blank", rel: "noopener noreferrer" }, t("nav.invite"))
            : null)))
      : h("p", { class: "muted small pad" }, t("nav.no_servers"));

    app.replaceChildren(
      h("div", { class: "layout" },
        h("aside", { class: "sidebar" },
          h("div", { class: "brand" }, avatarImg(state.public.avatar, "brand-avatar"), h("span", null, state.public.name)),
          h("nav", { class: "nav" }, navButton("stats", "📊", t("nav.stats")), navButton("playlists", "📁", t("nav.playlists"))),
          h("div", { class: "nav-title" }, t("nav.servers")),
          h("div", { class: "guild-list" }, guildItems)),
        h("div", { class: "main-area" },
          h("header", { class: "topbar" },
            h("h1", { class: "page-title", id: "page-title" }),
            h("div", { class: "topbar-user" },
              langSelect(),
              me.owner ? h("span", { class: "badge" }, t("nav.owner")) : null,
              avatarImg(me.user.avatar, "avatar"),
              h("span", { class: "username" }, me.user.name),
              h("button", { class: "btn btn-ghost btn-sm", onClick: logout }, t("nav.logout")))),
          h("main", { class: "content", id: "main" }))),
    );
    renderMain();
  }

  function renderMain() {
    clearTimers();
    state.applyPlayer = null;
    state.interacting = false;
    const token = ++state.renderId;
    const main = mainEl();
    main.replaceChildren(h("div", { class: "loading" }, h("div", { class: "spinner" })));

    const view = state.view;
    let task;
    if (view.name === "guild") task = renderGuild(view, token);
    else if (view.name === "playlists") task = renderPlaylists(token);
    else if (view.name === "playlist") task = renderPlaylist(view.id, token);
    else task = renderStats(token);

    task.catch((err) => {
      if (isCurrent(token) && mainEl()) mainEl().replaceChildren(h("div", { class: "alert" }, err.message));
    });
  }

  async function logout() {
    try {
      await api("POST", "/auth/logout");
    } catch {
      /* la sesión ya no existía */
    }
    state.me = null;
    render();
  }

  // ───── Estadísticas ─────

  function statCard(icon, label, value) {
    return h("div", { class: "card" }, h("div", { class: "card-icon" }, icon), h("div", { class: "card-value" }, value),
      h("div", { class: "muted small" }, label));
  }

  function nodesTable(nodes) {
    if (!nodes.length) return h("p", { class: "muted" }, "—");
    const headers = [t("stats.node"), t("stats.status"), t("stats.players"), t("stats.cpu"), t("stats.memory"), t("stats.uptime")];
    return h("div", { class: "table-wrap" },
      h("table", { class: "table" },
        h("thead", null, h("tr", null, headers.map((label) => h("th", null, label)))),
        h("tbody", null, nodes.map((node) => h("tr", null,
          h("td", null, node.identifier),
          h("td", null, h("span", { class: `status ${node.online ? "ok" : "off"}` }, node.online ? t("stats.online") : t("stats.offline"))),
          h("td", null, node.playing !== undefined ? `${node.playing}/${node.players}` : String(node.players)),
          h("td", null, node.cpu !== undefined ? `${node.cpu}%` : "—"),
          h("td", null, node.memory_used !== undefined
            ? `${Math.round(node.memory_used / 1048576)} / ${Math.round(node.memory_allocated / 1048576)} MB` : "—"),
          h("td", null, node.uptime !== undefined ? uptime(node.uptime / 1000) : "—"))))));
  }

  function activeList(active) {
    if (!active.length) return h("p", { class: "muted" }, t("stats.no_active"));
    return h("div", { class: "active-list" }, active.map((item) => h("button", {
      class: "active-item",
      onClick: () => navigate({ name: "guild", id: item.guild.id, tab: "player" }),
    },
    guildIcon(item.guild),
    h("div", { class: "grow left" },
      h("div", { class: "strong" }, item.guild.name),
      h("div", { class: "muted small" }, item.track
        ? `${item.paused ? "⏸" : "▶"} ${item.track.title} — ${item.track.author}`
        : t("stats.idle"))),
    h("span", { class: "muted small" }, `🔊 ${item.channel || "—"} · ${t("stats.listeners", { count: item.listeners })}`))));
  }

  async function renderStats(token) {
    setTitle(t("stats.title"));
    const container = h("div", { class: "stack" });
    const draw = (data) => {
      container.replaceChildren(
        h("div", { class: "cards" },
          statCard("🖥️", t("stats.servers"), data.servers),
          statCard("🎧", t("stats.players"), data.players),
          statCard("▶️", t("stats.playing"), data.playing),
          statCard("⏱️", t("stats.uptime"), uptime(data.uptime)),
          statCard("📶", t("stats.latency"), data.latency === null ? "—" : `${data.latency} ms`)),
        h("section", { class: "panel" }, h("h2", null, t("stats.nodes")), nodesTable(data.nodes)),
        data.active ? h("section", { class: "panel" }, h("h2", null, t("stats.active_players")), activeList(data.active)) : null,
        h("p", { class: "muted small" },
          `HexMusic ${data.versions.hexmusic} · discord.py ${data.versions.discord} · wavelink ${data.versions.wavelink} · Python ${data.versions.python}`),
      );
    };

    const data = await api("GET", "/api/stats");
    if (!isCurrent(token)) return;
    draw(data);
    mainEl().replaceChildren(container);
    every(10000, async () => {
      try {
        const fresh = await api("GET", "/api/stats");
        if (isCurrent(token)) draw(fresh);
      } catch {
        /* se reintenta en el siguiente ciclo */
      }
    });
  }

  // ───── Servidor ─────

  async function renderGuild(view, token) {
    const guild = await api("GET", `/api/guilds/${view.id}`);
    if (!isCurrent(token)) return;
    setTitle(guild.name);

    const tab = (name, label) => h("button", {
      class: `tab${view.tab === name ? " active" : ""}`,
      onClick: () => navigate({ ...view, tab: name }),
    }, label);

    const body = h("div", { class: "stack" });
    mainEl().replaceChildren(
      h("div", { class: "guild-header" }, guildIcon(guild, "lg"), h("h1", null, guild.name)),
      h("div", { class: "tabs" }, tab("player", `🎵 ${t("player.tab")}`), tab("settings", `⚙️ ${t("settings.tab")}`)),
      body,
    );

    if (view.tab === "settings") renderSettings(guild, body);
    else await renderPlayer(guild, body, token);
  }

  // ───── Reproductor ─────

  async function playerAction(guild, payload, successMessage) {
    try {
      const data = await api("POST", `/api/guilds/${guild.id}/player`, payload);
      state.interacting = false;
      if (state.applyPlayer) state.applyPlayer(data, true);
      if (successMessage) toast(successMessage, "success");
      return true;
    } catch (err) {
      state.interacting = false;
      toast(err.message, "error");
      return false;
    }
  }

  async function renderPlayer(guild, body, token) {
    const now = h("section", { class: "panel" });
    const add = h("section", { class: "panel" });
    const queue = h("section", { class: "panel" });
    body.replaceChildren(h("div", { class: "player-grid" }, h("div", { class: "stack" }, now, add), queue));

    state.player = null;
    state.playerSig = { now: "", queue: "" };

    const apply = (data, force = false) => {
      const previous = state.player;
      state.player = data;
      state.playerFetchedAt = Date.now();

      const current = data.current || {};
      const nowSig = JSON.stringify([data.connected, current.title, current.uri, data.paused, data.volume, data.loop,
        data.autoplay, data.filter, data.listeners, data.channel && data.channel.id, data.stay_247]);
      const queueSig = JSON.stringify([data.connected, data.queue_length, (data.queue || []).map((track) => `${track.uri}|${track.title}`)]);

      if ((force || nowSig !== state.playerSig.now) && !state.interacting) {
        drawNow(now, guild);
        state.playerSig.now = nowSig;
      }
      if (force || queueSig !== state.playerSig.queue) {
        drawQueue(queue, guild);
        state.playerSig.queue = queueSig;
      }
      if (!previous || previous.connected !== data.connected) drawAdd(add, guild);
    };
    state.applyPlayer = apply;

    const refresh = async () => {
      try {
        const data = await api("GET", `/api/guilds/${guild.id}/player`);
        if (isCurrent(token)) apply(data);
      } catch {
        /* se mantiene el último estado */
      }
    };

    const data = await api("GET", `/api/guilds/${guild.id}/player`);
    if (!isCurrent(token)) return;
    apply(data, true);
    every(2500, refresh);
    every(500, tickProgress);
  }

  function tickProgress() {
    const p = state.player;
    if (!p || !p.connected || !p.current || p.current.is_stream || p.paused || state.interacting) return;
    const position = Math.min(p.current.length, p.position + (Date.now() - state.playerFetchedAt));
    const bar = document.getElementById("progress");
    const label = document.getElementById("time-pos");
    if (bar) bar.value = position;
    if (label) label.textContent = duration(position);
  }

  function channelSelect(guild) {
    return h("select", { class: "input" },
      h("option", { value: "" }, t("player.choose_channel")),
      guild.voice_channels.map((channel) => h("option", { value: channel.id },
        `🔊 ${channel.name}${channel.members ? ` (${channel.members})` : ""}`)));
  }

  const holdRedraw = () => {
    state.interacting = true;
  };
  const releaseRedraw = () => setTimeout(() => {
    state.interacting = false;
  }, 400);

  function drawNow(container, guild) {
    const p = state.player;

    if (!p.connected) {
      const select = channelSelect(guild);
      container.replaceChildren(
        h("div", { class: "empty" },
          h("div", { class: "empty-icon" }, "🔇"),
          h("h2", null, t("player.not_connected")),
          h("p", { class: "muted" }, t("player.not_connected_hint")),
          h("div", { class: "row wrap" }, select,
            h("button", {
              class: "btn btn-primary",
              onClick: () => {
                if (!select.value) return toast(t("player.choose_channel"), "error");
                return playerAction(guild, { action: "join", channel_id: select.value });
              },
            }, t("player.join")))),
      );
      return;
    }

    const track = p.current;
    const cover = track && safeUrl(track.artwork)
      ? h("img", { class: "cover", src: track.artwork, alt: "" })
      : h("div", { class: "cover cover-empty" }, "🎵");

    let info;
    if (track) {
      const source = (guild.sources.find((s) => s.value === track.source) || {}).label || track.source;
      const requester = track.requester
        ? t("player.requested_by", { name: track.requester.name || track.requester.id })
        : (track.recommended ? t("player.autoplay_track") : "");
      info = h("div", { class: "track-info" },
        h("div", { class: "eyebrow" }, `${p.paused ? t("player.paused") : t("player.now_playing")} · ${source}`),
        safeUrl(track.uri)
          ? h("a", { class: "track-title", href: track.uri, target: "_blank", rel: "noopener noreferrer" }, track.title)
          : h("div", { class: "track-title" }, track.title),
        h("div", { class: "muted" }, track.author),
        requester ? h("div", { class: "muted small" }, requester) : null);
    } else {
      info = h("div", { class: "track-info" },
        h("div", { class: "track-title" }, t("player.nothing_playing")),
        h("div", { class: "muted" }, t("player.nothing_playing_hint")));
    }

    let progress = null;
    if (track && !track.is_stream) {
      progress = h("div", { class: "progress-wrap" },
        h("span", { class: "time muted small", id: "time-pos" }, duration(p.position)),
        h("input", {
          type: "range", class: "progress", id: "progress", min: 0, max: track.length, step: 1000, value: p.position,
          "aria-label": t("player.seek"),
          onPointerdown: holdRedraw,
          onPointerup: releaseRedraw,
          onChange: (event) => playerAction(guild, { action: "seek", position: Number(event.target.value) }),
        }),
        h("span", { class: "time muted small" }, duration(track.length)));
    } else if (track) {
      progress = h("div", { class: "live" }, `🔴 ${t("player.live")}`);
    }

    const controls = h("div", { class: "controls" },
      iconButton("⏮", t("player.previous"), () => playerAction(guild, { action: "previous" })),
      iconButton(p.paused ? "▶" : "⏸", p.paused ? t("player.resume") : t("player.pause"),
        () => playerAction(guild, { action: "pause", paused: !p.paused }), "primary", !track),
      iconButton("⏭", t("player.skip"), () => playerAction(guild, { action: "skip" }), "", !track),
      iconButton("⏹", t("player.stop"), () => {
        if (window.confirm(t("player.confirm_stop"))) playerAction(guild, { action: "stop" });
      }));

    const volumeLabel = h("span", { class: "muted small time" }, `${p.volume}%`);
    const volume = h("div", { class: "field" },
      h("span", { class: "field-label" }, `🔊 ${t("player.volume")}`),
      h("div", { class: "volume-row" },
        h("input", {
          type: "range", min: 0, max: guild.max_volume, value: p.volume, "aria-label": t("player.volume"),
          onPointerdown: holdRedraw,
          onPointerup: releaseRedraw,
          onInput: (event) => {
            volumeLabel.textContent = `${event.target.value}%`;
          },
          onChange: (event) => playerAction(guild, { action: "volume", value: Number(event.target.value) }),
        }),
        volumeLabel));

    const selectField = (label, select) => h("label", { class: "field" }, h("span", { class: "field-label" }, label), select);

    const loop = h("select", {
      class: "input", value: p.loop, onFocus: holdRedraw, onBlur: releaseRedraw,
      onChange: (event) => playerAction(guild, { action: "loop", mode: event.target.value }),
    },
    h("option", { value: "off" }, t("player.loop_off")),
    h("option", { value: "track" }, t("player.loop_track")),
    h("option", { value: "queue" }, t("player.loop_queue")));

    const filterOptions = [h("option", { value: "" }, t("player.no_filter")), guild.presets.map((name) => h("option", { value: name }, name))];
    if (p.filter && !guild.presets.includes(p.filter)) filterOptions.push(h("option", { value: p.filter }, t("player.custom_filter")));
    const filter = h("select", {
      class: "input", value: p.filter || "", onFocus: holdRedraw, onBlur: releaseRedraw,
      onChange: (event) => playerAction(guild, { action: "filter", preset: event.target.value || null }),
    }, filterOptions);

    const autoplay = guild.features.autoplay
      ? h("label", { class: "field" }, h("span", { class: "field-label" }, `♾️ ${t("player.autoplay")}`),
        h("span", { class: "check" },
          h("input", {
            type: "checkbox", checked: p.autoplay,
            onChange: (event) => playerAction(guild, { action: "autoplay", enabled: event.target.checked }),
          }),
          p.autoplay ? t("settings.on") : t("settings.off")))
      : null;

    container.replaceChildren(
      h("div", { class: "now-top" }, cover, info),
      progress,
      controls,
      h("div", { class: "options" }, volume, selectField(`🔁 ${t("player.loop")}`, loop), selectField(`🎛️ ${t("player.filter")}`, filter), autoplay),
      h("div", { class: "now-footer" },
        h("span", { class: "muted small" },
          `🔊 ${p.channel ? p.channel.name : "—"} · ${t("player.listeners", { count: p.listeners })}${p.stay_247 ? " · 24/7" : ""}`),
        h("button", {
          class: "btn btn-ghost btn-sm btn-danger",
          onClick: () => {
            if (window.confirm(t("player.confirm_leave"))) playerAction(guild, { action: "leave" });
          },
        }, t("player.leave"))),
    );
  }

  function drawAdd(container, guild) {
    const p = state.player;
    const input = h("input", { class: "input grow", type: "text", maxlength: 500, placeholder: t("player.add_placeholder") });
    const source = h("select", { class: "input" },
      h("option", { value: "" }, t("player.source_default")),
      guild.sources.map((item) => h("option", { value: item.value }, item.label)));
    const next = h("input", { type: "checkbox" });
    const channel = p.connected ? null : channelSelect(guild);
    const button = h("button", { class: "btn btn-primary", type: "submit" }, t("player.add_button"));

    const form = h("form", {
      class: "add-form",
      onSubmit: async (event) => {
        event.preventDefault();
        const query = input.value.trim();
        if (!query) return;
        button.disabled = true;
        const ok = await playerAction(guild, {
          action: "play",
          query,
          source: source.value || null,
          next: next.checked,
          channel_id: channel ? channel.value || null : null,
        }, t("player.added"));
        button.disabled = false;
        if (ok) input.value = "";
      },
    },
    h("div", { class: "row" }, input, button),
    h("div", { class: "row wrap" }, source, channel, h("label", { class: "check" }, next, t("player.play_next"))));

    container.replaceChildren(h("h2", null, `➕ ${t("player.add_title")}`), form);
  }

  function drawQueue(container, guild) {
    const p = state.player;
    const hasQueue = p.connected && p.queue_length > 0;

    const header = h("div", { class: "panel-header" },
      h("h2", null, `📜 ${t("player.queue")}`,
        hasQueue ? h("span", { class: "muted small" }, ` · ${t("player.queue_info", { count: p.queue_length, duration: duration(p.queue_duration) })}`) : null),
      hasQueue
        ? h("div", { class: "row" },
          h("button", { class: "btn btn-sm", onClick: () => playerAction(guild, { action: "shuffle" }) }, `🔀 ${t("player.shuffle")}`),
          h("button", {
            class: "btn btn-sm btn-danger",
            onClick: () => {
              if (window.confirm(t("player.confirm_clear"))) playerAction(guild, { action: "clear" });
            },
          }, t("player.clear")))
        : null);

    if (!hasQueue) {
      container.replaceChildren(header, h("p", { class: "muted" }, t("player.queue_empty")));
      return;
    }

    const list = h("ol", { class: "queue" }, p.queue.map((track, i) => {
      const index = i + 1;
      return h("li", { class: "queue-item" },
        h("span", { class: "queue-index" }, index),
        safeUrl(track.artwork) ? h("img", { class: "thumb", src: track.artwork, alt: "", loading: "lazy" }) : h("div", { class: "thumb" }),
        h("div", { class: "queue-text" },
          safeUrl(track.uri)
            ? h("a", { class: "queue-title", href: track.uri, target: "_blank", rel: "noopener noreferrer" }, track.title)
            : h("span", { class: "queue-title" }, track.title),
          h("span", { class: "muted small" }, track.author, track.requester && track.requester.name ? ` · ${track.requester.name}` : "")),
        h("span", { class: "muted small time" }, track.is_stream ? t("player.live") : duration(track.length)),
        h("div", { class: "queue-actions" },
          iconButton("▶", t("player.skip_to"), () => playerAction(guild, { action: "skipto", index }), "sm"),
          iconButton("↑", t("player.move_up"), () => playerAction(guild, { action: "move", from: index, to: index - 1 }), "sm", index === 1),
          iconButton("↓", t("player.move_down"), () => playerAction(guild, { action: "move", from: index, to: index + 1 }), "sm", index === p.queue_length),
          iconButton("✕", t("player.remove"), () => playerAction(guild, { action: "remove", index }), "sm danger")));
    }));

    container.replaceChildren(header, list,
      p.queue_length > p.queue.length ? h("p", { class: "muted small" }, t("player.queue_more", { count: p.queue_length - p.queue.length })) : null);
  }

  // ───── Ajustes ─────

  function renderSettings(guild, body) {
    const s = guild.settings;
    const d = guild.defaults;
    const onOff = (value) => (value ? t("settings.on") : t("settings.off"));
    const languageName = (code) => (guild.languages.find((lang) => lang.code === code) || {}).name || code;

    const field = (label, control, hint) => h("label", { class: "field" },
      h("span", { class: "field-label" }, label), control, hint ? h("small", { class: "muted" }, hint) : null);
    const checkField = (label, control, hint) => h("label", { class: "check-field" }, control,
      h("span", { class: "field" }, h("span", null, label), hint ? h("small", { class: "muted" }, hint) : null));
    const triSelect = (value, fallback) => h("select", { class: "input", value: value === null ? "" : String(value) },
      h("option", { value: "" }, t("settings.default_option", { value: onOff(fallback) })),
      h("option", { value: "true" }, t("settings.on")),
      h("option", { value: "false" }, t("settings.off")));

    const language = h("select", { class: "input", value: s.language || "" },
      h("option", { value: "" }, t("settings.default_option", { value: languageName(d.language) })),
      guild.languages.map((lang) => h("option", { value: lang.code }, lang.name)));
    const prefix = h("input", { class: "input", maxlength: 10, placeholder: d.prefix, value: s.prefix || "" });
    const djRole = h("select", { class: "input", value: s.dj_role_id || "" },
      h("option", { value: "" }, t("settings.no_role")),
      guild.roles.map((role) => h("option", { value: role.id }, `@${role.name}`)));
    const volume = h("input", {
      class: "input", type: "number", min: 0, max: guild.max_volume, placeholder: String(d.default_volume),
      value: s.default_volume === null ? "" : s.default_volume,
    });
    const voteSkip = triSelect(s.vote_skip, d.vote_skip);
    const announce = triSelect(s.announce, d.announce);
    const autoplay = h("input", { type: "checkbox", checked: s.autoplay });
    const stay = h("input", { type: "checkbox", checked: s.stay_247 });

    const requestChannel = guild.text_channels.find((channel) => channel.id === s.request_channel_id);
    const save = h("button", { class: "btn btn-primary", type: "submit" }, t("settings.save"));

    const form = h("form", {
      class: "panel",
      onSubmit: async (event) => {
        event.preventDefault();
        const tri = (select) => (select.value === "" ? null : select.value === "true");
        const payload = {
          language: language.value || null,
          prefix: prefix.value.trim() || null,
          dj_role_id: djRole.value || null,
          default_volume: volume.value === "" ? null : Number(volume.value),
          announce: tri(announce),
        };
        if (guild.features.vote_skip) payload.vote_skip = tri(voteSkip);
        if (guild.features.autoplay) payload.autoplay = autoplay.checked;
        if (guild.features.stay_247) payload.stay_247 = stay.checked;

        save.disabled = true;
        try {
          const updated = await api("PATCH", `/api/guilds/${guild.id}/settings`, payload);
          Object.assign(guild, updated);
          toast(t("settings.saved"), "success");
        } catch (err) {
          toast(err.message, "error");
        } finally {
          save.disabled = false;
          renderSettings(guild, body);
        }
      },
    },
    h("div", { class: "settings-grid" },
      field(`🌍 ${t("settings.language")}`, language),
      field(`⌨️ ${t("settings.prefix")}`, prefix, t("settings.prefix_hint")),
      field(`🎧 ${t("settings.dj_role")}`, djRole, t("settings.dj_role_hint")),
      field(`🔊 ${t("settings.default_volume")}`, volume, t("settings.volume_hint", { max: guild.max_volume })),
      guild.features.vote_skip ? field(`🗳️ ${t("settings.vote_skip")}`, voteSkip) : null,
      field(`📣 ${t("settings.announce")}`, announce)),
    h("div", { class: "settings-grid" },
      guild.features.autoplay ? checkField(`♾️ ${t("settings.autoplay")}`, autoplay, t("settings.autoplay_hint")) : null,
      guild.features.stay_247 ? checkField(`🕒 ${t("settings.stay_247")}`, stay, t("settings.stay_247_hint")) : null),
    guild.features.request_channel
      ? field(`📨 ${t("settings.request_channel")}`,
        h("div", { class: "input" }, requestChannel ? `#${requestChannel.name}` : t("settings.none")),
        t("settings.request_channel_hint"))
      : null,
    h("div", { class: "row end" }, save));

    body.replaceChildren(form);
  }

  // ───── Playlists ─────

  async function renderPlaylists(token) {
    setTitle(t("playlists.title"));
    const data = await api("GET", "/api/playlists");
    if (!isCurrent(token)) return;

    const input = h("input", { class: "input grow", maxlength: 32, placeholder: t("playlists.create_placeholder") });
    const form = h("form", {
      class: "row",
      onSubmit: async (event) => {
        event.preventDefault();
        const name = input.value.trim();
        if (!name) return;
        try {
          await api("POST", "/api/playlists", { name });
          toast(t("playlists.created"), "success");
          renderMain();
        } catch (err) {
          toast(err.message, "error");
        }
      },
    }, input, h("button", { class: "btn btn-primary", type: "submit" }, t("playlists.create")));

    const list = data.playlists.length
      ? h("div", { class: "playlist-grid" }, data.playlists.map((playlist) => h("div", { class: "playlist-card" },
        h("div", { class: "playlist-icon" }, "📁"),
        h("div", { class: "grow" },
          h("div", { class: "playlist-name" }, playlist.name),
          h("div", { class: "muted small" }, t("playlists.tracks", { count: playlist.tracks }))),
        h("button", { class: "btn btn-sm", onClick: () => navigate({ name: "playlist", id: String(playlist.id) }) }, t("playlists.open")))))
      : h("p", { class: "muted" }, t("playlists.empty"));

    mainEl().replaceChildren(
      h("section", { class: "panel" },
        h("h2", null, t("playlists.new")),
        form,
        h("p", { class: "muted small" }, t("playlists.limits", { playlists: data.limits.max_playlists, tracks: data.limits.max_tracks }))),
      h("section", { class: "panel" }, list),
    );
  }

  async function renderPlaylist(id, token) {
    const data = await api("GET", `/api/playlists/${id}`);
    if (!isCurrent(token)) return;
    setTitle(data.name);

    const nameInput = h("input", { class: "input grow", maxlength: 32, value: data.name });
    const rename = h("form", {
      class: "row",
      onSubmit: async (event) => {
        event.preventDefault();
        try {
          await api("PATCH", `/api/playlists/${id}`, { name: nameInput.value.trim() });
          toast(t("playlists.renamed"), "success");
          renderMain();
        } catch (err) {
          toast(err.message, "error");
        }
      },
    }, nameInput, h("button", { class: "btn", type: "submit" }, t("playlists.rename")));

    const guilds = state.me.guilds.filter((guild) => guild.bot_present);
    const guildSelect = h("select", { class: "input" },
      h("option", { value: "" }, t("playlists.choose_server")),
      guilds.map((guild) => h("option", { value: guild.id }, guild.name)));
    const shuffle = h("input", { type: "checkbox" });
    const play = h("form", {
      class: "row wrap",
      onSubmit: async (event) => {
        event.preventDefault();
        if (!guildSelect.value) return toast(t("playlists.choose_server"), "error");
        try {
          const result = await api("POST", `/api/playlists/${id}/play`, { guild_id: guildSelect.value, shuffle: shuffle.checked });
          toast(t("playlists.playing", { count: result.added }), "success");
        } catch (err) {
          toast(err.message, "error");
        }
        return undefined;
      },
    },
    guildSelect,
    h("label", { class: "check" }, shuffle, t("playlists.shuffle")),
    h("button", { class: "btn btn-primary", type: "submit", disabled: !data.tracks.length }, `▶ ${t("playlists.play")}`));

    const remove = h("button", {
      class: "btn btn-danger",
      onClick: async () => {
        if (!window.confirm(t("playlists.confirm_delete", { name: data.name }))) return;
        try {
          await api("DELETE", `/api/playlists/${id}`);
          toast(t("playlists.deleted"), "success");
          navigate({ name: "playlists" });
        } catch (err) {
          toast(err.message, "error");
        }
      },
    }, t("playlists.delete"));

    const tracks = data.tracks.length
      ? h("ol", { class: "queue" }, data.tracks.map((track) => h("li", { class: "queue-item" },
        h("span", { class: "queue-index" }, track.index),
        h("div", { class: "queue-text" },
          safeUrl(track.uri)
            ? h("a", { class: "queue-title", href: track.uri, target: "_blank", rel: "noopener noreferrer" }, track.title)
            : h("span", { class: "queue-title" }, track.title),
          h("span", { class: "muted small" }, track.author || "")),
        h("span", { class: "muted small time" }, duration(track.length)),
        h("div", { class: "queue-actions" },
          iconButton("✕", t("playlists.remove"), async () => {
            try {
              await api("DELETE", `/api/playlists/${id}/tracks/${track.index}`);
              renderMain();
            } catch (err) {
              toast(err.message, "error");
            }
          }, "sm danger")))))
      : h("p", { class: "muted" }, t("playlists.empty_tracks"));

    mainEl().replaceChildren(
      h("div", null, h("button", { class: "btn btn-ghost btn-sm", onClick: () => navigate({ name: "playlists" }) }, `← ${t("playlists.back")}`)),
      h("section", { class: "panel" }, h("h2", null, t("playlists.manage")), rename, play, h("div", { class: "row end" }, remove)),
      h("section", { class: "panel" },
        h("h2", null, t("playlists.tracks", { count: data.tracks.length })),
        tracks,
        h("p", { class: "muted small" }, t("playlists.add_hint"))),
    );
  }

  // ───── Arranque ─────

  async function boot() {
    let saved = null;
    try {
      saved = localStorage.getItem(LANG_KEY);
    } catch {
      saved = null;
    }
    try {
      state.public = await api("GET", "/api/public");
      document.documentElement.style.setProperty("--accent", state.public.color);
      await loadStrings(saved || (navigator.language || "").split("-")[0]);
    } catch (err) {
      app.replaceChildren(h("div", { class: "login" }, h("div", { class: "login-card" }, h("p", null, err.message))));
      return;
    }
    try {
      state.me = await api("GET", "/api/me");
    } catch {
      state.me = null;
    }
    state.view = hashToView();
    render();
  }

  boot();
})();
