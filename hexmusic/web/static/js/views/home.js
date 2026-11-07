// Inicio: cifras del bot, tus servidores y (dueños) actividad global.
"use strict";

import { fill, api, avatar, card, emptyState, fmt, guildIcon, h, icon, safeUrl, spinner, state, t, tile } from "../core.js";
import { summaryBlocks } from "./history.js";

export function nodesTable(nodes) {
  if (!nodes.length) return emptyState("server", t("stats.no_nodes"), null);
  return h("div", { class: "table-wrap" }, h("table", { class: "table" },
    h("thead", null, h("tr", null, [t("stats.node"), t("stats.status"), t("stats.players"), t("stats.cpu"), t("stats.memory"), t("stats.uptime")]
      .map((label, i) => h("th", { class: i >= 2 ? "num" : null }, label)))),
    h("tbody", null, nodes.map((node) => h("tr", null,
      h("td", { class: "strong" }, node.identifier),
      h("td", null, h("span", { class: "row tight" }, h("span", { class: `dot ${node.online ? "ok" : "off"}` }),
        node.online ? t("stats.online") : t("stats.offline"))),
      h("td", { class: "num" }, node.playing !== undefined ? `${node.playing}/${node.players}` : String(node.players)),
      h("td", { class: "num" }, node.cpu !== undefined ? `${node.cpu}%` : "—"),
      h("td", { class: "num" }, node.memory_used !== undefined ? `${fmt.bytes(node.memory_used)} / ${fmt.bytes(node.memory_allocated)}` : "—"),
      h("td", { class: "num" }, node.uptime !== undefined ? fmt.uptime(node.uptime / 1000) : "—"))))));
}

export async function render(ctx) {
  const { root, scope } = ctx;
  ctx.setTitle(t("home.title"), state.public.name);
  const me = state.me;

  const tilesBox = h("div", { class: "tiles" }, h("div", { class: "loading", style: { minHeight: "90px" } }, spinner()));
  const nodesBox = h("div");
  const activeBox = h("div");
  const globalBox = h("div", { class: "stack" });

  const present = me.guilds.filter((guild) => guild.bot_present);
  const absent = me.guilds.filter((guild) => !guild.bot_present);
  const servers = me.guilds.length
    ? h("div", { class: "grid-auto" },
      present.map((guild) => h("a", { class: "server-card", href: `#/g/${guild.id}/player`, style: { textDecoration: "none" } },
        guildIcon(guild, "lg"),
        h("div", { class: "grow" }, h("div", { class: "strong ellipsis" }, guild.name), h("div", { class: "muted small" }, t("home.manage"))),
        icon("chevronRight"))),
      absent.map((guild) => h("div", { class: "server-card disabled" },
        guildIcon(guild, "lg"),
        h("div", { class: "grow" }, h("div", { class: "strong ellipsis" }, guild.name), h("div", { class: "muted small" }, t("home.not_in_server"))),
        safeUrl(guild.invite_url)
          ? h("a", { class: "btn btn-sm btn-primary", href: guild.invite_url, target: "_blank", rel: "noopener noreferrer" }, icon("plus", "icon-sm"), t("nav.invite"))
          : null)))
    : emptyState("server", t("nav.no_servers"), t("home.no_servers_hint"));

  fill(root, 
    h("div", { class: "home-hero" },
      avatar(me.user.avatar, "avatar lg"),
      h("div", { class: "grow" },
        h("h1", null, t("home.greeting", { name: me.user.name })),
        h("p", { class: "muted" }, me.owner ? t("home.subtitle_owner") : t("home.subtitle"))),
      h("div", { class: "page-actions" },
        safeUrl(state.public.invite_url)
          ? h("a", { class: "btn", href: state.public.invite_url, target: "_blank", rel: "noopener noreferrer" }, icon("plus", "icon-sm"), t("nav.add_bot"))
          : null,
        state.guildId ? h("a", { class: "btn btn-primary", href: `#/g/${state.guildId}/player` }, icon("play", "icon-sm"), t("home.open_player")) : null)),
    tilesBox,
    card({ title: t("home.your_servers"), iconName: "server", sub: String(me.guilds.length) }, servers),
    activeBox,
    globalBox,
    card({ title: t("stats.nodes"), iconName: "activity" }, nodesBox));

  const draw = (data) => {
    fill(tilesBox, 
      tile("server", t("stats.servers"), fmt.number(data.servers)),
      tile("headphones", t("stats.players"), fmt.number(data.players)),
      tile("play", t("stats.playing"), fmt.number(data.playing)),
      tile("clock", t("stats.uptime"), fmt.uptime(data.uptime)),
      tile("activity", t("stats.latency"), data.latency === null ? "—" : `${data.latency} ms`));
    fill(nodesBox, nodesTable(data.nodes),
      h("p", { class: "muted small" },
        `HexMusic ${data.versions.hexmusic} · discord.py ${data.versions.discord} · wavelink ${data.versions.wavelink} · Python ${data.versions.python}`));
    if (data.active) {
      fill(activeBox, card({ title: t("stats.active_players"), iconName: "radio", sub: String(data.active.length) },
        data.active.length
          ? h("div", { class: "list" }, data.active.map((item) => h("a", { class: "list-row", href: `#/g/${item.guild.id}/player`, style: { textDecoration: "none", color: "inherit" } },
            guildIcon(item.guild),
            h("div", { class: "text" },
              h("span", { class: "title" }, item.guild.name),
              h("span", { class: "meta" }, item.track ? `${item.paused ? "⏸" : "▶"} ${item.track.title} — ${item.track.author}` : t("stats.idle"))),
            h("span", { class: "time" }, `${item.channel || "—"} · ${t("player.listeners", { count: item.listeners })}`))))
          : emptyState("radio", t("stats.no_active"), null)));
    }
  };

  const data = await api("GET", "/api/stats");
  if (!scope.alive) return;
  draw(data);
  scope.every(10000, async () => {
    try {
      const fresh = await api("GET", "/api/stats");
      if (scope.alive) draw(fresh);
    } catch {
      /* se reintenta en el siguiente ciclo */
    }
  });

  if (me.owner && me.features.history) {
    try {
      const tz = -new Date().getTimezoneOffset();
      const summary = await api("GET", `/api/stats/history?days=14&tz=${tz}`);
      if (!scope.alive) return;
      const blocks = summaryBlocks(summary, { showGuilds: true });
      fill(globalBox, h("div", { class: "row between" }, h("h2", null, t("home.global_activity")),
        h("span", { class: "muted small" }, t("history.days", { count: 14 }))), blocks.tiles, blocks.chart, blocks.top);
    } catch {
      fill(globalBox);
    }
  }
}
