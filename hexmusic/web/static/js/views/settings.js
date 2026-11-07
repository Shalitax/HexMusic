// Ajustes de un servidor: generales, música, permisos DJ y canal de peticiones.
"use strict";

import { api, card, confirmDialog, fail, fill, field, h, icon, select, switchControl, t, toast } from "../core.js";
import { refreshPlayer } from "../realtime.js";

export async function render(ctx) {
  const { root, guild } = ctx;
  const gid = guild.id;
  ctx.setTitle(t("settings.title"), guild.name);

  const save = async (payload, message) => {
    try {
      const updated = await api("PATCH", `/api/guilds/${gid}/settings`, payload);
      Object.assign(guild, updated);
      toast(message || t("settings.saved"), "success");
      refreshPlayer(gid);
      return true;
    } catch (err) {
      fail(err);
      return false;
    }
  };

  function draw() {
    const s = guild.settings;
    const d = guild.defaults;
    const onOff = (value) => (value ? t("common.on") : t("common.off"));
    const languageName = (code) => (guild.languages.find((lang) => lang.code === code) || {}).name || code;
    const tri = (value, fallback) => select([
      { value: "", label: t("settings.default_option", { value: onOff(fallback) }) },
      { value: "true", label: t("common.on") },
      { value: "false", label: t("common.off") },
    ], value === null || value === undefined ? "" : String(value));

    // ── General ──
    const language = select([{ value: "", label: t("settings.default_option", { value: languageName(d.language) }) },
      ...guild.languages.map((lang) => ({ value: lang.code, label: lang.name }))], s.language || "");
    const prefix = h("input", { class: "input", maxlength: 10, placeholder: d.prefix, value: s.prefix || "" });
    const volume = h("input", { class: "input", type: "number", min: 0, max: guild.max_volume, placeholder: String(d.default_volume),
      value: s.default_volume === null ? "" : s.default_volume });
    const announce = tri(s.announce, d.announce);
    const voteSkip = tri(s.vote_skip, d.vote_skip);
    const saveButton = h("button", { class: "btn btn-primary", type: "submit" }, icon("save", "icon-sm"), t("common.save"));

    const general = h("form", {
      class: "card",
      onSubmit: async (event) => {
        event.preventDefault();
        const triValue = (el) => (el.value === "" ? null : el.value === "true");
        const payload = {
          language: language.value || null,
          prefix: prefix.value.trim() || null,
          default_volume: volume.value === "" ? null : Number(volume.value),
          announce: triValue(announce),
        };
        if (guild.features.vote_skip) payload.vote_skip = triValue(voteSkip);
        saveButton.disabled = true;
        await save(payload);
        saveButton.disabled = false;
        draw();
      },
    },
    h("div", { class: "card-header" }, h("div", { class: "title" }, icon("settings"), h("h2", null, t("settings.general")))),
    h("div", { class: "fields" },
      field(t("settings.language"), language, t("settings.language_hint")),
      field(t("settings.prefix"), prefix, t("settings.prefix_hint")),
      field(t("settings.default_volume"), volume, t("settings.volume_hint", { max: guild.max_volume })),
      field(t("settings.announce"), announce, t("settings.announce_hint")),
      guild.features.vote_skip ? field(t("settings.vote_skip"), voteSkip, t("settings.vote_skip_hint")) : null),
    h("div", { class: "row end" }, saveButton));

    // ── Música ──
    const toggleRow = (title, hint, control) => h("div", { class: "toggle-row" },
      h("div", { class: "text" }, h("span", { class: "strong" }, title), h("span", { class: "muted small" }, hint)), control);
    const music = card({ title: t("settings.music"), iconName: "music" },
      h("div", null,
        guild.features.autoplay
          ? toggleRow(t("settings.autoplay"), t("settings.autoplay_hint"),
            switchControl(s.autoplay, async (value, input) => { if (!await save({ autoplay: value })) input.checked = !value; }, null))
          : null,
        guild.features.stay_247
          ? toggleRow(t("settings.stay_247"), t("settings.stay_247_hint"),
            switchControl(s.stay_247, async (value, input) => { if (!await save({ stay_247: value })) input.checked = !value; }, null))
          : null,
        !guild.features.autoplay && !guild.features.stay_247 ? h("p", { class: "muted" }, t("settings.music_disabled")) : null));

    // ── Permisos DJ ──
    const djRole = select([{ value: "", label: t("settings.no_role") },
      ...guild.roles.map((role) => ({ value: role.id, label: `@${role.name}` }))], s.dj_role_id || "",
    (value) => save({ dj_role_id: value || null }));
    const custom = Array.isArray(s.dj_commands);
    let selected = new Set(custom ? s.dj_commands : d.dj_commands);
    const chips = h("div", { class: "chips" });
    const drawChips = (enabled) => fill(chips, ...guild.dj_command_choices.map((name) => h("button", {
      type: "button",
      class: `chip${selected.has(name) ? " on" : ""}`,
      disabled: !enabled,
      "aria-pressed": selected.has(name) ? "true" : "false",
      onClick: () => {
        if (selected.has(name)) selected.delete(name);
        else selected.add(name);
        drawChips(true);
        saveDj.disabled = false;
      },
    }, selected.has(name) ? icon("check", "icon-sm") : null, `/${name}`)));
    const saveDj = h("button", { class: "btn btn-primary btn-sm", disabled: true,
      onClick: async () => {
        saveDj.disabled = true;
        await save({ dj_commands: [...selected] }, t("settings.dj_saved"));
        draw();
      } }, t("common.save"));
    const useGlobal = switchControl(!custom, async (value) => {
      if (value) {
        await save({ dj_commands: null }, t("settings.dj_saved"));
        draw();
      } else {
        selected = new Set(d.dj_commands);
        drawChips(true);
        saveDj.disabled = false;
      }
    }, t("settings.dj_use_global"));
    drawChips(custom);
    const dj = card({ title: t("settings.permissions"), iconName: "shield" },
      field(t("settings.dj_role"), djRole, t("settings.dj_role_hint")),
      h("div", { class: "field" },
        h("span", { class: "field-label" }, t("settings.dj_commands")),
        h("span", { class: "field-hint" }, t("settings.dj_commands_hint")),
        useGlobal, chips, h("div", { class: "row end" }, saveDj)));

    // ── Canal de peticiones ──
    let requestCard = null;
    if (guild.features.request_channel) {
      const rc = guild.request_channel;
      const channel = select([{ value: "", label: t("settings.request_new") },
        ...guild.text_channels.map((item) => ({ value: item.id, label: `# ${item.name}` }))], rc.exists ? rc.id : "");
      const apply = h("button", { class: "btn btn-primary btn-sm", onClick: async () => {
        apply.disabled = true;
        try {
          Object.assign(guild, await api("POST", `/api/guilds/${gid}/request-channel`, { channel_id: channel.value || null }));
          toast(t("settings.request_done"), "success");
          draw();
        } catch (err) {
          fail(err);
        } finally {
          apply.disabled = false;
        }
      } }, icon("check", "icon-sm"), rc.id ? t("settings.request_move") : t("settings.request_create"));
      const remove = rc.id ? h("button", { class: "btn btn-sm btn-danger", onClick: async () => {
        if (!await confirmDialog({ title: t("settings.request_remove_confirm"), danger: true, confirm: t("settings.request_remove") })) return;
        try {
          Object.assign(guild, await api("DELETE", `/api/guilds/${gid}/request-channel`));
          toast(t("settings.request_removed"), "success");
          draw();
        } catch (err) {
          fail(err);
        }
      } }, t("settings.request_remove")) : null;
      requestCard = card({ title: t("settings.request_channel"), iconName: "inbox" },
        h("div", { class: rc.id ? "notice" : "notice warn" }, icon(rc.id ? "check" : "info"),
          h("div", null, rc.id
            ? (rc.exists ? t("settings.request_active", { channel: rc.name }) : t("settings.request_missing"))
            : t("settings.request_inactive"))),
        h("p", { class: "muted small" }, t("settings.request_hint")),
        !guild.bot_permissions.manage_messages ? h("div", { class: "notice warn" }, icon("alert"), t("settings.request_perms")) : null,
        h("div", { class: "row wrap" }, h("div", { style: { minWidth: "240px" } }, channel), apply, remove));
    }

    // ── Restablecer ──
    const danger = card({ title: t("settings.danger"), iconName: "alert", cls: "danger-zone" },
      h("div", { class: "toggle-row" },
        h("div", { class: "text" }, h("span", { class: "strong" }, t("settings.reset")), h("span", { class: "muted small" }, t("settings.reset_hint"))),
        h("button", { class: "btn btn-danger btn-sm", onClick: async () => {
          if (!await confirmDialog({ title: t("settings.reset_confirm"), danger: true, confirm: t("settings.reset") })) return;
          try {
            Object.assign(guild, await api("POST", `/api/guilds/${gid}/settings/reset`));
            toast(t("settings.reset_done"), "success");
            draw();
          } catch (err) {
            fail(err);
          }
        } }, icon("replay", "icon-sm"), t("settings.reset"))));

    fill(root, general, h("div", { class: "grid-2" }, music, dj), requestCard, danger);
  }

  draw();
}
