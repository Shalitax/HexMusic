// Administración (solo dueños del bot): resumen, configuración global, servidores y registros.
"use strict";

import {
  api, card, confirmDialog, emptyState, fail, fill, fmt, guildIcon, h, icon, safeUrl, select, spinner, state, switchControl,
  t, tile, toast, tryT,
} from "../core.js";
import { nodesTable } from "./home.js";

// ───── Resumen ─────

function youtubeCard(scope) {
  const box = card({ title: t("youtube.title"), iconName: "youtube" }, h("div", { class: "loading", style: { minHeight: "80px" } }, spinner()));
  let info = null;

  const act = async (action, confirmText) => {
    if (confirmText && !await confirmDialog({ title: confirmText, danger: true, confirm: t("youtube.unlink") })) return;
    try {
      info = await api("POST", "/api/youtube", { action });
      draw();
    } catch (err) {
      fail(err);
    }
  };

  const draw = () => {
    const children = [];
    if (!info.enabled) {
      children.push(h("p", { class: "muted" }, t("youtube.disabled")));
    } else {
      const tone = info.status === "linked" ? "ok" : info.status === "unverified" ? "warn" : info.status === "linking" ? "accent" : "";
      children.push(h("div", { class: "row" }, h("span", { class: `badge ${tone}` }, t(`youtube.badge_${info.status}`)),
        h("span", { class: "muted small" }, t(`youtube.status_${info.status}`))));
      if (info.code) {
        children.push(h("div", { class: "notice" }, icon("info"), h("div", { class: "stack tight" },
          h("div", null, t("youtube.step_open"), " ",
            h("a", { href: safeUrl(info.code.url) || "#", target: "_blank", rel: "noopener noreferrer" }, info.code.url)),
          h("div", { class: "row wrap" }, t("youtube.step_code"), h("span", { class: "code-box" }, info.code.code)),
          h("div", { class: "muted small" }, t("youtube.step_account")))));
      }
      const buttons = [];
      if (info.linking) buttons.push(h("button", { class: "btn", onClick: () => act("cancel") }, t("youtube.cancel")));
      else buttons.push(h("button", { class: "btn btn-primary", onClick: () => act("link") }, icon("link", "icon-sm"),
        info.status === "linked" ? t("youtube.relink") : t("youtube.link")));
      if (info.status === "linked" || info.status === "unverified") {
        buttons.push(h("button", { class: "btn btn-danger", onClick: () => act("unlink", t("youtube.confirm_unlink")) }, t("youtube.unlink")));
      }
      children.push(h("div", { class: "row wrap" }, buttons));
      if (info.panel_token) children.push(h("p", { class: "muted small" }, t("youtube.panel_token")));
    }
    fill(box, box.firstChild, ...children);
  };

  api("GET", "/api/youtube").then((data) => {
    info = data;
    if (scope.alive) draw();
  }).catch((err) => fill(box, box.firstChild, h("p", { class: "muted" }, err.message)));

  scope.every(4000, async () => {
    if (!info || !info.linking) return;
    try {
      const fresh = await api("GET", "/api/youtube");
      const finished = !fresh.linking;
      info = fresh;
      if (scope.alive) draw();
      if (finished && fresh.status === "linked") toast(t("youtube.linked_toast"), "success");
    } catch {
      /* se reintenta en el siguiente ciclo */
    }
  });
  return box;
}

