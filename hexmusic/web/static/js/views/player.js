// Reproductor de un servidor: canción actual, controles, cola, letras y recientes.
"use strict";

import {
  api, avatar, card, confirmDialog, cover, emptyState, fail, fill, fmt, h, icon, iconButton, safeUrl, segmented, select,
  sourceName, spinner, switchControl, t, toast,
} from "../core.js";
import { estimatePosition, getPlayer, playerAction, refreshPlayer } from "../realtime.js";

const LOOP_ICONS = { off: "repeat", track: "repeat1", queue: "repeat" };

export function voiceChannelOptions(guild, placeholder) {
  return [
    { value: "", label: placeholder || t("player.choose_channel") },
    ...guild.voice_channels.map((channel) => ({
      value: channel.id,
      label: `🔊 ${channel.name}${channel.members ? ` (${channel.members})` : ""}`,
    })),
  ];
}

export function trackRow(track, { index, actions, current, extraMeta } = {}) {
  const title = safeUrl(track.uri)
    ? h("a", { class: "title", href: track.uri, target: "_blank", rel: "noopener noreferrer" }, track.title)
    : h("span", { class: "title" }, track.title);
  const meta = [track.author, extraMeta].filter(Boolean).join(" · ");
  return h("li", { class: `list-row${current ? " current" : ""}` },
    index !== undefined ? h("span", { class: "index" }, index) : null,
    cover(track.artwork),
    h("div", { class: "text" }, title, h("span", { class: "meta" }, meta)),
    h("span", { class: "time hide-sm" }, track.is_stream ? t("player.live") : fmt.duration(track.length)),
    actions ? h("div", { class: "actions" }, actions) : null);
}

