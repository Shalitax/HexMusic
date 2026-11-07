// Playlists del usuario: crear, gestionar, añadir canciones y reproducirlas en cualquier servidor.
"use strict";

import {
  api, card, confirmDialog, emptyState, fail, fill, fmt, h, icon, iconButton, promptDialog, safeUrl, select, spinner, state,
  switchControl, t, toast,
} from "../core.js";

export async function renderList(ctx) {
  const { root, scope } = ctx;
  ctx.setTitle(t("playlists.title"), t("nav.general"));
  fill(root, h("div", { class: "loading" }, spinner()));
  const data = await api("GET", "/api/playlists");
  if (!scope.alive) return;
  state.playlists = data.playlists;

  const input = h("input", { class: "input", maxlength: 32, placeholder: t("playlists.create_placeholder") });
  const create = h("form", {
    class: "row",
    onSubmit: async (event) => {
      event.preventDefault();
      const name = input.value.trim();
      if (!name) return;
      try {
        const created = await api("POST", "/api/playlists", { name });
        toast(t("playlists.created"), "success");
        state.playlists = null;
        location.hash = `#/playlists/${created.id}`;
      } catch (err) {
        fail(err);
      }
    },
  }, h("div", { class: "grow" }, input), h("button", { class: "btn btn-primary", type: "submit" }, icon("plus", "icon-sm"), t("playlists.create")));

  const grid = data.playlists.length
    ? h("div", { class: "grid-auto" }, data.playlists.map((playlist) => h("a", {
      class: "server-card", href: `#/playlists/${playlist.id}`, style: { textDecoration: "none" },
    },
    h("div", { class: "guild-icon lg" }, icon("folder", "icon-lg")),
    h("div", { class: "grow" },
      h("div", { class: "strong ellipsis" }, playlist.name),
      h("div", { class: "muted small" }, t("playlists.tracks", { count: playlist.tracks }),
        playlist.public ? [" · ", t("playlists.public")] : null)),
    icon("chevronRight"))))
    : emptyState("folder", t("playlists.empty"), t("playlists.empty_hint"));

  fill(root, 
    card({ title: t("playlists.new"), iconName: "plus", sub: t("playlists.limits", { playlists: data.limits.max_playlists, tracks: data.limits.max_tracks }) }, create),
    card({ title: t("playlists.mine"), iconName: "folder", sub: String(data.playlists.length) }, grid));
}