async function renderOverview(ctx) {
  const { root, scope } = ctx;
  ctx.setTitle(t("admin.overview"), t("nav.admin"));
  fill(root, h("div", { class: "loading" }, spinner()));
  const [data, stats] = await Promise.all([api("GET", "/api/admin/overview"), api("GET", "/api/stats")]);
  if (!scope.alive) return;

  const action = (name, label, iconName, payload = {}, confirmText = null) => h("button", {
    class: "btn",
    onClick: async (event) => {
      if (confirmText && !await confirmDialog({ title: confirmText, confirm: label })) return;
      const button = event.currentTarget;
      button.disabled = true;
      try {
        const result = await api("POST", "/api/admin/actions", { action: name, ...payload });
        toast(t(`admin.done_${name}`, { count: result.count ?? 0, languages: (result.languages || []).join(", ") }), "success");
      } catch (err) {
        fail(err);
      } finally {
        button.disabled = false;
      }
    },
  }, icon(iconName, "icon-sm"), label);

  const kv = (label, value) => h("tr", null, h("td", { class: "muted" }, label), h("td", { class: "strong" }, value));

  fill(root, 
    data.restart_pending.length
      ? h("div", { class: "notice warn" }, icon("alert"), h("div", null, h("div", { class: "strong" }, t("admin.restart_pending")),
        h("div", { class: "small mono" }, data.restart_pending.join(", "))))
      : null,
    h("div", { class: "tiles" },
      tile("server", t("stats.servers"), fmt.number(data.guilds)),
      tile("users", t("admin.members"), fmt.compact(data.members)),
      tile("headphones", t("stats.players"), fmt.number(data.players)),
      tile("play", t("stats.playing"), fmt.number(data.playing), t("admin.listeners", { count: data.listeners })),
      tile("clock", t("stats.uptime"), fmt.uptime(data.uptime)),
      tile("activity", t("stats.latency"), stats.latency === null ? "—" : `${stats.latency} ms`),
      tile("database", t("admin.memory"), data.memory ? fmt.bytes(data.memory) : "—")),
    h("div", { class: "grid-2" },
      card({ title: t("admin.actions"), iconName: "bolt" },
        h("div", { class: "stack tight" },
          h("div", { class: "row wrap" },
            action("sync", t("admin.sync"), "refresh", {}, t("admin.sync_confirm")),
            action("reload_locales", t("admin.reload_locales"), "globe"),
            action("save_sessions", t("admin.save_sessions"), "save"),
            action("purge_history", t("admin.purge_history"), "history")),
          h("p", { class: "muted small" }, t("admin.actions_hint")))),
      card({ title: t("admin.system"), iconName: "server" },
        h("table", { class: "table" }, h("tbody", null,
          kv(t("admin.bot_user"), data.bot.name || "—"),
          kv("HexMusic", data.versions.hexmusic),
          kv("discord.py · wavelink", `${data.versions.discord} · ${data.versions.wavelink}`),
          kv("Python", `${data.versions.python} (${data.versions.platform})`),
          kv(t("admin.shards"), String(data.shards)),
          kv(t("admin.database"), fmt.bytes(data.storage.database)),
          kv(t("admin.library_size"), fmt.bytes(data.storage.library)),
          kv(t("admin.data_dir"), h("span", { class: "mono small" }, data.storage.data_dir)),
          kv(t("admin.panel"), h("span", { class: "small" }, data.web.public_url, " · ", t("admin.realtime_clients", { count: data.web.realtime_clients }))))))),
    h("div", { class: "grid-2" },
      card({ title: t("admin.features"), iconName: "toggle", actions: h("a", { class: "btn btn-sm", href: "#/admin/config" }, icon("settings", "icon-sm"), t("admin.edit_config")) },
        h("div", { class: "chips" }, Object.entries(data.features).map(([name, on]) => h("span", { class: `chip${on ? " on" : ""}` },
          icon(on ? "check" : "x", "icon-sm"), tryT(`cfg.f.features-${name}`) || name)))),
      youtubeCard(scope)),
    card({ title: t("stats.nodes"), iconName: "activity" }, nodesTable(stats.nodes)));
}

// ───── Configuración global ─────

const fieldId = (key) => key.replace(/\./g, "-");

function fieldLabel(key) {
  return tryT(`cfg.f.${fieldId(key)}`) || key;
}

function optionLabel(spec, value) {
  if (spec.key === "bot.default_language") return (state.languages.find((lang) => lang.code === value) || {}).name || value;
  if (spec.key === "bot.status.type") return tryT(`cfg.status.${value}`) || value;
  if (spec.key === "lavalink.default_search") return tryT(`cfg.search.${value}`) || value;
  if (spec.key === "dj.commands") return `/${value}`;
  return String(value);
}

