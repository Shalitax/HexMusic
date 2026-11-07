// Búsqueda con resultados: añadir a la cola, a continuación o a una playlist.
"use strict";

import { api, card, cover, emptyState, fail, fill, fmt, h, icon, iconButton, popover, safeUrl, select, sourceName, spinner, state, t, toast } from "../core.js";
import { refreshPlayer } from "../realtime.js";

async function myPlaylists() {
  if (!state.playlists) state.playlists = (await api("GET", "/api/playlists")).playlists;
  return state.playlists;
}

function playlistMenu(anchor, ids) {
  popover(anchor, async (el, close) => {
    el.append(h("div", { class: "loading", style: { minHeight: "80px" } }, spinner("sm")));
    let lists;
    try {
      lists = await myPlaylists();
    } catch (err) {
      close();
      fail(err);
      return;
    }
    const add = async (playlist) => {
      close();
      try {
        const result = await api("POST", `/api/playlists/${playlist.id}/tracks`, { ids });
        toast(t("search.saved_to", { count: result.added, name: playlist.name }), "success");
        state.playlists = null;
      } catch (err) {
        fail(err);
      }
    };
    fill(el, 
      h("div", { class: "nav-title", style: { padding: "6px 10px" } }, t("search.save_to_playlist")),
      lists.length
        ? lists.map((playlist) => h("button", { class: "popover-item", role: "menuitem", onClick: () => add(playlist) },
          icon("folder"), h("span", { class: "grow ellipsis" }, playlist.name), h("span", { class: "muted small" }, playlist.tracks)))
        : h("p", { class: "muted small", style: { padding: "6px 10px" } }, t("search.no_playlists")),
      h("button", { class: "popover-item", onClick: () => { close(); location.hash = "#/playlists"; } }, icon("plus"), t("search.new_playlist")));
  });
}

export async function render(ctx) {
  const { root, guild, route } = ctx;
  const gid = guild.id;
  ctx.setTitle(t("search.title"), guild.name);

  const input = h("input", { class: "input", type: "search", maxlength: 500, placeholder: t("search.placeholder"),
    value: route.query.q || "", "aria-label": t("search.title") });
  const source = select([{ value: "", label: t("player.source_default") }, ...guild.sources], state.searchSource ?? "", (value) => {
    state.searchSource = value;
  });
  const button = h("button", { class: "btn btn-primary", type: "submit" }, icon("search"), t("search.button"));
  const results = h("div", { class: "stack" });

  const enqueue = async (ids, next, label) => {
    try {
      const result = await api("POST", `/api/guilds/${gid}/enqueue`, { ids, next });
      toast(label || t("search.added", { count: result.added }), "success");
      refreshPlayer(gid);
    } catch (err) {
      fail(err);
    }
  };

  const playLibrary = async (entry, next) => {
    try {
      await api("POST", `/api/guilds/${gid}/library/play`, { ids: [entry.id], next });
      toast(t("search.added", { count: 1 }), "success");
      refreshPlayer(gid);
    } catch (err) {
      fail(err);
    }
  };

  async function run(query) {
    fill(results, h("div", { class: "loading" }, spinner()));
    let data;
    try {
      data = await api("POST", `/api/guilds/${gid}/search`, { query, source: source.value || null });
    } catch (err) {
      fill(results, card({}, emptyState("alert", err.message, null)));
      return;
    }
    const blocks = [];
    if (data.library.length) {
      blocks.push(card({ title: t("search.library_matches"), iconName: "library" },
        h("ol", { class: "list", style: { margin: 0, padding: 0 } }, data.library.map((entry) => h("li", { class: "list-row" },
          h("div", { class: "thumb" }, icon("folder")),
          h("div", { class: "text" }, h("span", { class: "title" }, entry.title), h("span", { class: "meta" }, t("search.from_library"))),
          h("span", { class: "time" }, entry.length ? fmt.duration(entry.length) : "—"),
          h("div", { class: "actions always" },
            iconButton("plus", t("search.add"), () => playLibrary(entry, false), "sm"),
            iconButton("queueNext", t("player.play_next"), () => playLibrary(entry, true), "sm")))))));
    }
    if (!data.tracks.length) {
      blocks.push(card({}, emptyState("search", t("search.no_results"), t("search.no_results_hint"))));
      fill(results, ...blocks);
      return;
    }
    const allIds = data.tracks.map((track) => track.id);
    const header = data.playlist
      ? h("div", { class: "row wrap" },
        cover(data.playlist.artwork, "thumb"),
        h("div", { class: "grow" }, h("div", { class: "strong" }, data.playlist.name),
          h("div", { class: "muted small" }, t("search.playlist_count", { count: data.playlist.count }))),
        h("button", { class: "btn btn-primary btn-sm", onClick: () => enqueue(allIds, false) }, icon("plus", "icon-sm"), t("search.add_all")),
        h("button", { class: "btn btn-sm", onClick: (event) => playlistMenu(event.currentTarget, allIds) }, icon("folder", "icon-sm"), t("search.save_all")))
      : null;
    blocks.push(card({ title: data.playlist ? null : t("search.results", { count: data.tracks.length }), iconName: "music" },
      header,
      h("ol", { class: "list", style: { margin: 0, padding: 0 } }, data.tracks.map((track, i) => {
        const title = safeUrl(track.uri)
          ? h("a", { class: "title", href: track.uri, target: "_blank", rel: "noopener noreferrer" }, track.title)
          : h("span", { class: "title" }, track.title);
        return h("li", { class: "list-row" },
          h("span", { class: "index" }, i + 1),
          cover(track.artwork),
          h("div", { class: "text" }, title,
            h("span", { class: "meta" }, [track.author, track.album].filter(Boolean).join(" · "))),
          h("span", { class: "source" }, sourceName(track.source)),
          h("span", { class: "time hide-sm" }, track.is_stream ? t("player.live") : fmt.duration(track.length)),
          h("div", { class: "actions always" },
            iconButton("plus", t("search.add"), () => enqueue([track.id], false), "sm"),
            iconButton("queueNext", t("player.play_next"), () => enqueue([track.id], true), "sm"),
            iconButton("folder", t("search.save_to_playlist"), (event) => playlistMenu(event.currentTarget, [track.id]), "sm")));
      }))));
    fill(results, ...blocks);
  }

  const form = h("form", {
    class: "card",
    onSubmit: async (event) => {
      event.preventDefault();
      const query = input.value.trim();
      if (!query) return;
      history.replaceState(null, "", `#/g/${gid}/search?q=${encodeURIComponent(query)}`);
      button.disabled = true;
      await run(query);
      button.disabled = false;
    },
  },
  h("div", { class: "row wrap" },
    h("div", { class: "input-icon grow", style: { minWidth: "220px" } }, icon("search"), input),
    h("div", { style: { minWidth: "180px" } }, source),
    button),
  h("p", { class: "muted small" }, t("search.hint")));

  fill(root, form, results);
  if (input.value.trim()) run(input.value.trim());
  else fill(results, card({}, emptyState("search", t("search.empty_title"), t("search.empty_hint"))));
  input.focus();
}

