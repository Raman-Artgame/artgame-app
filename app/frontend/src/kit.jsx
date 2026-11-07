import React, { useEffect, useState } from 'react'
import { api } from './api.js'

// «Сбор на объект» (HEAD 07.11): чек-лист выезда росписи и печати. Взял → вернул → состояние → «Сдать проект».
// Аэрозоль — номер цвета и штук, фасадная — общие литры, остальное количеством. Собирают Главный, Про, Мастер печати, ГИП.
const ZT = { mural: 'Роспись', print: 'Печать' }
const n = v => (v === null || v === undefined ? '' : String(v))
const num = s => s.replace(',', '.').replace(/[^\d.]/g, '')

export function Kit() {
  const [list, setList] = useState(null)
  const [open, setOpen] = useState(null)
  const [e, setE] = useState('')
  const load = () => api('/kit').then(setList, x => setE(x.message))
  useEffect(() => { load() }, [])
  if (open) return <KitCard key={open.id + open.zone} {...open} back={() => { setOpen(null); load() }} />
  if (e) return <div className="card muted">{e}</div>
  if (!list) return <div className="card muted">Загрузка…</div>
  return <div className="card">
    <h2>Сбор на объект</h2>
    <p className="small muted">Перед выездом отметь, что взяли; после — что вернули и в каком состоянии. «Сдать проект» закрывает список.</p>
    {list.objects.filter(o => o.id).map(o => <div key={o.id} className="row">
      <div><b>{o.title}</b><div className="small muted">{o.city}</div></div>
      <div className="qbtns">{list.zones.map(z => {
        const k = o.lists[z]
        return <button key={z} className="ghost mini" onClick={() => setOpen({ id: o.id, zone: z })}>
          {ZT[z]}{k ? (k.status === 'closed' ? ' · сдан' : ' · собирается') : o.can_edit ? ' · собрать' : ''}</button>
      })}</div>
    </div>)}
    {!list.objects.filter(o => o.id).length && <p className="small muted">Активных объектов нет.</p>}
  </div>
}