function sameValue(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

async function renderConfig(ctx) {
  const { root, scope } = ctx;
  ctx.setTitle(t("admin.config"), t("nav.admin"));
  fill(root, h("div", { class: "loading" }, spinner()));
  let data = await api("GET", "/api/admin/config");
  if (!scope.alive) return;

  let section = (location.hash.split("?")[1] || "").replace("s=", "") || data.sections[0].id;
  const changes = new Map();
  const resets = new Set();
  const errors = new Map();
  let search = "";

  const navBox = h("nav", { class: "config-nav" });
  const body = h("div", { class: "stack" });
  const savebarBox = h("div");
  const searchInput = h("input", { class: "input sm", type: "search", placeholder: t("admin.config_search"), "aria-label": t("admin.config_search"),
    onInput: () => { search = searchInput.value.trim().toLowerCase(); drawBody(); } });

  const specs = () => data.sections.flatMap((s) => s.fields.map((f) => ({ ...f, section: s.id })));
  const valueOf = (spec) => (changes.has(spec.key) ? changes.get(spec.key) : resets.has(spec.key) ? spec.base : spec.value);

  function setValue(spec, value) {
    resets.delete(spec.key);
    if (sameValue(value, spec.value)) changes.delete(spec.key);
    else changes.set(spec.key, value);
    drawSavebar();
  }

  function control(spec) {
    const value = valueOf(spec);
    const commit = (v) => setValue(spec, v);
    switch (spec.type) {
      case "bool":
        return switchControl(Boolean(value), (v) => commit(v), value ? t("common.on") : t("common.off"));
      case "int":
      case "float": {
        const input = h("input", { class: "input", type: "number", value: value ?? "", min: spec.min ?? null, max: spec.max ?? null,
          step: spec.type === "float" ? "0.05" : "1",
          onInput: (event) => {
            const raw = event.target.value;
            const number = spec.type === "int" ? parseInt(raw, 10) : parseFloat(raw);
            const bad = raw === "" || Number.isNaN(number) || (spec.min !== null && number < spec.min) || (spec.max !== null && number > spec.max);
            input.classList.toggle("invalid", bad);
            if (bad) errors.set(spec.key, true);
            else {
              errors.delete(spec.key);
              commit(number);
            }
            drawSavebar();
          } });
        return input;
      }
      case "color": {
        const text = h("input", { class: "input mono", value: value || "", maxlength: 7 });
        const picker = h("input", { type: "color", value: /^#[0-9a-f]{6}$/i.test(value || "") ? value : "#000000" });
        picker.addEventListener("input", () => { text.value = picker.value.toUpperCase(); text.classList.remove("invalid"); errors.delete(spec.key); commit(picker.value.toUpperCase()); });
        text.addEventListener("input", () => {
          const ok = /^#[0-9a-f]{6}$/i.test(text.value.trim());
          text.classList.toggle("invalid", !ok);
          if (ok) {
            errors.delete(spec.key);
            picker.value = text.value.trim();
            commit(text.value.trim().toUpperCase());
          } else errors.set(spec.key, true);
          drawSavebar();
        });
        return h("div", { class: "color-input" }, picker, text);
      }
      case "select":
        return select(spec.options.map((option) => ({ value: option, label: optionLabel(spec, option) })), value, (v) => commit(v));
      case "multiselect": {
        const chosen = new Set(value || []);
        const box = h("div", { class: "chips" });
        const draw = () => fill(box, ...spec.options.map((option) => h("button", {
          type: "button", class: `chip${chosen.has(option) ? " on" : ""}`, "aria-pressed": chosen.has(option) ? "true" : "false",
          onClick: () => {
            if (chosen.has(option)) chosen.delete(option);
            else chosen.add(option);
            draw();
            commit(spec.options.filter((item) => chosen.has(item)));
          },
        }, chosen.has(option) ? icon("check", "icon-sm") : null, optionLabel(spec, option))));
        draw();
        return box;
      }
      case "json": {
        const area = h("textarea", { class: "textarea", spellcheck: "false", rows: 10 });
        area.value = JSON.stringify(value || {}, null, 2);
        const error = h("span", { class: "field-error", hidden: true });
        area.addEventListener("input", () => {
          try {
            const parsed = JSON.parse(area.value || "{}");
            if (typeof parsed !== "object" || Array.isArray(parsed) || parsed === null) throw new Error(t("admin.json_object"));
            error.hidden = true;
            area.classList.remove("invalid");
            errors.delete(spec.key);
            commit(parsed);
          } catch (err) {
            error.textContent = err.message;
            error.hidden = false;
            errors.set(spec.key, true);
            drawSavebar();
          }
        });
        return h("div", { class: "stack tight" }, area, error);
      }
      default: {
        const input = h("input", { class: "input", type: spec.type === "url" ? "url" : "text", value: value ?? "", maxlength: spec.max_length || 200,
          placeholder: spec.type === "url" ? "https://…" : null,
          onInput: (event) => commit(event.target.value) });
        return input;
      }
    }
  }

  function fieldBlock(spec) {
    const changed = changes.has(spec.key) || resets.has(spec.key);
    const overridden = resets.has(spec.key) ? false : spec.overridden || changes.has(spec.key);
    const hint = tryT(`cfg.h.${fieldId(spec.key)}`);
    const base = spec.type === "json" ? null : spec.type === "bool" ? (spec.base ? t("common.on") : t("common.off"))
      : Array.isArray(spec.base) ? spec.base.map((v) => optionLabel(spec, v)).join(", ") : spec.type === "select" ? optionLabel(spec, spec.base) : String(spec.base ?? "");
    return h("div", { class: `config-field${changed ? " changed" : ""}` },
      h("div", { class: "head" },
        h("span", { class: "strong" }, fieldLabel(spec.key)),
        !spec.live ? h("span", { class: "badge warn", title: t("admin.needs_restart_hint") }, icon("refresh", "icon-sm"), t("admin.needs_restart")) : null,
        overridden ? h("span", { class: "badge accent" }, t("admin.overridden")) : null,
        h("span", { class: "key" }, spec.key)),
      hint ? h("span", { class: "field-hint" }, hint) : null,
      h("div", { class: "control" }, control(spec)),
      h("div", { class: "row wrap small muted" },
        base !== null && base !== "" ? h("span", null, t("admin.base_value", { value: base })) : null,
        spec.overridden && !resets.has(spec.key)
          ? h("button", { class: "btn btn-xs btn-ghost", type: "button", onClick: () => {
            changes.delete(spec.key);
            errors.delete(spec.key);
            resets.add(spec.key);
            drawBody();
            drawSavebar();
          } }, icon("replay", "icon-sm"), t("admin.reset_field"))
          : null,
        changed ? h("button", { class: "btn btn-xs btn-ghost", type: "button", onClick: () => {
          changes.delete(spec.key);
          resets.delete(spec.key);
          errors.delete(spec.key);
          drawBody();
          drawSavebar();
        } }, t("admin.undo")) : null));
  }

  function drawNav() {
    fill(navBox, searchInput, ...data.sections.map((s) => {
      const dirty = s.fields.some((f) => changes.has(f.key) || resets.has(f.key));
      return h("button", { class: `nav-item${s.id === section && !search ? " active" : ""}`, onClick: () => {
        section = s.id;
        search = "";
        searchInput.value = "";
        history.replaceState(null, "", `#/admin/config?s=${s.id}`);
        drawNav();
        drawBody();
      } }, icon(s.icon), tryT(`cfg.sections.${s.id}`) || s.id, dirty ? h("span", { class: "badge accent" }, "•") : null);
    }));
  }

  function drawBody() {
    if (search) {
      const found = specs().filter((spec) => spec.key.toLowerCase().includes(search) || fieldLabel(spec.key).toLowerCase().includes(search));
      fill(body, card({ title: t("admin.config_results", { count: found.length }), iconName: "search" },
        found.length ? h("div", null, found.map(fieldBlock)) : emptyState("search", t("admin.config_no_results"), null)));
      return;
    }
    const current = data.sections.find((s) => s.id === section) || data.sections[0];
    fill(body, card({ title: tryT(`cfg.sections.${current.id}`) || current.id, iconName: current.icon },
      tryT(`cfg.sections_hint.${current.id}`) ? h("p", { class: "muted small" }, t(`cfg.sections_hint.${current.id}`)) : null,
      h("div", null, current.fields.map(fieldBlock))));
  }

  function drawSavebar() {
    drawNav();
    const count = changes.size + resets.size;
    if (!count) {
      fill(savebarBox);
      return;
    }
    const saveBtn = h("button", { class: "btn btn-primary btn-sm", disabled: errors.size > 0, onClick: async () => {
      saveBtn.disabled = true;
      try {
        data = await api("PATCH", "/api/admin/config", { changes: Object.fromEntries(changes), reset: [...resets] });
        changes.clear();
        resets.clear();
        errors.clear();
        toast(t("admin.config_saved"), "success");
        bus_refresh();
        drawBody();
        drawSavebar();
        drawRestart();
      } catch (err) {
        fail(err);
        saveBtn.disabled = false;
      }
    } }, icon("save", "icon-sm"), t("common.save"));
    fill(savebarBox, h("div", { class: "savebar", role: "region", "aria-label": t("admin.unsaved", { count }) },
      h("span", { class: "strong" }, errors.size ? t("admin.fix_errors") : t("admin.unsaved", { count })),
      h("div", { class: "row tight" },
        h("button", { class: "btn btn-sm", onClick: () => { changes.clear(); resets.clear(); errors.clear(); drawBody(); drawSavebar(); } }, t("admin.discard")),
        saveBtn)));
  }

  const restartBox = h("div");
  function drawRestart() {
    fill(restartBox, data.restart_pending.length
      ? h("div", { class: "notice warn" }, icon("alert"), h("div", null, h("div", { class: "strong" }, t("admin.restart_pending")),
        h("div", { class: "small mono" }, data.restart_pending.join(", "))))
      : null);
  }

  // Tras guardar, el nombre, el color o el idioma pueden haber cambiado: se refresca la cabecera
  const bus_refresh = () => ctx.refreshPublic();

  fill(root, 
    h("div", { class: "notice" }, icon("info"), h("div", null, t("admin.config_intro"), " ", h("span", { class: "mono small" }, data.file))),
    restartBox,
    h("div", { class: "config-layout" }, navBox, h("div", { class: "stack" }, body, savebarBox)));
  drawRestart();
  drawNav();
  drawBody();

  ctx.beforeLeave(() => (changes.size + resets.size ? t("admin.leave_unsaved") : null));
}

// ───── Servidores ─────

async function renderGuilds(ctx) {
  const { root, scope } = ctx;
  ctx.setTitle(t("admin.guilds"), t("nav.admin"));
  fill(root, h("div", { class: "loading" }, spinner()));
  let data = await api("GET", "/api/admin/guilds");
  if (!scope.alive) return;

  const filter = h("input", { class: "input sm", type: "search", placeholder: t("admin.guilds_search"), onInput: () => draw() });
  const tableBox = h("div");

  function draw() {
    const text = filter.value.trim().toLowerCase();
    const items = data.guilds.filter((g) => !text || g.name.toLowerCase().includes(text) || g.id.includes(text));
    fill(tableBox, items.length ? h("div", { class: "table-wrap" }, h("table", { class: "table" },
      h("thead", null, h("tr", null, h("th", null, t("admin.server")), h("th", { class: "num" }, t("admin.members")),
        h("th", null, t("admin.joined")), h("th", null, t("admin.player")), h("th", null, ""))),
      h("tbody", null, items.map((g) => h("tr", null,
        h("td", null, h("div", { class: "row" }, guildIcon(g, "sm"), h("div", { class: "text", style: { display: "grid", minWidth: 0 } },
          h("span", { class: "strong ellipsis" }, g.name), h("span", { class: "muted tiny mono" }, g.id)))),
        h("td", { class: "num" }, fmt.number(g.members)),
        h("td", { class: "muted small nowrap" }, g.joined_at ? fmt.date(g.joined_at, false) : "—"),
        h("td", null, g.player
          ? h("div", { class: "row tight small" }, h("span", { class: `dot ${g.player.paused ? "warn" : "ok"}` }),
            h("span", { class: "ellipsis", style: { maxWidth: "260px" } }, g.player.track || t("stats.idle")),
            h("span", { class: "muted" }, `· ${t("player.listeners", { count: g.player.listeners })}`))
          : h("span", { class: "muted small" }, "—")),
        h("td", { class: "num nowrap" },
          h("a", { class: "btn btn-xs", href: `#/g/${g.id}/player` }, t("admin.open")),
          " ",
          h("button", { class: "btn btn-xs btn-danger", onClick: async () => {
            if (!await confirmDialog({ title: t("admin.leave_confirm", { name: g.name }), message: t("admin.leave_hint"), danger: true, confirm: t("admin.leave") })) return;
            try {
              await api("POST", `/api/admin/guilds/${g.id}/leave`);
              toast(t("admin.left", { name: g.name }), "success");
              data = await api("GET", "/api/admin/guilds");
              draw();
            } catch (err) {
              fail(err);
            }
          } }, t("admin.leave")))))))) : emptyState("server", t("admin.guilds_empty"), null));
  }

  fill(root, card({ title: t("admin.guilds"), iconName: "server", sub: String(data.guilds.length),
    actions: h("div", { style: { width: "240px" } }, filter) }, tableBox));
  draw();
}

// ───── Registros ─────

async function renderLogs(ctx) {
  const { root, scope } = ctx;
  ctx.setTitle(t("admin.logs"), t("nav.admin"));
  let last = 0;
  let paused = false;
  let level = "INFO";
  const items = [];
  const box = h("div", { class: "logs", role: "log", "aria-live": "off" });
  const filter = h("input", { class: "input sm", type: "search", placeholder: t("admin.logs_filter"), onInput: () => redraw() });
  const time = new Intl.DateTimeFormat(state.lang, { hour: "2-digit", minute: "2-digit", second: "2-digit" });

  const line = (item) => h("div", { class: `log-line ${item.level}` },
    h("span", { class: "muted" }, time.format(new Date(item.time * 1000))),
    h("span", { class: "lvl" }, item.level),
    h("span", { class: "logger", title: item.logger }, item.logger),
    h("span", null, item.message));

  function matches(item) {
    const text = filter.value.trim().toLowerCase();
    return !text || item.message.toLowerCase().includes(text) || item.logger.toLowerCase().includes(text);
  }

  function redraw() {
    fill(box, ...items.filter(matches).map(line));
    box.scrollTop = box.scrollHeight;
  }

  async function poll(reset) {
    if (paused && !reset) return;
    try {
      const data = await api("GET", `/api/admin/logs?after=${reset ? 0 : last}&level=${level}`);
      if (!scope.alive) return;
      if (reset) items.length = 0;
      const stick = box.scrollTop + box.clientHeight >= box.scrollHeight - 30;
      items.push(...data.items);
      if (items.length > 1500) items.splice(0, items.length - 1500);
      last = data.last;
      if (reset) redraw();
      else {
        const fresh = data.items.filter(matches).map(line);
        box.append(...fresh);
        if (stick) box.scrollTop = box.scrollHeight;
      }
    } catch {
      /* se reintenta */
    }
  }

  const pauseBtn = h("button", { class: "btn btn-sm", onClick: () => {
    paused = !paused;
    fill(pauseBtn, icon(paused ? "play" : "pause", "icon-sm"), paused ? t("admin.logs_resume") : t("admin.logs_pause"));
  } }, icon("pause", "icon-sm"), t("admin.logs_pause"));
  const levelSelect = select(["INFO", "WARNING", "ERROR"].map((value) => ({ value, label: value })), level, (value) => {
    level = value;
    poll(true);
  }, "select sm");

  fill(root, card({ title: t("admin.logs"), iconName: "terminal", actions: [
    h("div", { style: { width: "200px" } }, filter),
    h("div", { style: { width: "120px" } }, levelSelect),
    pauseBtn,
    h("button", { class: "btn btn-sm", onClick: async () => {
      try {
        await navigator.clipboard.writeText(items.filter(matches).map((item) => `${new Date(item.time * 1000).toISOString()} ${item.level} ${item.logger} ${item.message}`).join("\n"));
        toast(t("admin.logs_copied"), "success");
      } catch {
        toast(t("errors.generic"), "error");
      }
    } }, icon("copy", "icon-sm"), t("admin.logs_copy")),
  ] }, box, h("p", { class: "muted small" }, t("admin.logs_hint"))));
  await poll(true);
  scope.every(2000, () => poll(false));
}

export async function render(ctx) {
  const tab = ctx.route.tab;
  if (tab === "config") return renderConfig(ctx);
  if (tab === "guilds") return renderGuilds(ctx);
  if (tab === "logs") return renderLogs(ctx);
  return renderOverview(ctx);
}

