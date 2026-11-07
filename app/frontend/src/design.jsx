import React, { useEffect, useState } from 'react'
import { api } from './api.js'
import { Sheet } from './ui.jsx'

// «Дизайн» (HEAD 06–07.11): воронка Битрикса «Дизайн РК», единицы за месяц, каталог референсов.
// Единица — только при «УТВЕРЖДЕНО» (макет и эскиз утверждены); каждый переход в «Правки» — новый круг, без доплаты.
const money = n => Number(n || 0).toLocaleString('ru-RU') + ' ₸'
const CST = { draft: 'черновик', sent: 'у HEAD', returned: 'вернул', approved: 'утверждено' }
const dmy = s => s ? new Date(s).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' }) : ''

export function Design({ me }) {
  const [view, setView] = useState('deals')
  return <>
    <div className="card"><div className="segf">
      <button className={view === 'deals' ? 'on' : ''} onClick={() => setView('deals')}>Сделки</button>
      <button className={view === 'units' ? 'on' : ''} onClick={() => setView('units')}>Единицы</button>
      <button className={view === 'cat' ? 'on' : ''} onClick={() => setView('cat')}>Каталоги</button>
    </div></div>
    {view === 'deals' ? <Deals /> : view === 'units' ? <Units /> : <Catalogs me={me} />}
  </>
}

function useTeam() {
  const [t, setT] = useState([])
  useEffect(() => { api('/design/team').then(setT, () => setT([])) }, [])
  return t
}

function Deals() {
  const [d, setD] = useState(null)
  const [e, setE] = useState('')
  const [open, setOpen] = useState(null)
  const team = useTeam()
  const load = (fresh = 0) => api('/design/deals?fresh=' + fresh).then(setD, x => setE(x.message))
  useEffect(() => { load() }, [])
  if (e) return <div className="card muted">{e}</div>
  if (!d) return <div className="card muted">Загрузка…</div>
  return <div className="card">
    <div className="head"><h2>Воронка «Дизайн РК»</h2><button className="ghost mini" onClick={() => { setD(null); load(1) }}>Обновить</button></div>
    {!d.bx && <p className="small why">Запись в Битрикс выключена — изменения пишутся только в журнал.</p>}
    {d.stages.map(s => { const rows = d.deals.filter(x => x.stage === s.id)
      if (!rows.length) return null
      return <div key={s.id} className="stage"><div className="stagehead"><b>{s.name}</b> <span className="muted small">{rows.length}</span></div>
        {rows.map(x => <div key={x.id} className="row" onClick={() => setOpen(x)} style={{ cursor: 'pointer' }}>
          <div><b>{x.title || 'Сделка ' + x.id}</b>
            <div className="small muted">{[x.designer || 'дизайнер не назначен', x.size ? x.size.toUpperCase() + ' · ' + x.units + ' ед.' : 'размер не задан',
              x.deadline && 'срок ' + dmy(x.deadline), x.rounds ? `правки: круг ${x.rounds}` : '', x.city].filter(Boolean).join(' · ')}</div></div>
          <span className="tag">№ {x.id}</span></div>)}</div> })}
    {!d.deals.length && <p className="small muted">{d.can_assign ? 'Открытых сделок дизайна нет.' : 'На вас пока нет сделок дизайна.'}</p>}
    {open && <DealSheet x={open} d={d} team={team} onClose={() => setOpen(null)} onDone={() => { setOpen(null); load(1) }} />}
  </div>
}

