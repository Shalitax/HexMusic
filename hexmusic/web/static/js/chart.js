// Gráfico de columnas (una serie) en SVG: barras finas, tooltip al pasar o enfocar y vista de tabla.
"use strict";

import { fill, fmt, h, state, svg, t } from "./core.js";

const MAX_W = 720;
const PAD = { top: 14, right: 8, bottom: 26, left: 36 };
const BAR_MAX = 24;
const RADIUS = 4;

function niceMax(value) {
  if (value <= 4) return 4;
  const power = 10 ** Math.floor(Math.log10(value));
  for (const step of [1, 2, 2.5, 5, 10]) {
    if (step * power >= value) return step * power;
  }
  return 10 * power;
}

/** Barra con el extremo de datos redondeado y la base recta. */
function barPath(x, y, width, height) {
  const r = Math.min(RADIUS, height, width / 2);
  const bottom = y + height;
  return `M${x},${bottom} V${y + r} Q${x},${y} ${x + r},${y} H${x + width - r} Q${x + width},${y} ${x + width},${y + r} V${bottom} Z`;
}

/** Días del rango con 0 reproducciones incluidos. ``daily`` viene agrupado por día local (tz del navegador). */
export function fillDays(daily, days) {
  const tzSeconds = -new Date().getTimezoneOffset() * 60;
  const today = Math.floor((Date.now() / 1000 + tzSeconds) / 86400);
  const byDay = new Map(daily.map((item) => [item.day, item.plays]));
  const points = [];
  for (let day = today - days + 1; day <= today; day++) {
    // Mediodía del día local, para mostrar la fecha sin saltos de zona horaria
    const date = new Date((day * 86400 - tzSeconds + 43200) * 1000);
    points.push({ day, date, value: byDay.get(day) || 0 });
  }
  return points;
}

export function barChart(points, { valueLabel }) {
  const wrap = h("div", { class: "chart" });
  const tip = h("div", { class: "chart-tip", hidden: true });
  const max = niceMax(Math.max(1, ...points.map((p) => p.value)));
  // En pantallas estrechas el SVG se dibuja más estrecho en lugar de escalarse (si no, el texto quedaría diminuto)
  const W = window.innerWidth < 900 ? Math.max(300, Math.min(MAX_W, window.innerWidth - 72)) : MAX_W;
  const H = W < 500 ? 200 : 230;
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const band = plotW / points.length;
  // La barra nunca llena su franja: el resto es aire entre columnas
  const barW = Math.max(2, Math.min(BAR_MAX, band * 0.62));
  const short = new Intl.DateTimeFormat(state.lang, { day: "numeric", month: "short" });
  const long = new Intl.DateTimeFormat(state.lang, { weekday: "long", day: "numeric", month: "long" });
  const maxLabels = Math.max(2, Math.floor(plotW / 62));
  const every = Math.ceil(points.length / maxLabels);

  const grid = [];
  for (let i = 0; i <= 4; i++) {
    const value = (max / 4) * i;
    const y = PAD.top + plotH - (value / max) * plotH;
    grid.push(svg("line", { class: "grid-line", x1: PAD.left, x2: W - PAD.right, y1: y, y2: y }));
    grid.push(svg("text", { class: "axis-label", x: PAD.left - 8, y: y + 4, "text-anchor": "end" }, fmt.compact(value)));
  }

  const show = (point, x, y) => {
    fill(tip, h("strong", null, fmt.number(point.value)), h("span", { class: "muted" }, `${valueLabel} · ${long.format(point.date)}`));
    const rect = svgEl.getBoundingClientRect();
    const scale = rect.width / W;
    tip.style.left = `${x * scale}px`;
    tip.style.top = `${y * scale}px`;
    tip.hidden = false;
  };
  const hide = () => { tip.hidden = true; };

  const bars = points.map((point, i) => {
    const cx = PAD.left + band * i + band / 2;
    const height = point.value ? Math.max(2, (point.value / max) * plotH) : 0;
    const y = PAD.top + plotH - height;
    const label = i % every === (points.length - 1) % every
      ? svg("text", { class: "axis-label", x: cx, y: H - 8, "text-anchor": "middle" }, short.format(point.date))
      : null;
    const hit = svg("rect", {
      class: "bar-hit", x: PAD.left + band * i, y: PAD.top, width: band, height: plotH, tabindex: 0,
      role: "img", "aria-label": `${long.format(point.date)}: ${point.value} ${valueLabel}`,
      onPointerenter: () => show(point, cx, Math.min(y, PAD.top + plotH - 4)),
      onPointerleave: hide,
      onFocus: () => show(point, cx, Math.min(y, PAD.top + plotH - 4)),
      onBlur: hide,
    });
    const bar = height ? svg("path", { class: "bar", d: barPath(cx - barW / 2, y, barW, height) }) : svg("g");
    return [hit, bar, label];
  });

  const svgEl = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "group", "aria-label": valueLabel },
    grid, svg("line", { class: "grid-line", x1: PAD.left, x2: W - PAD.right, y1: PAD.top + plotH, y2: PAD.top + plotH }), bars);
  wrap.append(svgEl, tip);
  return wrap;
}

/** Tabla equivalente al gráfico (accesible sin pasar el ratón). */
export function chartTable(points, valueLabel) {
  const long = new Intl.DateTimeFormat(state.lang, { weekday: "short", day: "numeric", month: "short" });
  return h("div", { class: "table-wrap", style: { maxHeight: "300px", overflowY: "auto" } },
    h("table", { class: "table" },
      h("thead", null, h("tr", null, h("th", null, t("history.day")), h("th", { class: "num" }, valueLabel))),
      h("tbody", null, [...points].reverse().map((point) => h("tr", null,
        h("td", null, long.format(point.date)), h("td", { class: "num" }, fmt.number(point.value)))))));
}
