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
  const objs = list.objects.filter(o => o.id)
  return <>
    <div className="card dark prodhead"><span className="kick">Сбор и сдача</span><h2>Что берём на объект</h2>
      <p className="small muted">Три шага: взяли → вернули → сдали. Отметки сохраняются, видно всей команде объекта.</p></div>
    {objs.map(o => <div key={o.id} className="card kitobj">
      <div><b>№{o.id} · {o.title}</b><div className="small muted">{o.city}</div></div>
      <div className="kitzones">{list.zones.map(z => {
        const k = o.lists[z]
        const st = k ? (k.status === 'closed' ? ['сдан', 'ok'] : ['собирается', 'warn']) : [o.can_edit ? 'начать сбор' : 'не начат', '']
        return <button key={z} className="ghost" onClick={() => setOpen({ id: o.id, zone: z })}>
          <span>{ZT[z]}</span><span className={'badge ' + st[1]}>{st[0]}</span></button>
      })}</div>
    </div>)}
    {!objs.length && <div className="card small muted">Объектов в работе нет.</div>}
  </>
}

// Счётчик «− 3 +»: на объекте в перчатках проще жать, чем печатать.
function Step({ value, set, ro, unit, ph }) {
  const v = value === '' || value == null ? '' : String(value)
  const add = d => set(String(Math.max(0, Math.round(((parseFloat(v) || 0) + d) * 10) / 10)))
  return <span className="stepper">
    {!ro && <button type="button" className="ghost" aria-label="меньше" onClick={() => add(-1)}>−</button>}
    <input inputMode="decimal" disabled={ro} placeholder={ph || '0'} value={v} onChange={e => set(num(e.target.value))} />
    {!ro && <button type="button" className="ghost" aria-label="больше" onClick={() => add(1)}>+</button>}
    <i>{unit}</i></span>
}

function Tap({ on, ro, set, children, sub }) {
  return <button type="button" className={'tap' + (on ? ' on' : '')} disabled={ro} onClick={() => set(!on)}>
    <span className="box">{on ? '✓' : ''}</span><span className="t">{children}{sub && <i>{sub}</i>}</span></button>
}

const STEPS = [['take', '1 · Взяли'], ['back', '2 · Вернули'], ['done', '3 · Сдать']]