export async function render(ctx) {
  const { root, scope, guild } = ctx;
  const gid = guild.id;
  ctx.setTitle(t("player.title"), guild.name);

  const nowBox = h("section", { class: "card now-card" });
  const addBox = h("div");
  const sideBox = h("section", { class: "card" });
  fill(root, h("div", { class: "player-layout" }, h("div", { class: "stack" }, nowBox, addBox), sideBox));

  let interacting = false;
  let sig = { now: null, queue: null, add: null };
  let sideTab = "queue";
  let lyrics = { key: null, data: null, loading: false, error: null };
  const elements = {};

  const hold = () => { interacting = true; };
  const release = () => setTimeout(() => { interacting = false; }, 400);

  // ───── Sonando ahora ─────

  function drawNow(p) {
    elements.progress = null;
    if (!p.connected) {
      const channel = select(voiceChannelOptions(guild), "");
      fill(nowBox, h("div", { class: "now-inner" },
        emptyState("headphones", t("player.not_connected"), t("player.not_connected_hint"),
          h("div", { class: "row wrap", style: { justifyContent: "center" } },
            h("div", { style: { minWidth: "220px" } }, channel),
            h("button", {
              class: "btn btn-primary",
              onClick: () => (channel.value
                ? playerAction(gid, { action: "join", channel_id: channel.value })
                : toast(t("player.choose_channel"), "error")),
            }, icon("plug"), t("player.join"))))));
      return;
    }

    const track = p.current;
    const art = track && safeUrl(track.artwork);
    const bg = h("div", { class: "now-bg" });
    if (art) bg.style.backgroundImage = `url("${art.replace(/["\\]/g, "")}")`;

    let meta;
    if (track) {
      const requester = track.requester
        ? h("span", { class: "requester" }, avatar(track.requester.avatar, "avatar xs"),
          t("player.requested_by", { name: track.requester.name || track.requester.id }))
        : track.recommended ? h("span", { class: "requester" }, icon("infinity", "icon-sm"), t("player.autoplay_track")) : null;
      meta = h("div", { class: "track-meta" },
        h("div", { class: "eyebrow" },
          h("span", { class: `eq${p.paused ? " paused" : ""}` }, h("span"), h("span"), h("span")),
          p.paused ? t("player.paused") : t("player.now_playing"),
          h("span", { class: "source" }, sourceName(track.source))),
        safeUrl(track.uri)
          ? h("a", { class: "track-title", href: track.uri, target: "_blank", rel: "noopener noreferrer" }, track.title)
          : h("div", { class: "track-title" }, track.title),
        h("div", { class: "track-author" }, track.author || ""),
        requester);
    } else {
      meta = h("div", { class: "track-meta" },
        h("div", { class: "eyebrow" }, t("player.idle")),
        h("div", { class: "track-title" }, t("player.nothing_playing")),
        h("div", { class: "track-author muted" }, t("player.nothing_playing_hint")));
    }

    let progress = null;
    if (track && !track.is_stream) {
      const range = h("input", {
        type: "range", min: 0, max: track.length, step: 1000, value: estimatePosition(gid),
        "aria-label": t("player.seek"), disabled: !track.seekable,
        onPointerdown: hold, onPointerup: release, onKeydown: hold, onKeyup: release,
        onInput: (event) => { posLabel.textContent = fmt.duration(Number(event.target.value)); },
        onChange: (event) => playerAction(gid, { action: "seek", position: Number(event.target.value) }),
      });
      const posLabel = h("span", null, fmt.duration(estimatePosition(gid)));
      elements.progress = { range, posLabel };
      progress = h("div", { class: "progress" }, posLabel, range, h("span", null, fmt.duration(track.length)));
    } else if (track) {
      progress = h("span", { class: "live-pill" }, t("player.live"));
    }

    const loop = segmented([
      { value: "off", icon: "repeat", label: t("player.loop_off") },
      { value: "track", icon: "repeat1", label: t("player.loop_track") },
      { value: "queue", icon: LOOP_ICONS.queue, label: t("player.loop_queue") },
    ], p.loop, (mode) => playerAction(gid, { action: "loop", mode }));

    const transport = h("div", { class: "transport" },
      iconButton("shuffle", t("player.shuffle"), () => playerAction(gid, { action: "shuffle" }), "lg", !p.queue_length),
      iconButton("prev", t("player.previous"), () => playerAction(gid, { action: "previous" }), "lg"),
      iconButton(p.paused ? "play" : "pause", p.paused ? t("player.resume") : t("player.pause"),
        () => playerAction(gid, { action: "pause", paused: !p.paused }), "play", !track),
      iconButton("next", t("player.skip"), () => playerAction(gid, { action: "skip" }), "lg", !track),
      iconButton("stop", t("player.stop"), async () => {
        if (await confirmDialog({ title: t("player.confirm_stop"), danger: true, confirm: t("player.stop") })) {
          playerAction(gid, { action: "stop" });
        }
      }, "lg"));

    // Volumen con silencio
    const volValue = h("span", { class: "value" }, `${p.volume}%`);
    const volRange = h("input", {
      type: "range", min: 0, max: guild.max_volume, value: p.volume, "aria-label": t("player.volume"),
      onPointerdown: hold, onPointerup: release,
      onInput: (event) => { volValue.textContent = `${event.target.value}%`; },
      onChange: (event) => playerAction(gid, { action: "volume", value: Number(event.target.value) }),
    });
    const muteBtn = iconButton(p.volume === 0 ? "mute" : "volume", p.volume === 0 ? t("player.unmute") : t("player.mute"), () => {
      if (p.volume > 0) {
        elements.lastVolume = p.volume;
        playerAction(gid, { action: "volume", value: 0 });
      } else {
        playerAction(gid, { action: "volume", value: elements.lastVolume || guild.settings.default_volume || 100 });
      }
    }, "sm");

    const presets = [{ value: "", label: t("player.no_filter") }, ...guild.presets.map((name) => ({ value: name, label: name }))];
    if (p.filter && !guild.presets.includes(p.filter)) presets.push({ value: p.filter, label: t("player.custom_filter") });
    const filter = select(presets, p.filter || "", (value) => playerAction(gid, { action: "filter", preset: value || null }));
    filter.addEventListener("focus", hold);
    filter.addEventListener("blur", release);

    const loopField = h("div", { class: "field span-2" }, h("span", { class: "field-label" }, icon("repeat", "icon-sm"), t("player.loop")), loop);
    const options = h("div", { class: "player-options" },
      h("div", { class: "field span-2" }, h("span", { class: "field-label" }, icon("volume", "icon-sm"), t("player.volume")),
        h("div", { class: "volume" }, muteBtn, volRange, volValue)),
      h("div", { class: "field" }, h("span", { class: "field-label" }, icon("sliders", "icon-sm"), t("player.filter")), filter),
      h("div", { class: "field" }, h("span", { class: "field-label" }, icon("bolt", "icon-sm"), t("player.modes")),
        h("div", { class: "row wrap" },
          guild.features.autoplay
            ? switchControl(p.autoplay, (value) => playerAction(gid, { action: "autoplay", enabled: value }), t("player.autoplay"))
            : null,
          guild.features.stay_247
            ? switchControl(p.stay_247, async (value, input) => {
              try {
                Object.assign(guild, await api("PATCH", `/api/guilds/${gid}/settings`, { stay_247: value }));
                refreshPlayer(gid);
              } catch (err) {
                input.checked = !value;
                fail(err);
              }
            }, "24/7")
            : null)),
      loopField);

    const channelSelect = select(voiceChannelOptions(guild), p.channel ? p.channel.id : "",
      (value) => value && playerAction(gid, { action: "join", channel_id: value }), "select sm");
    channelSelect.addEventListener("focus", hold);
    channelSelect.addEventListener("blur", release);
    const listeners = (p.listener_list || []).slice(0, 8);

    fill(nowBox, bg, h("div", { class: "now-inner" },
      h("div", { class: "now-top" }, cover(track && track.artwork, "cover"), meta),
      progress,
      transport,
      options,
      h("div", { class: "now-footer" },
        h("div", { class: "row wrap" },
          h("div", { style: { minWidth: "200px" } }, channelSelect),
          listeners.length ? h("div", { class: "avatars", title: listeners.map((m) => m.name).join(", ") },
            listeners.map((m) => avatar(m.avatar))) : null,
          h("span", { class: "muted small" }, t("player.listeners", { count: p.listeners }))),
        h("button", {
          class: "btn btn-sm btn-danger",
          onClick: async () => {
            if (await confirmDialog({ title: t("player.confirm_leave"), danger: true, confirm: t("player.leave") })) {
              playerAction(gid, { action: "leave" });
            }
          },
        }, icon("door", "icon-sm"), t("player.leave")))));
  }

  // ───── Añadir ─────

  function drawAdd(p) {
    const input = h("input", { class: "input", type: "text", maxlength: 500, placeholder: t("player.add_placeholder"),
      "aria-label": t("player.add_title") });
    const source = select([{ value: "", label: t("player.source_default") }, ...guild.sources], "", null, "select sm");
    const next = h("input", { type: "checkbox" });
    const channel = p.connected ? null : select(voiceChannelOptions(guild, t("player.channel_auto")), "", null, "select sm");
    const button = h("button", { class: "btn btn-primary", type: "submit" }, icon("plus"), t("player.add_button"));

    fill(addBox, card({ title: t("player.add_title"), iconName: "plus",
      actions: h("button", { class: "btn btn-sm btn-ghost", type: "button",
        onClick: () => { location.hash = `#/g/${gid}/search${input.value.trim() ? `?q=${encodeURIComponent(input.value.trim())}` : ""}`; } },
      icon("search", "icon-sm"), t("player.advanced_search")) },
    h("form", {
      class: "stack tight",
      onSubmit: async (event) => {
        event.preventDefault();
        const query = input.value.trim();
        if (!query) return;
        button.disabled = true;
        const ok = await playerAction(gid, {
          action: "play", query, source: source.value || null, next: next.checked,
          channel_id: channel ? channel.value || null : null,
        }, t("player.added"));
        button.disabled = false;
        if (ok) input.value = "";
      },
    },
    h("div", { class: "row" }, h("div", { class: "input-icon grow" }, icon("search"), input), button),
    h("div", { class: "row wrap" },
      h("div", { style: { minWidth: "170px" } }, source),
      channel ? h("div", { style: { minWidth: "200px" } }, channel) : null,
      h("label", { class: "row tight small" }, next, t("player.play_next"))))));
  }

  // ───── Cola, letras y recientes ─────

  function moveTarget(from, row, after) {
    let slot = after ? row : row - 1; // posición 0-based donde insertar en la lista original
    if (slot > from - 1) slot -= 1;
    return slot + 1;
  }

  function drawQueue(p, body) {
    if (!p.connected || !p.queue_length) {
      fill(body, emptyState("list", t("player.queue_empty"), t("player.queue_empty_hint")));
      return;
    }
    let dragFrom = null;
    const rows = p.queue.map((track, i) => {
      const index = i + 1;
      const row = trackRow(track, {
        index,
        extraMeta: track.requester && track.requester.name ? track.requester.name : null,
        actions: [
          iconButton("play", t("player.skip_to"), () => playerAction(gid, { action: "skipto", index }), "sm"),
          iconButton("chevronDown", t("player.move_down"), () => playerAction(gid, { action: "move", from: index, to: index + 1 }), "sm", index === p.queue_length),
          iconButton("x", t("player.remove"), () => playerAction(gid, { action: "remove", index }), "sm danger"),
        ],
      });
      row.prepend(h("span", { class: "handle", title: t("player.drag") }, icon("grip", "icon-sm")));
      row.draggable = true;
      row.addEventListener("dragstart", (event) => {
        dragFrom = index;
        row.classList.add("dragging");
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", String(index));
        hold();
      });
      row.addEventListener("dragend", () => {
        row.classList.remove("dragging");
        body.querySelectorAll(".drop-before, .drop-after").forEach((el) => el.classList.remove("drop-before", "drop-after"));
        release();
      });
      row.addEventListener("dragover", (event) => {
        if (dragFrom === null) return;
        event.preventDefault();
        const rect = row.getBoundingClientRect();
        const after = event.clientY > rect.top + rect.height / 2;
        row.classList.toggle("drop-after", after);
        row.classList.toggle("drop-before", !after);
      });
      row.addEventListener("dragleave", () => row.classList.remove("drop-before", "drop-after"));
      row.addEventListener("drop", (event) => {
        event.preventDefault();
        const after = row.classList.contains("drop-after");
        row.classList.remove("drop-before", "drop-after");
        if (dragFrom === null) return;
        const to = moveTarget(dragFrom, index, after);
        const from = dragFrom;
        dragFrom = null;
        interacting = false;
        if (to !== from) playerAction(gid, { action: "move", from, to });
      });
      return row;
    });
    fill(body, 
      h("ol", { class: "list", style: { maxHeight: "640px", overflowY: "auto", margin: 0, padding: 0 } }, rows),
      p.queue_length > p.queue.length ? h("p", { class: "muted small" }, t("player.queue_more", { count: p.queue_length - p.queue.length })) : null);
  }

  function drawRecent(p, body) {
    const items = p.connected ? p.recent || [] : [];
    if (!items.length) {
      fill(body, emptyState("history", t("player.recent_empty"), null));
      return;
    }
    fill(body, h("ol", { class: "list", style: { margin: 0, padding: 0 } }, items.map((track) => trackRow(track, {
      actions: safeUrl(track.uri) ? [
        iconButton("plus", t("player.add_again"), () => playerAction(gid, { action: "play", query: track.uri }, t("player.added")), "sm"),
        iconButton("queueNext", t("player.play_next"), () => playerAction(gid, { action: "play", query: track.uri, next: true }, t("player.added")), "sm"),
      ] : null,
    }))));
  }

  async function loadLyrics(p) {
    const key = p.connected && p.current ? p.current.uri || p.current.title : null;
    if (key === lyrics.key) return;
    lyrics = { key, data: null, loading: Boolean(key), error: null };
    if (!key) return;
    try {
      const result = await api("GET", `/api/guilds/${gid}/lyrics`);
      if (lyrics.key === key) lyrics = { key, data: result.lyrics, loading: false, error: null };
    } catch (err) {
      if (lyrics.key === key) lyrics = { key, data: null, loading: false, error: err.message };
    }
    if (scope.alive && sideTab === "lyrics") drawSide(getPlayer(gid) || { connected: false });
  }

  function drawLyrics(p, body) {
    elements.lyrics = null;
    if (!p.connected || !p.current) {
      fill(body, emptyState("mic", t("player.lyrics_idle"), null));
      return;
    }
    loadLyrics(p);
    if (lyrics.loading) {
      fill(body, h("div", { class: "loading" }, spinner()));
      return;
    }
    if (lyrics.error) {
      fill(body, emptyState("alert", lyrics.error, null));
      return;
    }
    const data = lyrics.data;
    if (!data) {
      fill(body, emptyState("mic", t("player.lyrics_not_found"), t("player.lyrics_source")));
      return;
    }
    if (data.instrumental) {
      fill(body, emptyState("music", t("player.lyrics_instrumental"), null));
      return;
    }
    const header = h("div", { class: "muted small" }, `${data.title} — ${data.artist}`, " · ",
      data.synced.length ? t("player.lyrics_synced") : t("player.lyrics_plain"));
    if (data.synced.length) {
      const lines = data.synced.map((line) => h("p", null, line.text || "♪"));
      const box = h("div", { class: "lyrics" }, lines);
      elements.lyrics = { box, lines, times: data.synced.map((line) => line.t), active: -1 };
      fill(body, header, box);
      tickLyrics();
    } else {
      fill(body, header, h("div", { class: "lyrics plain" }, data.text.split("\n").map((line) => h("p", null, line || " "))));
    }
  }

  function tickLyrics() {
    const lyr = elements.lyrics;
    if (!lyr) return;
    const position = estimatePosition(gid) + 250;
    let active = -1;
    for (let i = 0; i < lyr.times.length; i++) {
      if (lyr.times[i] <= position) active = i;
      else break;
    }
    if (active === lyr.active) return;
    lyr.active = active;
    lyr.lines.forEach((line, i) => {
      line.classList.toggle("active", i === active);
      line.classList.toggle("past", i < active);
    });
    if (active >= 0) {
      const line = lyr.lines[active];
      lyr.box.scrollTop = line.offsetTop - lyr.box.offsetTop - lyr.box.clientHeight / 2 + line.clientHeight / 2;
    }
  }

  function drawSide(p) {
    const tabs = [
      { id: "queue", icon: "list", label: t("player.queue"), count: p.connected ? p.queue_length : 0 },
      guild.features.lyrics ? { id: "lyrics", icon: "mic", label: t("player.lyrics") } : null,
      { id: "recent", icon: "history", label: t("player.recent") },
    ].filter(Boolean);
    if (!tabs.some((tab) => tab.id === sideTab)) sideTab = "queue";

    const body = h("div", { class: "stack tight" });
    const headerActions = sideTab === "queue" && p.connected && p.queue_length
      ? h("div", { class: "row tight" },
        h("span", { class: "muted small" }, t("player.queue_info", { count: p.queue_length, duration: fmt.duration(p.queue_duration) })),
        h("button", { class: "btn btn-xs", onClick: () => playerAction(gid, { action: "shuffle" }) }, icon("shuffle", "icon-sm"), t("player.shuffle")),
        h("button", {
          class: "btn btn-xs btn-danger",
          onClick: async () => {
            if (await confirmDialog({ title: t("player.confirm_clear"), danger: true, confirm: t("player.clear") })) {
              playerAction(gid, { action: "clear" });
            }
          },
        }, icon("trash", "icon-sm"), t("player.clear")))
      : null;

    fill(sideBox, 
      h("div", { class: "tabs", role: "tablist" }, tabs.map((tab) => h("button", {
        class: `tab${tab.id === sideTab ? " active" : ""}`, role: "tab", "aria-selected": tab.id === sideTab ? "true" : "false",
        onClick: () => { sideTab = tab.id; drawSide(getPlayer(gid) || { connected: false }); },
      }, icon(tab.icon, "icon-sm"), tab.label, tab.count ? h("span", { class: "badge" }, tab.count) : null))),
      headerActions,
      body);
    if (sideTab === "queue") drawQueue(p, body);
    else if (sideTab === "lyrics") drawLyrics(p, body);
    else drawRecent(p, body);
  }

  // ───── Actualización ─────

  function apply(p, force = false) {
    const current = p.current || {};
    const nowSig = JSON.stringify([p.connected, current.title, current.uri, current.requester, p.paused, p.volume, p.loop,
      p.autoplay, p.stay_247, p.filter, p.listeners, p.channel && p.channel.id, (p.listener_list || []).length, p.queue_length > 0]);
    const queueSig = JSON.stringify([p.connected, p.queue_length, (p.queue || []).map((track) => `${track.uri}|${track.title}`),
      (p.recent || []).map((track) => track.uri), current.uri]);
    const addSig = String(p.connected);
    if ((force || nowSig !== sig.now) && !interacting) {
      drawNow(p);
      sig.now = nowSig;
    } else if (elements.progress && !interacting) {
      // Saltos de posición (seek desde Discord): solo se mueve la barra
      const position = estimatePosition(gid);
      elements.progress.range.value = position;
      elements.progress.posLabel.textContent = fmt.duration(position);
    }
    if ((force || queueSig !== sig.queue) && !interacting) {
      drawSide(p);
      sig.queue = queueSig;
    }
    if (force || addSig !== sig.add) {
      drawAdd(p);
      sig.add = addSig;
    }
  }

  function tick() {
    if (interacting || !elements.progress) {
      tickLyrics();
      return;
    }
    const position = estimatePosition(gid);
    elements.progress.range.value = position;
    elements.progress.posLabel.textContent = fmt.duration(position);
    tickLyrics();
  }

  scope.on("player", ({ guildId, data }) => {
    if (guildId === gid) apply(data);
  });
  scope.every(500, tick);

  const existing = getPlayer(gid);
  if (existing) apply(existing, true);
  else {
    fill(nowBox, h("div", { class: "loading" }, spinner()));
    await refreshPlayer(gid);
    const fresh = getPlayer(gid);
    if (fresh && scope.alive) apply(fresh, true);
    else if (scope.alive) apply({ connected: false }, true);
  }
}
