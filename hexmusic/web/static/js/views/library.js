// Biblioteca de archivos del servidor: subir desde el navegador, reproducir, renombrar y borrar.
"use strict";

import {
  api, avatar, card, confirmDialog, emptyState, fail, fill, fmt, h, icon, iconButton, meter, promptDialog, spinner, t, toast,
  uploadFile,
} from "../core.js";
import { refreshPlayer } from "../realtime.js";

export async function render(ctx) {
  const { root, guild, scope } = ctx;
  const gid = guild.id;
  ctx.setTitle(t("library.title"), guild.name);
  fill(root, h("div", { class: "loading" }, spinner()));

  let data = await api("GET", `/api/guilds/${gid}/library`);
  if (!scope.alive) return;

  if (!data.enabled) {
    fill(root, card({}, emptyState("library", t("library.disabled"), t("library.disabled_hint"))));
    return;
  }

  const usageBox = h("div");
  const listBox = h("div", { class: "stack tight" });
  const uploads = h("div", { class: "uploads" });
  const filter = h("input", { class: "input sm", type: "search", placeholder: t("library.filter"), "aria-label": t("library.filter"),
    onInput: () => drawList() });
  const fileInput = h("input", { type: "file", multiple: true, accept: data.formats.map((ext) => `.${ext}`).join(","), hidden: true,
    onChange: (event) => { queueFiles([...event.target.files]); event.target.value = ""; } });

  async function reload() {
    try {
      data = await api("GET", `/api/guilds/${gid}/library`);
      if (scope.alive) {
        drawUsage();
        drawList();
      }
    } catch (err) {
      fail(err);
    }
  }

  const play = async (payload, message) => {
    try {
      const result = await api("POST", `/api/guilds/${gid}/library/play`, payload);
      toast(message || t("library.queued", { count: result.added }), "success");
      refreshPlayer(gid);
    } catch (err) {
      fail(err);
    }
  };

  function drawUsage() {
    const u = data.usage;
    const spaceFraction = u.max_bytes ? u.used / u.max_bytes : 0;
    fill(usageBox, h("div", { class: "grid-2" },
      h("div", { class: "field" },
        h("div", { class: "row between small" }, h("span", { class: "strong" }, t("library.space")),
          h("span", { class: "muted tabular" }, `${fmt.bytes(u.used)} / ${u.max_bytes ? fmt.bytes(u.max_bytes) : "∞"}`)),
        u.max_bytes ? meter(spaceFraction) : null),
      h("div", { class: "field" },
        h("div", { class: "row between small" }, h("span", { class: "strong" }, t("library.files")),
          h("span", { class: "muted tabular" }, `${u.count} / ${u.max_files || "∞"}`)),
        u.max_files ? meter(u.count / u.max_files) : null)),
    h("p", { class: "muted small", style: { marginTop: "10px" } },
      t("library.limits", { size: fmt.bytes(u.max_file_bytes), formats: data.formats.join(", ") })));
  }

  function drawList() {
    const text = filter.value.trim().toLowerCase();
    const entries = data.entries.filter((entry) => !text || entry.title.toLowerCase().includes(text) || entry.filename.toLowerCase().includes(text));
    if (!data.entries.length) {
      fill(listBox, emptyState("folder", t("library.empty"), t("library.empty_hint")));
      return;
    }
    if (!entries.length) {
      fill(listBox, emptyState("search", t("library.no_match"), null));
      return;
    }
    fill(listBox, h("ol", { class: "list", style: { margin: 0, padding: 0 } }, entries.map((entry) => h("li", { class: "list-row" },
      h("div", { class: "thumb" }, icon("music")),
      h("div", { class: "text" },
        h("span", { class: "title", title: entry.filename }, entry.title),
        h("span", { class: "meta" },
          [entry.ext.toUpperCase(), fmt.bytes(entry.size), entry.uploader && entry.uploader.name, fmt.relative(entry.created_at)]
            .filter(Boolean).join(" · "))),
      entry.uploader ? avatar(entry.uploader.avatar, "avatar xs hide-sm") : null,
      h("span", { class: "time" }, entry.length ? fmt.duration(entry.length) : "—"),
      h("div", { class: "actions" },
        iconButton("play", t("library.play"), () => play({ ids: [entry.id] }, t("library.queued", { count: 1 })), "sm"),
        iconButton("queueNext", t("player.play_next"), () => play({ ids: [entry.id], next: true }, t("library.queued", { count: 1 })), "sm"),
        iconButton("edit", t("library.rename"), async () => {
          const title = await promptDialog({ title: t("library.rename"), label: entry.filename, value: entry.title, maxlength: 100 });
          if (!title || title === entry.title) return;
          try {
            await api("PATCH", `/api/guilds/${gid}/library/${entry.id}`, { title });
            entry.title = title;
            drawList();
          } catch (err) {
            fail(err);
          }
        }, "sm"),
        iconButton("trash", t("library.delete"), async () => {
          if (!await confirmDialog({ title: t("library.confirm_delete", { title: entry.title }), danger: true, confirm: t("library.delete") })) return;
          try {
            await api("DELETE", `/api/guilds/${gid}/library/${entry.id}`);
            toast(t("library.deleted"), "success");
            reload();
          } catch (err) {
            fail(err);
          }
        }, "sm danger"))))));
  }

  // Subidas de una en una (cada archivo se comprueba con Lavalink al llegar)
  const pending = [];
  let uploading = false;

  function queueFiles(files) {
    const allowed = new Set(data.formats);
    for (const file of files) {
      const ext = (file.name.split(".").pop() || "").toLowerCase();
      const row = { file, bar: meter(0, "", false), status: h("span", { class: "muted small" }, t("library.waiting")) };
      row.el = h("div", { class: "upload-item" }, h("span", { class: "ellipsis" }, file.name), row.status, row.bar);
      if (!allowed.has(ext)) {
        row.status.textContent = t("library.bad_format");
        row.status.className = "small";
        row.status.style.color = "var(--danger)";
      } else if (file.size > data.usage.max_file_bytes) {
        row.status.textContent = t("library.too_big", { size: fmt.bytes(data.usage.max_file_bytes) });
        row.status.className = "small";
        row.status.style.color = "var(--danger)";
      } else {
        pending.push(row);
      }
      uploads.append(row.el);
    }
    processQueue();
  }

  async function processQueue() {
    if (uploading) return;
    uploading = true;
    let done = 0;
    while (pending.length && scope.alive) {
      const row = pending.shift();
      row.status.textContent = t("library.uploading");
      const form = new FormData();
      form.append("file", row.file, row.file.name);
      try {
        const result = await uploadFile(`/api/guilds/${gid}/library`, form, (fraction) => {
          row.bar.firstChild.style.width = `${Math.round(fraction * 100)}%`;
          if (fraction >= 1) row.status.textContent = t("library.checking");
        });
        row.status.textContent = `${t("library.uploaded")} · ${result.length ? fmt.duration(result.length) : ""}`;
        row.status.style.color = "var(--success)";
        done++;
        setTimeout(() => row.el.remove(), 4000);
      } catch (err) {
        row.status.textContent = err.message;
        row.status.style.color = "var(--danger)";
      }
    }
    uploading = false;
    if (done && scope.alive) {
      toast(t("library.upload_done", { count: done }), "success");
      reload();
    }
  }

  const drop = h("div", {
    class: "dropzone", tabindex: 0, role: "button", "aria-label": t("library.drop"),
    onClick: () => fileInput.click(),
    onKeydown: (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); fileInput.click(); } },
    onDragover: (event) => { event.preventDefault(); drop.classList.add("over"); },
    onDragleave: () => drop.classList.remove("over"),
    onDrop: (event) => {
      event.preventDefault();
      drop.classList.remove("over");
      queueFiles([...event.dataTransfer.files]);
    },
  }, icon("upload", "icon-xl"), h("div", { class: "strong" }, t("library.drop")), h("div", { class: "small" }, t("library.drop_hint")));

  fill(root, 
    card({ title: t("library.upload_title"), iconName: "upload", sub: data.running ? null : t("library.not_running") },
      data.running ? drop : h("div", { class: "notice warn" }, icon("alert"), t("library.not_running_hint")),
      fileInput, uploads, usageBox),
    card({
      title: t("library.files_title"), iconName: "library",
      actions: [
        h("div", { style: { width: "200px" } }, filter),
        h("button", { class: "btn btn-sm btn-primary", onClick: () => play({ all: true }) }, icon("play", "icon-sm"), t("library.play_all")),
        h("button", { class: "btn btn-sm", onClick: () => play({ all: true, shuffle: true }) }, icon("shuffle", "icon-sm"), t("library.shuffle_all")),
      ],
    }, listBox));
  drawUsage();
  drawList();
}
