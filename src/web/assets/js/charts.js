/* charts.js —— ECharts 统一主题与常用图型；所有图表都走这里，方便一次性调风格 */
export const PALETTE = ['#c8102e', '#2563eb', '#0ea5a5', '#e8960c', '#7c5cff', '#12a06a', '#ec4899', '#64748b', '#0891b2', '#a16207'];
export const C = {
  red: '#c8102e', blue: '#2563eb', teal: '#0ea5a5', amber: '#e8960c',
  violet: '#7c5cff', green: '#12a06a', ink: '#0d1b31', ink2: '#3d4c63',
  ink3: '#8494ab', line: '#eef1f7', grid: '#eef1f7', slate: '#64748b',
};

const FONT = '"Inter","Segoe UI","Microsoft YaHei","PingFang SC",system-ui,sans-serif';

export const base = (extra = {}) => ({
  color: PALETTE,
  textStyle: { fontFamily: FONT, color: C.ink2, fontSize: 12 },
  animationDuration: 760,
  animationEasing: 'cubicOut',
  animationDurationUpdate: 420,
  grid: { left: 10, right: 16, top: 26, bottom: 6, containLabel: true },
  tooltip: {
    trigger: 'axis',
    backgroundColor: 'rgba(255,255,255,.98)',
    borderColor: '#e7ecf4',
    borderWidth: 1,
    padding: [9, 12],
    extraCssText: 'border-radius:10px;box-shadow:0 12px 32px -12px rgba(13,27,49,.28);',
    textStyle: { color: C.ink, fontSize: 12, fontFamily: FONT },
    axisPointer: { type: 'line', lineStyle: { color: '#cfd8e6', type: 'dashed' } },
  },
  ...extra,
});

export const xAxis = (data, opt = {}) => ({
  type: 'category',
  data,
  axisLine: { lineStyle: { color: '#e3e9f2' } },
  axisTick: { show: false },
  axisLabel: { color: C.ink3, fontSize: 11, margin: 10, ...opt },
});

export const yAxis = (opt = {}) => ({
  type: 'value',
  axisLine: { show: false },
  axisTick: { show: false },
  splitLine: { lineStyle: { color: C.grid, type: 'dashed' } },
  axisLabel: { color: C.ink3, fontSize: 11 },
  ...opt,
});

/* ------------------------------------------------------------------ 实例管理 */
const instances = new Map();

export function mount(el, option, { onEvents } = {}) {
  if (!el) return null;
  const chart = window.echarts.init(el, null, { renderer: 'canvas' });
  chart.setOption(option);
  instances.set(el, chart);
  if (onEvents) Object.entries(onEvents).forEach(([k, fn]) => chart.on(k, fn));
  const ro = new ResizeObserver(() => chart.resize());
  ro.observe(el);
  chart.__ro = ro;
  return chart;
}

export function disposeAll() {
  instances.forEach((c, el) => {
    try { c.__ro && c.__ro.disconnect(); c.dispose(); } catch (e) { /* noop */ }
    instances.delete(el);
  });
}