function KitCard({ id, zone, back }) {
  const [d, setD] = useState(null)
  const [it, setIt] = useState(null)
  const [msg, setMsg] = useState('')
  const [dirty, setDirty] = useState(false)
  useEffect(() => {
    api(`/kit/${id}/${zone}`).then(r => {
      setD(r)
      const x = r.list?.items || {}
      setIt({ aerosol: x.aerosol || [], facade: x.facade || { taken: null, returned: null }, mat: x.mat || {}, extra: x.extra || [],
        obr: x.obr || {}, ras: x.ras || {}, pre: x.pre || [], post: x.post || [] })
    }, ex => setMsg(ex.message))
  }, [])
  if (!d || !it) return <div className="card muted">{msg || 'Загрузка…'}</div>
  const ro = !d.can_edit
  const k = d.dict
  const up = (key, v) => { setIt({ ...it, [key]: v }); setDirty(true) }
  const save = () => api(`/kit/${id}/${zone}`, { method: 'POST', body: { items: it } }).then(() => { setMsg('Сохранено.'); setDirty(false) }, ex => setMsg(ex.message))
  const close = async () => {
    if (dirty) await api(`/kit/${id}/${zone}`, { method: 'POST', body: { items: it } })
    api(`/kit/${id}/${zone}/close`, { method: 'POST' }).then(r => { setD({ ...d, can_edit: false, usage: r.usage, list: { ...d.list, status: 'closed' } }); setDirty(false); setMsg('Проект сдан.'); window.scrollTo(0, 0) },
      ex => setMsg(ex.message))
  }
  const qty = (r, set, unit) => <span className="kitq">
    <input inputMode="decimal" disabled={ro} placeholder="взял" value={n(r?.taken)} onChange={e => set({ ...r, taken: num(e.target.value) })} />
    <input inputMode="decimal" disabled={ro} placeholder="вернул" value={n(r?.returned)} onChange={e => set({ ...r, returned: num(e.target.value) })} />
    <i className="small muted">{unit}</i></span>
  const checks = (title, key, items) => <><h3>{title}</h3>{items.map((t, i) =>
    <label key={i} className="check"><input type="checkbox" disabled={ro} checked={!!it[key][i]}
      onChange={e => { const a = [...it[key]]; a[i] = e.target.checked; up(key, a) }} />{t}</label>)}</>
  return <div className="card kit">
    <div className="head"><h2>{d.object.title} · {ZT[zone]}</h2><button className="ghost mini" onClick={back}>Назад</button></div>
    {d.list?.status === 'closed' && <p className="small why">Проект сдан — список только для чтения.</p>}
    {ro && d.list?.status !== 'closed' && <p className="small muted">Список ведёт Главный художник, Художник-Про, Мастер печати или ГИП объекта.</p>}
    {d.usage && <div className="warnbox small">
      <b>Расход по проекту</b>
      {d.usage.aerosol.length > 0 && <div>Аэрозоль: {d.usage.aerosol.map(a => `${a.color} — ${a.used}`).join(', ')} (всего {d.usage.aerosol_total} шт)</div>}
      {d.usage.facade_l != null && <div>Фасадная: {d.usage.facade_l} л</div>}
      {Object.entries(d.usage.mat).filter(([, v]) => v).map(([c, v]) => <div key={c}>{(k.mat.find(m => m.code === c) || {}).title || c}: {v}</div>)}
      {d.usage.lost.length > 0 && <div>Не вернули: {d.usage.lost.map(c => (k.obr.find(o => o.code === c) || {}).title || c).join(', ')}</div>}
    </div>}
    {checks('Перед выездом', 'pre', k.pre)}
    {k.aerosol && <><h3>Аэрозоль <span className="small muted">номер цвета — штук</span></h3>
      {it.aerosol.map((r, i) => <div key={i} className="kitrow">
        <input disabled={ro} placeholder="номер цвета" value={r.color} onChange={e => { const a = [...it.aerosol]; a[i] = { ...r, color: e.target.value }; up('aerosol', a) }} />
        {qty(r, v => { const a = [...it.aerosol]; a[i] = v; up('aerosol', a) }, 'шт')}
        {!ro && <button className="ghost mini" aria-label="Убрать" onClick={() => up('aerosol', it.aerosol.filter((_, j) => j !== i))}>✕</button>}
      </div>)}
      {!ro && <button className="ghost mini" onClick={() => up('aerosol', [...it.aerosol, { color: '', taken: '' }])}>+ цвет</button>}</>}
    {k.facade && <><h3>Фасадная краска <span className="small muted">общие литры</span></h3>
      <div className="kitrow"><span>Всего</span>{qty(it.facade, v => up('facade', v), 'л')}</div></>}
    <h3>Материалы</h3>
    {k.mat.map(m => <div key={m.code} className="kitrow"><span>{m.title}</span>{qty(it.mat[m.code], v => up('mat', { ...it.mat, [m.code]: v }), m.unit)}</div>)}
    {it.extra.map((r, i) => <div key={'x' + i} className="kitrow">
      <input disabled={ro} placeholder="что ещё" value={r.title} onChange={e => { const a = [...it.extra]; a[i] = { ...r, title: e.target.value }; up('extra', a) }} />
      {qty(r, v => { const a = [...it.extra]; a[i] = v; up('extra', a) }, r.unit || 'шт')}</div>)}
    {!ro && <button className="ghost mini" onClick={() => up('extra', [...it.extra, { title: '', unit: 'шт', taken: '' }])}>+ позиция</button>}
    <h3>Оборудование <span className="small muted">взял · состояние · вернул · состояние</span></h3>
    {k.obr.map(o => { const r = it.obr[o.code] || {}; const set = v => up('obr', { ...it.obr, [o.code]: { ...r, ...v } })
      return <div key={o.code} className="kitobr">
        <label className="check"><input type="checkbox" disabled={ro} checked={!!r.took} onChange={e => set({ took: e.target.checked })} />{o.title}</label>
        {r.took && <div className="kitq">
          <select disabled={ro} value={r.state_out || ''} onChange={e => set({ state_out: e.target.value })}><option value="">взял: состояние</option>{k.states.map(s => <option key={s}>{s}</option>)}</select>
          <label className="check small"><input type="checkbox" disabled={ro} checked={!!r.back} onChange={e => set({ back: e.target.checked })} />вернул</label>
          <select disabled={ro} value={r.state_in || ''} onChange={e => set({ state_in: e.target.value })}><option value="">после</option>{k.states.map(s => <option key={s}>{s}</option>)}</select>
        </div>}
      </div> })}
    <h3>Расходники</h3>
    {k.ras.map(r => <label key={r.code} className="check"><input type="checkbox" disabled={ro} checked={!!it.ras[r.code]} onChange={e => up('ras', { ...it.ras, [r.code]: e.target.checked })} />{r.title}</label>)}
    {checks('После объекта', 'post', k.post)}
    {msg && <p className="small muted">{msg}</p>}
    {!ro && <div className="seg"><button className="ghost" onClick={save}>Сохранить</button><button onClick={close}>Сдать проект</button></div>}
  </div>
}