export async function renderDetail(ctx) {
  const { root, route, scope } = ctx;
  const id = route.id;
  fill(root, h("div", { class: "loading" }, spinner()));
  let data = await api("GET", `/api/playlists/${id}`);
  if (!scope.alive) return;

  async function reload() {
    try {
      data = await api("GET", `/api/playlists/${id}`);
      if (scope.alive) draw();
    } catch (err) {
      fail(err);
    }
  }

  function draw() {
    ctx.setTitle(data.name, t("playlists.title"));
    const guilds = state.me.guilds.filter((guild) => guild.bot_present);
    const preferred = state.guildId && guilds.some((guild) => guild.id === state.guildId) ? state.guildId : "";
    const guildSelect = select([{ value: "", label: t("playlists.choose_server") }, ...guilds.map((guild) => ({ value: guild.id, label: guild.name }))], preferred);
    const shuffle = h("input", { type: "checkbox" });
    const play = h("button", { class: "btn btn-primary", type: "submit", disabled: !data.tracks.length }, icon("play", "icon-sm"), t("playlists.play"));

    const playForm = h("form", {
      class: "row wrap",
      onSubmit: async (event) => {
        event.preventDefault();
        if (!guildSelect.value) {
          toast(t("playlists.choose_server"), "error");
          return;
        }
        play.disabled = true;
        try {
          const result = await api("POST", `/api/playlists/${id}/play`, { guild_id: guildSelect.value, shuffle: shuffle.checked });
          toast(t("playlists.playing", { count: result.added }), "success");
        } catch (err) {
          fail(err);
        } finally {
          play.disabled = false;
        }
      },
    }, h("div", { style: { minWidth: "220px" } }, guildSelect), h("label", { class: "row tight small" }, shuffle, t("playlists.shuffle")), play);

    const addInput = h("input", { class: "input", maxlength: 500, placeholder: t("playlists.add_placeholder") });
    const addButton = h("button", { class: "btn btn-primary", type: "submit" }, icon("plus", "icon-sm"), t("playlists.add"));
    const addForm = h("form", {
      class: "row",
      onSubmit: async (event) => {
        event.preventDefault();
        const query = addInput.value.trim();
        if (!query) return;
        addButton.disabled = true;
        try {
          const result = await api("POST", `/api/playlists/${id}/tracks`, { query });
          toast(t("playlists.added", { count: result.added }), "success");
          state.playlists = null;
          reload();
        } catch (err) {
          fail(err);
        } finally {
          addButton.disabled = false;
        }
      },
    }, h("div", { class: "input-icon grow" }, icon("search"), addInput), addButton);

    const tracks = data.tracks.length
      ? h("ol", { class: "list", style: { margin: 0, padding: 0 } }, data.tracks.map((track) => h("li", { class: "list-row" },
        h("span", { class: "index" }, track.index),
        h("div", { class: "thumb sm" }, icon("music")),
        h("div", { class: "text" },
          safeUrl(track.uri)
            ? h("a", { class: "title", href: track.uri, target: "_blank", rel: "noopener noreferrer" }, track.title)
            : h("span", { class: "title" }, track.title),
          h("span", { class: "meta" }, track.author || "")),
        h("span", { class: "time" }, fmt.duration(track.length)),
        h("div", { class: "actions" }, iconButton("x", t("playlists.remove"), async () => {
          try {
            await api("DELETE", `/api/playlists/${id}/tracks/${track.index}`);
            state.playlists = null;
            reload();
          } catch (err) {
            fail(err);
          }
        }, "sm danger")))))
      : emptyState("music", t("playlists.empty_tracks"), t("playlists.add_hint"));

    const total = data.tracks.reduce((sum, track) => sum + (track.length || 0), 0);
    fill(root, 
      h("div", { class: "home-hero" },
        h("div", { class: "guild-icon lg" }, icon("folder", "icon-lg")),
        h("div", { class: "grow" },
          h("h1", { class: "ellipsis" }, data.name),
          h("div", { class: "muted" }, t("playlists.tracks", { count: data.tracks.length }), " · ", fmt.long(total))),
        h("div", { class: "page-actions" },
          h("button", { class: "btn btn-sm", onClick: async () => {
            const name = await promptDialog({ title: t("playlists.rename"), value: data.name, maxlength: 32 });
            if (!name || name === data.name) return;
            try {
              await api("PATCH", `/api/playlists/${id}`, { name });
              toast(t("playlists.renamed"), "success");
              state.playlists = null;
              reload();
            } catch (err) {
              fail(err);
            }
          } }, icon("edit", "icon-sm"), t("playlists.rename")),
          h("button", { class: "btn btn-sm btn-danger", onClick: async () => {
            if (!await confirmDialog({ title: t("playlists.confirm_delete", { name: data.name }), danger: true, confirm: t("playlists.delete") })) return;
            try {
              await api("DELETE", `/api/playlists/${id}`);
              toast(t("playlists.deleted"), "success");
              state.playlists = null;
              location.hash = "#/playlists";
            } catch (err) {
              fail(err);
            }
          } }, icon("trash", "icon-sm"), t("playlists.delete")))),
      h("div", { class: "grid-2" },
        card({ title: t("playlists.play_title"), iconName: "play" }, playForm),
        card({ title: t("playlists.visibility"), iconName: "globe" },
          switchControl(Boolean(data.public), async (value, input) => {
            try {
              await api("PATCH", `/api/playlists/${id}`, { public: value });
              data.public = value;
              toast(value ? t("playlists.made_public") : t("playlists.made_private"), "success");
            } catch (err) {
              input.checked = !value;
              fail(err);
            }
          }, t("playlists.public")),
          h("p", { class: "muted small" }, t("playlists.public_hint")))),
      card({ title: t("playlists.songs"), iconName: "music", sub: String(data.tracks.length) },
        addForm, h("p", { class: "muted small" }, t("playlists.add_hint")), tracks));
  }

  draw();
}