/** 迷你走势（SVG，用于 KPI 卡片，比挂 ECharts 轻） */
export function sparkline(values, { color = C.blue, height = 34, fill = true } = {}) {
  const vals = (values || []).filter((v) => typeof v === 'number' && Number.isFinite(v));
  if (vals.length < 2) return `<div style="height:${height}px"></div>`;
  const w = 160, h = height, pad = 2;
  const mn = Math.min(...vals), mx = Math.max(...vals);
  const span = mx - mn || 1;
  const X = (i) => pad + (i * (w - pad * 2)) / (vals.length - 1);
  const Y = (v) => h - pad - ((v - mn) / span) * (h - pad * 2);
  const line = vals.map((v, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join(' ');
  const area = `${line} L${X(vals.length - 1).toFixed(1)},${h} L${pad},${h} Z`;
  const id = `sg${Math.random().toString(36).slice(2, 8)}`;
  return `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" preserveAspectRatio="none">
    <defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="${color}" stop-opacity=".22"/>
      <stop offset="1" stop-color="${color}" stop-opacity="0"/>
    </linearGradient></defs>
    ${fill ? `<path d="${area}" fill="url(#${id})"/>` : ''}
    <path d="${line}" fill="none" stroke="${color}" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${X(vals.length - 1)}" cy="${Y(vals[vals.length - 1])}" r="2.6" fill="#fff" stroke="${color}" stroke-width="1.8"/>
  </svg>`;
}

/* ------------------------------------------------------------------ 预设图型 */

/** 头尾突出：取前 top 与后 bottom，中间用一行省略号代替 */
export function splitRank(rows, { top = 6, bottom = 6, unit = '个' } = {}) {
  if (rows.length <= top + bottom + 1) return rows;
  const mid = rows.length - top - bottom;
  return [
    ...rows.slice(0, top).map((r) => ({ ...r, tone: 'top' })),
    { name: `⋯ 中间 ${mid} ${unit} ⋯`, value: null, sep: true },
    ...rows.slice(-bottom).map((r) => ({ ...r, tone: 'bottom' })),
  ];
}

export function barRank(rows, { color = C.blue, unit = '', decimals = 0, max = null, hideLabel = false } = {}) {
  const names = rows.map((r) => r.name);
  const vals = rows.map((r) => (r.value === null || r.value === undefined ? null : Number(r.value)));
  const num = vals.filter((v) => v !== null);
  const mxPos = max ?? Math.max(0, ...num);
  const mnNeg = Math.min(0, ...num);

  // 负值一侧要给"数字标签"留出位置，否则负值很小时（例如 +15288 / −497），
  // 负条只有几像素长，标签会被挤到坐标轴上、盖住支行名（私银资产较年初踩过）。
  // 规则：负侧至少留 35% 的负值幅度，且不小于正值幅度的 10%；两者取大。
  // 负值本来就很大的图（正负同量级）算出来仍等于原来的 *1.35，视觉不变。
  const negPad = mnNeg
    ? Math.max(Math.abs(mnNeg) * 0.35, (mxPos || 0) * 0.10)
    : 0;

  return base({
    grid: { left: 10, right: 52, top: 8, bottom: 6, containLabel: true },
    tooltip: {
      ...base().tooltip,
      formatter: (p) => {
        const row = rows[p[0].dataIndex] || {};
        const txt = row.text || `${Number(p[0].value).toLocaleString('zh-CN', { maximumFractionDigits: decimals })}${unit}`;
        return `${p[0].name}<br/><b>${txt}</b>`;
      },
    },
    xAxis: {
      ...yAxis({ max: (mxPos || 1) * 1.04, min: mnNeg ? mnNeg - negPad : 0, show: false }),
    },
    yAxis: {
      ...xAxis(names), inverse: true, axisLine: { show: false },
      axisLabel: {
        color: C.ink2, fontSize: 11,
        formatter: (v) => (String(v).startsWith('⋯') ? `{sep|${v}}` : v),
        rich: { sep: { color: '#aab6c8', fontSize: 10, fontStyle: 'italic' } },
      },
    },
    series: [{
      type: 'bar',
      data: rows.map((r) => {
        const v = r.value === null || r.value === undefined ? null : Number(r.value);
        const neg = v !== null && v < 0;
        const bottom = r.tone === 'bottom';
        return {
          value: v,
          label: { position: neg ? 'left' : 'right', color: r.color || C.ink2 },
          itemStyle: {
            borderRadius: neg ? [5, 0, 0, 5] : [0, 5, 5, 0],
            color: v === null ? 'transparent'
              : r.color                                          // 行内指定颜色（如头尾高亮）
                ? r.color
                : neg ? C.green
                  : new window.echarts.graphic.LinearGradient(0, 0, 1, 0, [
                    { offset: 0, color: color + (bottom ? '25' : 'aa') },
                    { offset: 1, color: bottom ? color + '66' : color }]),
          },
        };
      }),
      barWidth: '58%',
      label: {
        show: !hideLabel, fontSize: 11, color: C.ink2,
        formatter: (p) => {
          const row = rows[p.dataIndex] || {};
          if (row.text) return row.text;           // 行内自定义文案（如"1 名 · 1.0 分"）
          return p.value === null ? '' : p.value.toLocaleString('zh-CN', { maximumFractionDigits: decimals }) + unit;
        },
      },
      markLine: mnNeg < 0 ? {
        silent: true, symbol: 'none',
        lineStyle: { color: '#d6deea', type: 'solid', width: 1 },
        label: { show: false },
        data: [{ xAxis: 0 }],
      } : undefined,
    }],
  });
}

export function lineTrend(x, series, { unit = '', area = true, yMax = null, yMin = null, marks = [] } = {}) {
  return base({
    xAxis: xAxis(x, { axisLabel: { color: C.ink3, fontSize: 11, margin: 12 } }),
    yAxis: yAxis({ max: yMax, min: yMin, scale: true }),
    series: series.map((s, i) => ({
      name: s.name,
      type: 'line',
      smooth: 0.35,
      symbol: 'circle',
      symbolSize: 5,
      showSymbol: x.length <= 16,
      data: s.data,
      lineStyle: { width: 2.2, color: s.color || PALETTE[i] },
      itemStyle: { color: s.color || PALETTE[i], borderWidth: 1.5, borderColor: '#fff' },
      areaStyle: area && series.length === 1 ? {
        color: new window.echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: (s.color || PALETTE[i]) + '33' },
          { offset: 1, color: (s.color || PALETTE[i]) + '00' }]),
      } : undefined,
      markLine: i === 0 && marks.length ? {
        silent: true, symbol: 'none',
        lineStyle: { color: C.red, type: 'dashed', width: 1 },
        label: { color: C.red, fontSize: 10, formatter: (p) => p.name },
        data: marks.map((m) => ({ yAxis: m.value, name: m.label })),
      } : undefined,
      endLabel: series.length === 1 ? { show: true, color: C.ink2, fontSize: 11, formatter: (p) => `${p.value}${unit}` } : undefined,
    })),
  });
}