function KitCard({ id, zone, back }) {
  const [d, setD] = useState(null)
  const [it, setIt] = useState(null)
  const [msg, setMsg] = useState('')
  const [dirty, setDirty] = useState(false)
  const [step, setStep] = useState('take')
  useEffect(() => {
    api(`/kit/${id}/${zone}`).then(r => {
      setD(r)
      const x = r.list?.items || {}
      setIt({ aerosol: x.aerosol || [], facade: x.facade || { taken: null, returned: null }, mat: x.mat || {}, extra: x.extra || [],
        obr: x.obr || {}, ras: x.ras || {}, pre: x.pre || [], post: x.post || [] })
      if (r.list?.status === 'closed') setStep('done')
    }, ex => setMsg(ex.message))
  }, [])
  useEffect(() => { if (!dirty) return undefined; const t = setTimeout(() => save(true), 1500); return () => clearTimeout(t) }, [it, dirty])
  if (!d || !it) return <div className="card muted">{msg || 'Загрузка…'}</div>
  const ro = !d.can_edit
  const k = d.dict
  const up = (key, v) => { setIt({ ...it, [key]: v }); setDirty(true) }
  function save(auto) { return api(`/kit/${id}/${zone}`, { method: 'POST', body: { items: it } }).then(() => { setMsg(auto ? 'Сохранено' : 'Сохранено.'); setDirty(false) }, ex => setMsg(ex.message)) }
  const close = async () => {
    if (!confirm('Сдать проект? После этого список нельзя менять, расход посчитается.')) return
    if (dirty) await api(`/kit/${id}/${zone}`, { method: 'POST', body: { items: it } })
    api(`/kit/${id}/${zone}/close`, { method: 'POST' }).then(r => { setD({ ...d, can_edit: false, usage: r.usage, list: { ...d.list, status: 'closed' } }); setDirty(false); setMsg('Проект сдан.'); window.scrollTo(0, 0) },
      ex => setMsg(ex.message))
  }
  const has = r => r && r.taken !== '' && r.taken != null && +r.taken > 0
  // что взяли — для шага «Вернули» и итога
  const taken = [
    ...it.aerosol.filter(has).map((r, i) => ({ key: 'a' + i, title: `Аэрозоль ${r.color || '?'}`, r, unit: 'шт', set: v => { const a = [...it.aerosol]; a[it.aerosol.indexOf(r)] = v; up('aerosol', a) } })),
    ...(k.facade && has(it.facade) ? [{ key: 'f', title: 'Фасадная краска', r: it.facade, unit: 'л', set: v => up('facade', v) }] : []),
    ...k.mat.filter(m => has(it.mat[m.code])).map(m => ({ key: m.code, title: m.title, r: it.mat[m.code], unit: m.unit, set: v => up('mat', { ...it.mat, [m.code]: v }) })),
    ...it.extra.filter(has).map(r => ({ key: 'x' + r.title, title: r.title || 'позиция', r, unit: r.unit || 'шт', set: v => { const a = [...it.extra]; a[it.extra.indexOf(r)] = v; up('extra', a) } })),
  ]
  const tookObr = k.obr.filter(o => it.obr[o.code]?.took)
  const nTake = taken.length + tookObr.length + it.pre.filter(Boolean).length + Object.values(it.ras).filter(Boolean).length
  const nBackDone = taken.filter(t => t.r.returned !== '' && t.r.returned != null).length + tookObr.filter(o => it.obr[o.code]?.back).length
  const nBack = taken.length + tookObr.length
  const lost = tookObr.filter(o => !it.obr[o.code]?.back)
  const broken = tookObr.filter(o => ['сломано', 'потеряно'].includes(it.obr[o.code]?.state_in))
  const noReturn = taken.filter(t => t.r.returned === '' || t.r.returned == null)
  const states = (v, set) => <div className="chips sub">{k.states.map(s => <button key={s} type="button" disabled={ro} className={v === s ? 'on' : ''} onClick={() => set(s)}>{s}</button>)}</div>
  return <div className="kit">
    <div className="card dark kithead">
      <button className="ghost mini back" onClick={back}>← Назад</button>
      <span className="kick">{ZT[zone]}</span><h2>№{id} · {d.object.title}</h2>
      <div className="kitprog"><div><b>{nTake}</b><span>взяли</span></div><div><b>{nBackDone}/{nBack}</b><span>вернули</span></div>
        <div><b>{d.list?.status === 'closed' ? '✓' : nBackDone && lost.length ? lost.length : '—'}</b><span>{d.list?.status === 'closed' ? 'сдан' : 'не вернули'}</span></div></div>
    </div>
    {ro && d.list?.status !== 'closed' && <p className="small muted">Список ведёт Главный художник, Художник-Про, Мастер печати или ГИП объекта.</p>}
    <div className="segf sticky">{STEPS.map(([s, t]) => <button key={s} className={step === s ? 'on' : ''} onClick={() => setStep(s)}>{t}</button>)}</div>

    {step === 'take' && <>
      <div className="card"><h3>Перед выездом</h3>{k.pre.map((t, i) => <Tap key={i} ro={ro} on={!!it.pre[i]} set={v => { const a = [...it.pre]; a[i] = v; up('pre', a) }}>{t}</Tap>)}</div>
      {k.aerosol && <div className="card"><h3>Аэрозоль <span className="small muted">номер цвета — штук</span></h3>
        {it.aerosol.map((r, i) => <div key={i} className="kitrow2">
          <input disabled={ro} placeholder="номер цвета" value={r.color} onChange={e => { const a = [...it.aerosol]; a[i] = { ...r, color: e.target.value }; up('aerosol', a) }} />
          <Step ro={ro} unit="шт" value={r.taken} set={v => { const a = [...it.aerosol]; a[i] = { ...r, taken: v }; up('aerosol', a) }} />
          {!ro && <button className="ghost mini" aria-label="Убрать" onClick={() => up('aerosol', it.aerosol.filter((_, j) => j !== i))}>✕</button>}
        </div>)}
        {!ro && <button className="ghost mini" onClick={() => up('aerosol', [...it.aerosol, { color: '', taken: '1' }])}>+ цвет</button>}</div>}
      <div className="card"><h3>Материалы</h3>
        {k.facade && <div className="kitline"><span>Фасадная краска, всего</span><Step ro={ro} unit="л" value={it.facade.taken} set={v => up('facade', { ...it.facade, taken: v })} /></div>}
        {k.mat.map(m => <div key={m.code} className="kitline"><span>{m.title}</span><Step ro={ro} unit={m.unit} value={it.mat[m.code]?.taken} set={v => up('mat', { ...it.mat, [m.code]: { ...(it.mat[m.code] || {}), taken: v } })} /></div>)}
        {it.extra.map((r, i) => <div key={'x' + i} className="kitline">
          <input disabled={ro} placeholder="что ещё" value={r.title} onChange={e => { const a = [...it.extra]; a[i] = { ...r, title: e.target.value }; up('extra', a) }} />
          <Step ro={ro} unit={r.unit || 'шт'} value={r.taken} set={v => { const a = [...it.extra]; a[i] = { ...r, taken: v }; up('extra', a) }} /></div>)}
        {!ro && <button className="ghost mini" onClick={() => up('extra', [...it.extra, { title: '', unit: 'шт', taken: '1' }])}>+ позиция</button>}</div>
      <div className="card"><h3>Оборудование</h3>
        {k.obr.map(o => { const r = it.obr[o.code] || {}; const set = v => up('obr', { ...it.obr, [o.code]: { ...r, ...v } })
          return <div key={o.code}><Tap ro={ro} on={!!r.took} set={v => set({ took: v, state_out: v ? r.state_out || k.states[0] : r.state_out })}>{o.title}</Tap>
            {r.took && states(r.state_out, v => set({ state_out: v }))}</div> })}</div>
      <div className="card"><h3>Расходники</h3>{k.ras.map(r => <Tap key={r.code} ro={ro} on={!!it.ras[r.code]} set={v => up('ras', { ...it.ras, [r.code]: v })}>{r.title}</Tap>)}</div>
      {!ro && <button onClick={() => { save(); setStep('back'); window.scrollTo(0, 0) }}>Собрано → к возврату</button>}
    </>}

    {step === 'back' && <>
      <div className="card"><h3>Материалы — сколько вернули</h3>
        {!taken.length && <p className="small muted">Сначала отметь на шаге «Взяли», что берёте.</p>}
        {taken.map(t => <div key={t.key} className="kitline"><span>{t.title}<i className="small muted"> · взяли {t.r.taken} {t.unit}</i></span>
          <Step ro={ro} unit={t.unit} ph="вернули" value={t.r.returned} set={v => t.set({ ...t.r, returned: v })} /></div>)}
        {!ro && noReturn.length > 0 && <button className="ghost mini" onClick={() => noReturn.forEach(t => t.set({ ...t.r, returned: '0' }))}>Всё израсходовали (0)</button>}</div>
      <div className="card"><h3>Оборудование — вернули и в каком состоянии</h3>
        {!tookObr.length && <p className="small muted">Оборудование не брали.</p>}
        {tookObr.map(o => { const r = it.obr[o.code]; const set = v => up('obr', { ...it.obr, [o.code]: { ...r, ...v } })
          return <div key={o.code}><Tap ro={ro} on={!!r.back} sub={r.state_out ? ` · брали: ${r.state_out}` : ''} set={v => set({ back: v, state_in: v ? r.state_in || r.state_out || k.states[0] : r.state_in })}>{o.title}</Tap>
            {r.back && states(r.state_in, v => set({ state_in: v }))}</div> })}
        {!ro && tookObr.some(o => !it.obr[o.code].back) && <button className="ghost mini" onClick={() => up('obr', Object.fromEntries(Object.entries(it.obr).map(([c, r]) => [c, r.took ? { ...r, back: true, state_in: r.state_in || r.state_out || k.states[0] } : r])))}>Вернули всё</button>}</div>
      <div className="card"><h3>После объекта</h3>{k.post.map((t, i) => <Tap key={i} ro={ro} on={!!it.post[i]} set={v => { const a = [...it.post]; a[i] = v; up('post', a) }}>{t}</Tap>)}</div>
      {!ro && <button onClick={() => { save(); setStep('done'); window.scrollTo(0, 0) }}>Проверить и сдать →</button>}
    </>}

    {step === 'done' && <div className="card">
      {d.list?.status === 'closed' && <p className="small why">Проект сдан — список только для чтения.</p>}
      {d.usage ? <div className="warnbox small"><b>Расход по проекту</b>
        {d.usage.aerosol.length > 0 && <div>Аэрозоль: {d.usage.aerosol.map(a => `${a.color} — ${a.used}`).join(', ')} (всего {d.usage.aerosol_total} шт)</div>}
        {d.usage.facade_l != null && <div>Фасадная: {d.usage.facade_l} л</div>}
        {Object.entries(d.usage.mat).filter(([, v]) => v).map(([c, v]) => <div key={c}>{(k.mat.find(m => m.code === c) || {}).title || c}: {v}</div>)}
        {d.usage.lost.length > 0 && <div>Не вернули: {d.usage.lost.map(c => (k.obr.find(o => o.code === c) || {}).title || c).join(', ')}</div>}
      </div> : <>
        <h3>Итог перед сдачей</h3>
        <div className="checklist">
          <div className={noReturn.length ? 'bad' : 'good'}>{noReturn.length ? `Не отмечен возврат: ${noReturn.map(t => t.title).join(', ')}` : 'Материалы: возврат отмечен'}</div>
          <div className={lost.length ? 'bad' : 'good'}>{lost.length ? `Оборудование не вернули: ${lost.map(o => o.title).join(', ')}` : 'Оборудование: всё вернули'}</div>
          {broken.length > 0 && <div className="bad">Сломано / потеряно: {broken.map(o => o.title).join(', ')} — HEAD увидит в расходе</div>}
          <div className={it.post.filter(Boolean).length === k.post.length ? 'good' : 'bad'}>После объекта: {it.post.filter(Boolean).length} из {k.post.length}</div>
        </div>
        {!ro && <button onClick={close}>Сдать проект</button>}
      </>}
    </div>}
    {msg && <p className="small muted center">{msg}</p>}
  </div>
}
