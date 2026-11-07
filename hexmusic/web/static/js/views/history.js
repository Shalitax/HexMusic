// Historial de reproducción y estadísticas de un servidor.
"use strict";

import {
  api, avatar, card, confirmDialog, cover, emptyState, fail, fill, fmt, h, icon, iconButton, meter, safeUrl, segmented, spinner,
  store, t, tile, toast,
} from "../core.js";
import { barChart, chartTable, fillDays } from "../chart.js";
import { playerAction } from "../realtime.js";

export function summaryBlocks(summary, { onReplay, showGuilds = false } = {}) {
  const points = fillDays(summary.daily, summary.days);
  let asTable = false;
  const chartBox = h("div");
  const drawChart = () => fill(chartBox, asTable ? chartTable(points, t("history.plays")) : barChart(points, { valueLabel: t("history.plays") }));
  drawChart();
  const toggle = h("button", { class: "btn btn-xs btn-ghost", onClick: () => {
    asTable = !asTable;
    toggle.lastChild.textContent = asTable ? t("history.show_chart") : t("history.show_table");
    drawChart();
  } }, icon("list", "icon-sm"), h("span", null, t("history.show_table")));

  const tiles = h("div", { class: "tiles" },
    tile("play", t("history.plays"), fmt.number(summary.plays)),
    tile("clock", t("history.listened"), fmt.long(summary.listened_ms)),
    tile("disc", t("history.unique_tracks"), fmt.number(summary.unique_tracks)),
    tile("users", t("history.listeners"), fmt.number(summary.listeners)),
    showGuilds ? tile("server", t("history.servers"), fmt.number(summary.guilds)) : null);

  const topMax = Math.max(1, ...summary.top_tracks.map((item) => item.plays));
  const topTracks = summary.top_tracks.length
    ? h("ol", { class: "list", style: { margin: 0, padding: 0 } }, summary.top_tracks.map((item, i) => h("li", { class: "list-row" },
      h("span", { class: "rank" }, i + 1),
      cover(item.artwork),
      h("div", { class: "text" },
        safeUrl(item.uri)
          ? h("a", { class: "title", href: item.uri, target: "_blank", rel: "noopener noreferrer" }, item.title)
          : h("span", { class: "title" }, item.title),
        h("span", { class: "meta" }, item.author || ""),
        h("div", { style: { marginTop: "5px", maxWidth: "260px" } }, meter(item.plays / topMax, "", false))),
      h("span", { class: "time" }, t("history.times", { count: item.plays })),
      onReplay && safeUrl(item.uri)
        ? h("div", { class: "actions" }, iconButton("plus", t("player.add_again"), () => onReplay(item.uri), "sm"))
        : null)))
    : emptyState("chart", t("history.no_data"), null);

  const userMax = Math.max(1, ...summary.top_users.map((item) => item.plays));
  const topUsers = summary.top_users.length
    ? h("ol", { class: "list", style: { margin: 0, padding: 0 } }, summary.top_users.map((item, i) => h("li", { class: "list-row" },
      h("span", { class: "rank" }, i + 1),
      avatar(item.avatar, "avatar"),
      h("div", { class: "text" }, h("span", { class: "title" }, item.name || t("history.unknown_user", { id: item.id || "?" })),
        h("div", { style: { marginTop: "5px", maxWidth: "220px" } }, meter(item.plays / userMax, "", false))),
      h("span", { class: "time" }, t("history.times", { count: item.plays })))))
    : emptyState("users", t("history.no_data"), null);

  return {
    tiles,
    chart: card({ title: t("history.per_day"), iconName: "chart", actions: toggle }, chartBox),
    top: h("div", { class: "grid-2" },
      card({ title: t("history.top_tracks"), iconName: "music" }, topTracks),
      card({ title: t("history.top_listeners"), iconName: "users" }, topUsers)),
  };
}