export function stackedBar(x, series, { unit = '' } = {}) {
  return base({
    legend: { top: 0, right: 0, icon: 'roundRect', itemWidth: 8, itemHeight: 8, textStyle: { color: C.ink3, fontSize: 11 } },
    grid: { left: 10, right: 16, top: 34, bottom: 6, containLabel: true },
    xAxis: xAxis(x),
    yAxis: yAxis(),
    series: series.map((s, i) => ({
      name: s.name, type: 'bar', stack: 'a', data: s.data, barWidth: '46%',
      itemStyle: { color: s.color || PALETTE[i], borderRadius: i === series.length - 1 ? [4, 4, 0, 0] : 0 },
      emphasis: { focus: 'series' },
    })),
  });
}

export function scatter(points, { xName = '', yName = '', unit = '', branches = [],
  xUnit = '%', yUnit = '%', sizeName = '到店客群', sizeUnit = '户', showSize = true,
  yFmt = '' } = {}) {
  const groups = {};
  points.forEach((p) => { (groups[p.branch] = groups[p.branch] || []).push(p); });
  return base({
    legend: { top: 0, right: 0, icon: 'circle', itemWidth: 8, itemHeight: 8, textStyle: { color: C.ink3, fontSize: 11 } },
    grid: { left: 10, right: 18, top: 40, bottom: 26, containLabel: true },
    tooltip: {
      ...base().tooltip, trigger: 'item',
      formatter: (p) => `<b>${p.data.name}</b><br/>${xName} ${p.data.x}${xUnit} · ${yName} ${p.data.y}${yUnit}`
        + (showSize ? `<br/>${sizeName} ${p.data.size}${sizeUnit}` : ''),
    },
    xAxis: { ...yAxis(), name: xName, nameLocation: 'middle', nameGap: 30,
      nameTextStyle: { color: C.ink3, fontSize: 11 }, scale: true },
    yAxis: { ...yAxis(), name: yName, nameLocation: 'middle', nameGap: 34,
      nameTextStyle: { color: C.ink3, fontSize: 11 }, scale: true,
      axisLabel: { color: C.ink3, fontSize: 10, formatter: yFmt ? `{value}${yFmt}` : '{value}' } },
    series: Object.entries(groups).map(([br, ps], i) => ({
      name: br, type: 'scatter',
      data: ps.map((p) => ({ ...p, value: [p.x, p.y, p.size] })),
      symbolSize: (v) => Math.max(8, Math.min(30, Math.sqrt((v && v[2]) || 1) / 2.2)),
      itemStyle: { color: PALETTE[i % PALETTE.length], opacity: 0.78, borderColor: '#fff', borderWidth: 1 },
      emphasis: { itemStyle: { opacity: 1, shadowBlur: 12, shadowColor: 'rgba(13,27,49,.25)' } },
    })),
  });
}

