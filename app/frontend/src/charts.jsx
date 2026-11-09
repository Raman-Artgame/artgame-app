import React, { useState } from 'react'

// Графики без библиотек (HEAD 09.11: «финансы с диаграммами, как в артефакте»): SVG, тёмная тема, подписи по-русски.
const M = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']
export const mln = x => x == null ? '—' : Math.abs(x) >= 1e6 ? (x / 1e6).toFixed(Math.abs(x) >= 1e8 ? 0 : 1).replace('.', ',') + ' млн' :
  Math.abs(x) >= 1e3 ? Math.round(x / 1e3) + ' тыс' : Math.round(x) + ''
export const PALETTE = ['#E60041', '#3DDC97', '#F3C38A', '#7FA8FF', '#C58CFF', '#9C97A0', '#FF8A5C', '#5CD3E6']

// Столбцы «выручка / расходы» по месяцам + линия прибыли; тап по месяцу — цифры месяца
export function MonthBars({ months, onPick, picked }) {
  const W = 340, H = 180, P = 22, n = months.length || 1
  const max = Math.max(1, ...months.map(m => Math.max(m.net || 0, m.spent || 0)))
  const min = Math.min(0, ...months.map(m => m.profit || 0))
  const span = max - min, y = v => P + (H - 2 * P) * (1 - (v - min) / span), bw = (W - 2 * P) / n
  const pts = months.map((m, i) => m.profit == null ? null : `${P + bw * i + bw / 2},${y(m.profit)}`).filter(Boolean).join(' ')
  return <svg className="chart" viewBox={`0 0 ${W} ${H + 14}`} role="img" aria-label="Выручка, расходы и прибыль по месяцам">
    {[0, .5, 1].map(k => <line key={k} x1={P} x2={W - P} y1={y(min + span * k)} y2={y(min + span * k)} className="grid" />)}
    {min < 0 && <line x1={P} x2={W - P} y1={y(0)} y2={y(0)} className="zero" />}
    {months.map((m, i) => {
      const x = P + bw * i, on = picked === m.month
      return <g key={m.month} onClick={() => onPick?.(m.month)} style={{ cursor: 'pointer' }}>
        <rect x={x} y={P} width={bw} height={H - 2 * P} fill="transparent" />
        {on && <rect x={x + 1} y={P - 6} width={bw - 2} height={H - 2 * P + 12} rx="6" className="pick" />}
        <rect x={x + bw * .14} y={y(Math.max(m.net || 0, 0))} width={bw * .34} height={Math.max(0, y(0) - y(m.net || 0))} rx="2" className={'b-rev' + (m.estimate ? ' est' : '')} />
        <rect x={x + bw * .52} y={y(m.spent || 0)} width={bw * .34} height={Math.max(0, y(0) - y(m.spent || 0))} rx="2" className="b-cost" />
        <text x={x + bw / 2} y={H + 10} className="ax">{M[+m.month.slice(5) - 1]}</text>
      </g>
    })}
    {pts && <polyline points={pts} className="l-profit" />}
    {months.map((m, i) => m.profit != null && <circle key={i} cx={P + bw * i + bw / 2} cy={y(m.profit)} r="2.6" className="d-profit" />)}
    <text x={P} y={P - 8} className="ax l">{mln(max)}</text>
  </svg>
}

// Кольцо структуры: доли и легенда с суммами
export function Donut({ parts, label }) {
  const total = parts.reduce((a, p) => a + Math.max(0, p.v), 0) || 1
  let a0 = -Math.PI / 2
  const R = 52, r = 34, cx = 60, cy = 60
  const arc = (a1, a2) => {
    const L = a2 - a1 > Math.PI ? 1 : 0, p = (rr, a) => `${cx + rr * Math.cos(a)} ${cy + rr * Math.sin(a)}`
    return `M${p(R, a1)} A${R} ${R} 0 ${L} 1 ${p(R, a2)} L${p(r, a2)} A${r} ${r} 0 ${L} 0 ${p(r, a1)} Z`
  }
  return <div className="donut">
    <svg viewBox="0 0 120 120" role="img" aria-label={label}>
      {parts.filter(p => p.v > 0).map((p, i) => { const a1 = a0, a2 = a0 + Math.max(0.0001, p.v / total) * Math.PI * 2 * .9999; a0 = a2
        return <path key={p.t} d={arc(a1, a2)} fill={p.c || PALETTE[i % PALETTE.length]} /> })}
      <text x="60" y="57" className="dc-v">{mln(total)}</text><text x="60" y="71" className="dc-l">{label}</text>
    </svg>
    <div className="dlegend">{parts.filter(p => p.v > 0).map((p, i) => <div key={p.t}><i style={{ background: p.c || PALETTE[i % PALETTE.length] }} />
      <span>{p.t}</span><b>{mln(p.v)}</b><em>{Math.round(p.v / total * 100)}%</em></div>)}</div>
  </div>
}

// Горизонтальные полосы (города, статьи)
export function HBars({ rows }) {
  const max = Math.max(1, ...rows.map(r => r.v))
  return <div className="hbars">{rows.map((r, i) => <div key={r.t} className="hb">
    <span className="hb-t">{r.t}</span><span className="hb-bar"><i style={{ width: Math.max(2, r.v / max * 100) + '%', background: r.c || PALETTE[i % PALETTE.length] }} /></span>
    <b>{mln(r.v)}</b></div>)}</div>
}

// Мини-линия для Пульта
export function Spark({ values, className = '' }) {
  const v = values.filter(x => x != null)
  if (v.length < 2) return null
  const max = Math.max(...v), min = Math.min(0, ...v), W = 120, H = 32
  const pts = values.map((x, i) => x == null ? null : `${(i / (values.length - 1)) * W},${H - 2 - (x - min) / (max - min || 1) * (H - 4)}`).filter(Boolean).join(' ')
  return <svg className={"spark " + className} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true"><polyline points={pts} /></svg>
}

export function useToggle(init) { const [v, s] = useState(init); return [v, () => s(!v)] }