export async function render(ctx) {
  const { root, guild, scope } = ctx;
  const gid = guild.id;
  ctx.setTitle(t("history.title"), guild.name);

  let days = Number(store.get("history.days", 30)) || 30;
  const tz = -new Date().getTimezoneOffset();
  const summaryBox = h("div", { class: "stack" }, h("div", { class: "loading" }, spinner()));
  const recentList = h("ol", { class: "list", style: { margin: 0, padding: 0 } });
  const more = h("button", { class: "btn btn-sm", hidden: true, onClick: () => loadRecent(false) }, t("history.load_more"));
  let lastId = null;
  let lastUri = null;

  const replay = (uri) => playerAction(gid, { action: "play", query: uri }, t("player.added"));

  async function loadSummary() {
    try {
      const summary = await api("GET", `/api/guilds/${gid}/history/summary?days=${days}&tz=${tz}`);
      if (!scope.alive) return;
      const blocks = summaryBlocks(summary, { onReplay: replay });
      fill(summaryBox, blocks.tiles, blocks.chart, blocks.top);
    } catch (err) {
      fill(summaryBox, card({}, emptyState("alert", err.message, null)));
    }
  }

  async function loadRecent(reset) {
    try {
      const query = reset || !lastId ? "" : `&before=${lastId}`;
      const data = await api("GET", `/api/guilds/${gid}/history?limit=40${query}`);
      if (!scope.alive) return;
      const rows = data.items.map((item) => h("li", { class: "list-row" },
        cover(item.artwork),
        h("div", { class: "text" },
          safeUrl(item.uri)
            ? h("a", { class: "title", href: item.uri, target: "_blank", rel: "noopener noreferrer" }, item.title)
            : h("span", { class: "title" }, item.title),
          h("span", { class: "meta" }, [item.author, item.autoplay ? t("player.autoplay_track") : item.requester && item.requester.name]
            .filter(Boolean).join(" · "))),
        h("span", { class: "time hide-sm", title: fmt.date(item.played_at) }, fmt.relative(item.played_at)),
        safeUrl(item.uri) ? h("div", { class: "actions" }, iconButton("plus", t("player.add_again"), () => replay(item.uri), "sm")) : null));
      if (reset) fill(recentList, ...rows);
      else recentList.append(...rows);
      if (data.items.length) lastId = data.items[data.items.length - 1].id;
      more.hidden = !data.more;
      if (reset && !data.items.length) {
        fill(recentList, h("li", null, emptyState("history", data.enabled ? t("history.empty") : t("history.disabled"),
          data.enabled ? t("history.retention", { days: data.retention_days }) : null)));
      }
    } catch (err) {
      fail(err);
    }
  }

  const range = segmented([
    { value: 7, label: t("history.days", { count: 7 }) },
    { value: 30, label: t("history.days", { count: 30 }) },
    { value: 90, label: t("history.days", { count: 90 }) },
    { value: 365, label: t("history.days", { count: 365 }) },
  ], days, (value) => {
    days = value;
    store.set("history.days", value);
    range.update(value);
    loadSummary();
  });

  fill(root, 
    h("div", { class: "row between wrap" }, range,
      h("button", {
        class: "btn btn-sm btn-danger",
        onClick: async () => {
          if (!await confirmDialog({ title: t("history.confirm_clear"), message: t("history.confirm_clear_hint"), danger: true, confirm: t("history.clear") })) return;
          try {
            await api("DELETE", `/api/guilds/${gid}/history`);
            toast(t("history.cleared"), "success");
            loadSummary();
            loadRecent(true);
          } catch (err) {
            fail(err);
          }
        },
      }, icon("trash", "icon-sm"), t("history.clear"))),
    summaryBox,
    card({ title: t("history.recent"), iconName: "history" }, recentList, h("div", { class: "row" }, more)));

  // Cuando empieza otra canción se actualiza la lista (la historia se escribe al empezar)
  scope.on("player", ({ guildId, data }) => {
    if (guildId !== gid) return;
    const uri = data.connected && data.current ? data.current.uri || data.current.title : null;
    if (uri && lastUri !== null && uri !== lastUri) {
      setTimeout(() => {
        if (scope.alive) {
          loadRecent(true);
          loadSummary();
        }
      }, 800);
    }
    lastUri = uri;
  });

  await Promise.all([loadSummary(), loadRecent(true)]);
}