export function radar(indicators, series) {
  return base({
    legend: { top: 0, right: 0, icon: 'roundRect', itemWidth: 8, itemHeight: 8, textStyle: { color: C.ink3, fontSize: 11 } },
    tooltip: { ...base().tooltip, trigger: 'item' },
    radar: {
      indicator: indicators,
      radius: '62%',
      center: ['50%', '56%'],
      splitNumber: 4,
      axisName: { color: C.ink3, fontSize: 10.5 },
      splitLine: { lineStyle: { color: '#e9eef6' } },
      splitArea: { areaStyle: { color: ['#fbfcfe', '#ffffff'] } },
      axisLine: { lineStyle: { color: '#e9eef6' } },
    },
    series: [{
      type: 'radar',
      symbolSize: 4,
      data: series.map((s, i) => ({
        name: s.name, value: s.value,
        lineStyle: { width: 2, color: s.color || PALETTE[i] },
        itemStyle: { color: s.color || PALETTE[i] },
        areaStyle: { opacity: s.opacity ?? 0.12, color: s.color || PALETTE[i] },
      })),
    }],
  });
}

export function waterfall(categories, values, { unit = '' } = {}) {
  // 简易瀑布：起点、增量（正负）、终点
  const start = values[0];
  const inc = values[1];
  const end = values[2];
  return base({
    tooltip: { ...base().tooltip, formatter: (p) => `${p.name}<br/><b>${Number(p.value).toLocaleString('zh-CN', { maximumFractionDigits: 2 })}</b>${unit}` },
    xAxis: xAxis(categories),
    yAxis: yAxis({ min: (v) => Math.min(v.min * 0.98, start * 0.985), max: end * 1.004 }),
    series: [
      { name: 'base', type: 'bar', stack: 'w', itemStyle: { color: 'transparent' }, data: [0, Math.min(start, end), 0], silent: true },
      {
        type: 'bar', stack: 'w', barWidth: '46%',
        data: [
          { value: start, itemStyle: { color: '#c7d2e4', borderRadius: [5, 5, 0, 0] } },
          { value: Math.abs(inc), itemStyle: { color: inc >= 0 ? C.red : C.green, borderRadius: 5 } },
          { value: end, itemStyle: { color: C.blue, borderRadius: [5, 5, 0, 0] } },
        ],
        label: {
          show: true, position: 'top', color: C.ink2, fontSize: 11, fontWeight: 600,
          formatter: (p) => Number(p.value).toLocaleString('zh-CN', { maximumFractionDigits: 2 }),
        },
      },
    ],
  });
}

export function histogram(labels, counts, { unit = '', markValue = null } = {}) {
  return base({
    tooltip: { ...base().tooltip, formatter: (p) => `${p[0].name}<br/><b>${p[0].value}</b> 个网点` },
    xAxis: xAxis(labels, { axisLabel: { color: C.ink3, fontSize: 10, interval: 0, rotate: labels.length > 5 ? 16 : 0 } }),
    yAxis: yAxis({ minInterval: 1 }),
    series: [{
      type: 'bar', data: counts, barWidth: '62%',
      itemStyle: {
        borderRadius: [5, 5, 0, 0],
        color: new window.echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: '#4f7ff0' }, { offset: 1, color: '#a9c1f7' }]),
      },
      label: { show: true, position: 'top', color: C.ink3, fontSize: 10.5 },
      markLine: markValue ? {
        silent: true, symbol: 'none', lineStyle: { color: C.red, type: 'dashed' },
        label: { formatter: `目标 ${markValue}${unit}`, color: C.red, fontSize: 10 },
        data: [{ xAxis: markValue }],
      } : undefined,
    }],
  });
}