function DealSheet({ x, d, team, onClose, onDone }) {
  const [v, set] = useState({ stage: x.stage, designer_bx: x.designer_bx || '', size: x.size || '', deadline: x.deadline || '', folder: x.folder, layout: x.layout })
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const send = () => {
    const b = {}
    if (v.stage !== x.stage) b.stage = v.stage
    if (d.can_assign && String(v.designer_bx) !== String(x.designer_bx || '')) b.designer_bx = +v.designer_bx || 0
    if (d.can_assign && v.size && v.size !== x.size) b.size = v.size
    if (v.deadline && v.deadline !== x.deadline) b.deadline = v.deadline
    if (v.folder !== x.folder) b.folder = v.folder
    if (v.layout !== x.layout) b.layout = v.layout
    if (!Object.keys(b).length) return onClose()
    setBusy(true)
    api(`/design/deals/${x.id}`, { method: 'POST', body: b }).then(onDone, ex => { setMsg(ex.message); setBusy(false) })
  }
  const won = d.stages.find(s => s.name.toUpperCase() === 'УТВЕРЖДЕНО')?.id
  return <Sheet title={x.title || 'Сделка ' + x.id} onClose={onClose}>
    <p className="small muted">№ {x.id}{x.rounds ? ` · правки: круг ${x.rounds}` : ''} · единица засчитывается на «УТВЕРЖДЕНО»</p>
    <label className="muted">Стадия</label>
    <select value={v.stage} onChange={e => set({ ...v, stage: e.target.value })}>{d.stages.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
    {v.stage === won && v.stage !== x.stage && <p className="small why">Перед «УТВЕРЖДЕНО» нужны размер, дизайнер и ссылка на утверждённый эскиз.</p>}
    <label className="muted">Дизайнер</label>
    <select disabled={!d.can_assign} value={v.designer_bx} onChange={e => set({ ...v, designer_bx: e.target.value })}>
      <option value="">не назначен</option>
      {team.filter(t => t.bitrix_user_id).map(t => <option key={t.id} value={t.bitrix_user_id}>{t.full_name}</option>)}</select>
    {d.can_assign && team.some(t => !t.bitrix_user_id) && <p className="small muted">Не связаны с Битриксом: {team.filter(t => !t.bitrix_user_id).map(t => t.full_name).join(', ')} — HEAD, вкладка «Команда».</p>}
    <label className="muted">Размер</label>
    <div className="chips">{d.sizes.map(s => <button key={s.code} disabled={!d.can_assign} className={v.size === s.code ? 'on' : ''}
      onClick={() => set({ ...v, size: s.code })}>{s.title} · {String(s.units).replace('.', ',')}</button>)}</div>
    <label className="muted">Срок дизайна</label>
    <input type="date" value={v.deadline} onChange={e => set({ ...v, deadline: e.target.value })} />
    <label className="muted">Папка проекта</label>
    <input value={v.folder} placeholder="ссылка на Диск" onChange={e => set({ ...v, folder: e.target.value })} />
    <label className="muted">Утверждённый эскиз</label>
    <input value={v.layout} placeholder="ссылка на эскиз" onChange={e => set({ ...v, layout: e.target.value })} />
    {msg && <p className="small why">{msg}</p>}
    <button disabled={busy} onClick={send}>Сохранить в Битрикс</button>
  </Sheet>
}

function Units() {
  const [m, setM] = useState(new Date().toISOString().slice(0, 7))
  const [u, setU] = useState(null)
  const load = () => api('/design/units?ym=' + m).then(setU, () => setU({ rows: [], mine: 0 }))
  useEffect(() => { setU(null); load() }, [m])
  const cancel = r => { const why = prompt('Почему снимаем единицу? (проект в работу не пошёл…)'); if (why && why.trim().length >= 3) api(`/design/units/${r.deal_id}/cancel`, { method: 'POST', body: { reason: why.trim() } }).then(load, ex => alert(ex.message)) }
  return <div className="card">
    <div className="head"><h2>Единицы</h2><input type="month" value={m} onChange={e => setM(e.target.value)} style={{ width: 'auto' }} /></div>
    {u && <><div className="kv"><div><span className="muted small">Мои за месяц</span><b>{String(u.mine).replace('.', ',')}</b></div>
      <div><span className="muted small">Норма</span><b>{u.norm != null ? u.norm : 'ждёт решения HEAD'}</b></div></div>
      {u.unit_over && <p className="small muted">Сверх нормы — {money(u.unit_over)} за единицу (Главный дизайнер). Правки — счётчик кругов, без доплаты.</p>}
      {u.rows.map(r => <div key={r.deal_id} className="row">
        <div><b>{r.title || 'Сделка ' + r.deal_id}</b>
          <div className="small muted">{[r.full_name || 'дизайнер не связан', (r.size || '—').toUpperCase(), dmy(r.approved_at), r.rounds ? `кругов правок: ${r.rounds}` : 'без правок',
            r.status === 'cancelled' && 'снято: ' + r.reason].filter(Boolean).join(' · ')}</div></div>
        <div className="qbtns"><b className={r.status === 'cancelled' ? 'muted' : ''}>{String(+r.units).replace('.', ',')}</b>
          {u.can_cancel && r.status === 'active' && <button className="ghost mini" onClick={() => cancel(r)}>Снять</button>}</div>
      </div>)}
      {!u.rows.length && <p className="small muted">Утверждённых макетов за месяц нет.</p>}</>}
  </div>
}

function Catalogs({ me }) {
  const [c, setC] = useState(null)
  const [form, setForm] = useState(null)
  const [msg, setMsg] = useState('')
  const team = useTeam()
  const load = () => api('/design/catalogs').then(setC, ex => setMsg(ex.message))
  useEffect(() => { load() }, [])
  if (!c) return <div className="card muted">{msg || 'Загрузка…'}</div>
  const act = (path, body) => api(path, { method: 'POST', body }).then(() => { setMsg(''); load() }, ex => setMsg(ex.message))
  const mine = r => r.authors.includes(me.id) || r.created_by === me.id
  return <div className="card">
    <div className="head"><h2>Каталог референсов</h2>{!c.is_head && !form && <button className="mini" onClick={() => setForm({ title: '', style: '', url: '', authors: [me.id] })}>+ Новый</button>}</div>
    <p className="small muted">Собрал каталог (60+ работ) — отправь HEAD. После «утверждаю» {money(c.amount)} в «Мои»; двое исполнителей — пополам.</p>
    {form && <div className="warnbox">
      <input placeholder="Название" value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} />
      <input placeholder="Стиль" value={form.style || ''} onChange={e => setForm({ ...form, style: e.target.value })} />
      <input placeholder="Ссылка на папку или рефборд" value={form.url || ''} onChange={e => setForm({ ...form, url: e.target.value })} />
      <label className="muted small">Исполнители (1–2)</label>
      <div className="chips">{team.map(t => { const on = form.authors.includes(t.id)
        return <button key={t.id} className={on ? 'on' : ''} onClick={() => setForm({ ...form, authors: on ? form.authors.filter(a => a !== t.id) : [...form.authors, t.id].slice(-2) })}>{t.full_name}</button> })}</div>
      <div className="seg"><button className="ghost" onClick={() => setForm(null)}>Отмена</button>
        <button disabled={form.title.trim().length < 2 || !form.authors.length} onClick={() => api(form.id ? `/design/catalogs/${form.id}` : '/design/catalogs', { method: 'POST', body: form })
          .then(() => { setForm(null); load() }, ex => setMsg(ex.message))}>Сохранить</button></div>
    </div>}
    {msg && <p className="small why">{msg}</p>}
    {c.rows.map(r => <div key={r.id} className="row">
      <div><b>{r.title}</b>{r.url && <> · <a href={r.url} target="_blank" rel="noreferrer">открыть</a></>}
        <div className="small muted">{[r.style, (r.author_names || []).join(' + '), r.authors.length > 1 ? 'пополам' : ''].filter(Boolean).join(' · ')}</div>
        {r.comment && <div className="small">HEAD: {r.comment}</div>}</div>
      <div className="qbtns"><span className={'tag' + (r.status === 'approved' ? ' st-approved' : r.status === 'returned' ? ' st-rejected' : '')}>{CST[r.status]}</span>
        {mine(r) && ['draft', 'returned'].includes(r.status) && <>
          <button className="ghost mini" onClick={() => setForm({ id: r.id, title: r.title, style: r.style, url: r.url, authors: r.authors })}>Править</button>
          <button className="mini" onClick={() => act(`/design/catalogs/${r.id}/send`)}>Отправить HEAD</button></>}
        {c.is_head && r.status === 'sent' && <>
          <button className="mini" onClick={() => act(`/design/catalogs/${r.id}/decide`, { approve: true })}>Утверждаю</button>
          <button className="ghost mini" onClick={() => { const t = prompt('Что поправить?'); if (t && t.trim()) act(`/design/catalogs/${r.id}/decide`, { approve: false, comment: t.trim() }) }}>Вернуть</button></>}
      </div>
    </div>)}
    {!c.rows.length && !form && <p className="small muted">Каталогов пока нет.</p>}
  </div>
}
