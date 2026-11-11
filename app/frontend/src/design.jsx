import React, { useEffect, useState } from 'react'
import { api } from './api.js'
import { Sheet } from './ui.jsx'
import { bxLink, usePortal } from './crm.jsx'

// «Дизайн» (HEAD 06–07.11): воронка Битрикса «Дизайн РК», единицы за месяц, каталог референсов.
// Единица — только при «УТВЕРЖДЕНО» (макет и эскиз утверждены); каждый переход в «Правки» — новый круг, без доплаты.
const money = n => Number(n || 0).toLocaleString('ru-RU') + ' ₸'
const CST = { draft: 'черновик', sent: 'у HEAD', returned: 'вернул', approved: 'утверждено' }
// Ссылку из мини-приложения Telegram открываем через openLink — обычная ссылка там может не открыться (HEAD 11.11)
const openUrl = u => { const t = window.Telegram?.WebApp; if (t?.openLink && t.initData) t.openLink(u); else window.open(u, '_blank', 'noopener') }
const host = u => { try { const h = new URL(u).hostname.replace(/^www\./, ''); return /drive\.google|docs\.google/.test(h) ? 'Google Диск' : /pinterest|pin\.it/.test(h) ? 'Pinterest' : /figma/.test(h) ? 'Figma' : /behance/.test(h) ? 'Behance' : h } catch { return '' } }
const works = n => `${n} ${n % 10 === 1 && n % 100 !== 11 ? 'работа' : [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? 'работы' : 'работ'}`
const dmy = s => s ? new Date(s).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' }) : ''

export function Design({ me, initial }) {
  const [view, setView] = useState(initial || 'deals')
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

// Страница воронки (HEAD 08.11): карточками — что горит, где что лежит, и по каждой стадии: что делать, как, что ожидается.
// Ключ — код стадии Битрикса «Дизайн РК» (воронка 13); названия стадий — из Битрикса.
const GUIDE = {
  NEW: { color: '#1f86ff', todo: 'Принять заказ и проверить, что от МОП есть задача: что рисуем, где, к какому сроку.',
    how: 'Главный дизайнер назначает дизайнера, размер и срок. Нет задачи — вопрос МОП в сделке, не в личку.', want: 'В тот же день — «Сбор информации» или «Взято в работу».' },
  FINAL_INVOICE: { color: '#f11716', todo: 'Срочный заказ — берётся первым, остальное ждёт.',
    how: 'Срок сегодня или завтра. Вопросы к МОП — сразу, не копить. Главный дизайнер следит лично.', want: 'Эскиз клиенту к сроку, без переносов.' },
  UC_3KZLWD: { color: '#ace9fb', todo: 'Собрать всё для макета: размеры стены, фото объекта, референсы, пожелания клиента.',
    how: 'Запросить у МОП через сделку. Фото и размеры — в папку проекта, референсы — из каталогов.', want: 'Полная задача без догадок — тогда «Взято в работу».' },
  PREPARATION: { color: '#30afff', todo: 'Делать макет и эскиз.',
    how: 'Стиль — по каталогу референсов. На макете для клиента — поля 50 см у краёв; что печать, что руками — отметить. Готовое — в «ДИЗАЙН/Утвержденные дизайны».',
    want: 'Макет к сроку дизайна и ссылка на него в карточке.' },
  PREPAYMENT_INVOIC: { color: '#00c0d5', todo: 'Макет у клиента — ждём ответ.',
    how: 'Клиенту напрямую не пишем: всё через МОП и Битрикс. Тишина больше суток — напомнить МОП.', want: '«Утверждаю» — или список правок от МОП.' },
  EXECUTING: { color: '#31c469', todo: 'Внести правки клиента.',
    how: 'Правки — списком от МОП, все за один раз. Каждый вход в «Правки» — новый круг, без доплаты.', want: 'Исправленный макет быстро и без нового круга.' },
  UC_LC1X2T: { color: '#00c4fb', todo: 'Макет у МОП: КП и договор.',
    how: 'Проверь, что в карточке есть папка проекта и ссылка на утверждённый эскиз.', want: 'МОП закрывает с клиентом — стадия «УТВЕРЖДЕНО».' },
  WON: { color: '#7bd500', todo: 'Утверждено — единица засчитана.', how: 'Нужны размер, дизайнер и ссылка на утверждённый эскиз.', want: 'Эскиз уходит в производство.' },
}
const code = id => String(id || '').split(':')[1] || ''
const today = () => new Date(new Date().toDateString())
const daysLeft = s => s ? Math.round((new Date(s) - today()) / 864e5) : null
// «Горит» (HEAD 09.11) — только срок и срочность: просрочено, сегодня, завтра, «Срочный заказ», второй круг правок.
// Нет дизайнера, размера или срока — не «горит», а «Назначить» (у Главного дизайнера и HEAD).
function hot(x) {
  const d = daysLeft(x.deadline), r = []
  if (d != null && d < 0) r.push('срок прошёл')
  else if (d === 0) r.push('срок сегодня')
  else if (d === 1) r.push('срок завтра')
  if (code(x.stage) === 'FINAL_INVOICE') r.push('срочно')
  if (x.rounds >= 2) r.push(`правки: круг ${x.rounds}`)
  return r
}
function lacks(x) {
  return [!x.designer_bx && 'нет дизайнера', !x.size && 'нет размера', !x.deadline && 'нет срока'].filter(Boolean)
}
function Due({ s }) {
  const d = daysLeft(s)
  if (d == null) return <span className="due">без срока</span>
  return <span className={'due' + (d < 0 ? ' late' : d <= 1 ? ' soon' : '')}>{d < 0 ? `просрочено ${-d} дн` : d === 0 ? 'сегодня' : d === 1 ? 'завтра' : 'до ' + dmy(s)}</span>
}

function Deals() {
  const [d, setD] = useState(null)
  const [e, setE] = useState('')
  const [open, setOpen] = useState(null)
  const [view, setView] = useState('')
  const [only, setOnly] = useState('')
  const [shut, setShut] = useState({})
  const [guide, setGuide] = useState(() => { try { return localStorage.getItem('artgame.dzguide') === '1' } catch { return false } })
  const team = useTeam()
  const load = (fresh = 0) => api('/design/deals?fresh=' + fresh).then(setD, x => setE(x.message))
  useEffect(() => { load() }, [])
  if (e) return <div className="card muted">{e}</div>
  if (!d) return <div className="card muted">Загрузка…</div>
  const fire = d.deals.map(x => ({ x, why: hot(x) })).filter(f => f.why.length)
  const todo = d.can_assign ? d.deals.map(x => ({ x, why: lacks(x) })).filter(f => f.why.length) : []
  const stages = d.stages.filter(s => code(s.id) !== 'WON')
  const v = view || (fire.length ? 'fire' : 'stages')
  const toggle = () => { setGuide(!guide); try { localStorage.setItem('artgame.dzguide', guide ? '0' : '1') } catch { /* без памяти */ } }
  const Card = ({ x, why, need }) => { const g = GUIDE[code(x.stage)] || {}
    const i = stages.findIndex(s => s.id === x.stage)
    return <div className="dzcard" style={{ '--sc': g.color || 'var(--line)' }} onClick={() => setOpen(x)}>
      <div className="dztop"><span className="tag">№ {x.id}</span><Due s={x.deadline} /></div>
      <b className="dztitle">{x.title || 'Сделка ' + x.id}</b>
      <div className="small muted">{[x.designer || 'дизайнер не назначен', x.size ? x.size.toUpperCase() + ' · ' + String(x.units).replace('.', ',') + ' ед.' : '', x.city].filter(Boolean).join(' · ')}</div>
      {(why?.length || need?.length) ? <div>{(why || []).map(w => <span key={w} className="miss hotm">{w}</span>)}{(need || []).map(w => <span key={w} className="miss">{w}</span>)}</div> : null}
      <div className="dzst"><span className="dzdots">{stages.map((s, k) => <i key={s.id} className={k < i ? 'done' : k === i ? 'on' : ''} />)}</span>
        <span className="small muted">{stages[i]?.name || x.stage_name}</span></div>
    </div> }
  const tabs = [['fire', '🔥 Горит', fire.length], ...(d.can_assign ? [['todo', 'Назначить', todo.length]] : []), ['stages', 'По стадиям', d.deals.length]]
  return <>
    <div className="card dzhero">
      <div className="head"><h2>Воронка «Дизайн РК»</h2><button className="ghost mini" onClick={() => { setD(null); load(1) }}>Обновить</button></div>
      <p className="small muted">Единица — на «УТВЕРЖДЕНО». Связь с клиентом — кнопкой в карточке сделки, через Битрикс. Готовые эскизы — в «ДИЗАЙН/Утвержденные дизайны».</p>
      {!d.bx && <p className="small why">Запись в Битрикс выключена — изменения пишутся только в журнал.</p>}
      <div className="segf dztabs">{tabs.map(([k, t, n]) => <button key={k} className={v === k ? 'on' : ''} onClick={() => { setView(k); setOnly('') }}>{t}<b>{n}</b></button>)}</div>
    </div>
    {v === 'fire' && <div className="card dzfire"><h3>🔥 Горит · {fire.length}</h3>
      <p className="small muted">Срок прошёл, сегодня или завтра, срочный заказ, второй круг правок. Берётся первым.</p>
      {fire.length ? <div className="dzgrid">{fire.map(f => <Card key={f.x.id} x={f.x} why={f.why} />)}</div> : <p className="small muted">Ничего не горит.</p>}</div>}
    {v === 'todo' && <div className="card dztodo"><h3>Назначить · {todo.length}</h3>
      <p className="small muted">Не хватает дизайнера, размера или срока. Нажми на сделку и заполни.</p>
      {todo.length ? <div className="dzgrid">{todo.map(f => <Card key={f.x.id} x={f.x} need={f.why} />)}</div> : <p className="small muted">Все сделки назначены.</p>}</div>}
    {v === 'stages' && <>
      <div className="card"><div className="dzfunnel">{stages.map(s => { const n = d.deals.filter(x => x.stage === s.id).length, g = GUIDE[code(s.id)] || {}
        return <button key={s.id} className={'dzstep' + (only === s.id ? ' on' : '') + (n ? '' : ' empty')} style={{ '--sc': g.color || 'var(--line)' }}
          onClick={() => setOnly(only === s.id ? '' : s.id)}><b>{n}</b><span>{s.name}</span></button> })}</div>
        <button className="ghost mini" onClick={toggle}>{guide ? 'Скрыть подсказки' : 'Подсказки: что делать на каждой стадии'}</button></div>
      {stages.filter(s => !only || s.id === only).map(s => { const rows = d.deals.filter(x => x.stage === s.id), g = GUIDE[code(s.id)]
        if (!rows.length && !only) return null
        const closed = only ? false : shut[s.id] ?? rows.length > 6
        return <div key={s.id} className="card dzstage" style={{ '--sc': g?.color || 'var(--line)' }}>
          <button className="stagehead dzsh" onClick={() => setShut({ ...shut, [s.id]: !closed })}><span><i className="dzdot" />{s.name}</span><span className="muted small">{rows.length} {closed ? '▸' : '▾'}</span></button>
          {!closed && <>{guide && g && <div className="dzguide">
            <div><i>Что делать</i><span>{g.todo}</span></div><div><i>Как</i><span>{g.how}</span></div><div><i>Что ожидается</i><span>{g.want}</span></div></div>}
          <div className="dzgrid">{rows.map(x => <Card key={x.id} x={x} why={hot(x)} />)}</div>
          {!rows.length && <p className="small muted">Здесь сейчас пусто.</p>}</>}
        </div> })}</>}
    {!d.deals.length && <div className="card"><p className="small muted">{d.can_assign ? 'Открытых сделок дизайна нет.' : 'На вас пока нет сделок дизайна.'}</p></div>}
    {open && <DealSheet x={open} d={d} team={team} onClose={() => setOpen(null)} onDone={() => { setOpen(null); load(1) }} />}
  </>
}

function DealSheet({ x, d, team, onClose, onDone }) {
  const portal = usePortal()
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
  const bxu = bxLink(portal, 'deal', x.id)
  return <Sheet title={x.title || 'Сделка ' + x.id} onClose={onClose}>
    <p className="small muted">№ {x.id}{x.rounds ? ` · правки: круг ${x.rounds}` : ''} · единица засчитывается на «УТВЕРЖДЕНО»</p>
    {bxu && <div className="dealbtns dzcontact">
      <a className="btn" href={bxu} target="_blank" rel="noreferrer">Связаться с клиентом · звонок и WhatsApp в Битриксе</a></div>}
    {bxu && <p className="small muted">Звонок и переписка идут из карточки Битрикса — так всё остаётся в сделке.</p>}
    <label className="muted">Стадия</label>
    <select value={v.stage} onChange={e => set({ ...v, stage: e.target.value })}>{d.stages.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
    {v.stage === won && v.stage !== x.stage && <p className="small why">Перед «УТВЕРЖДЕНО» нужны размер, дизайнер и ссылка на утверждённый эскиз.</p>}
    <label className="muted">Дизайнер</label>
    <select disabled={!d.can_assign} value={v.designer_bx} onChange={e => set({ ...v, designer_bx: e.target.value })}>
      <option value="">не назначен</option>
      {team.filter(t => t.bitrix_user_id).map(t => <option key={t.bitrix_user_id} value={t.bitrix_user_id}>{t.full_name}{t.bx_only ? ' · из Битрикса' : ''}</option>)}</select>
    {d.can_assign && team.some(t => !t.bitrix_user_id) && <p className="small muted">Не связаны с Битриксом: {team.filter(t => !t.bitrix_user_id).map(t => t.full_name).join(', ')} — HEAD, вкладка «Команда».</p>}
    {d.can_assign && team.some(t => t.bx_only) && <p className="small muted">«Из Битрикса» — дизайнер ещё не вошёл в приложение: сделку назначить можно, единицы засчитаются, когда HEAD свяжет его в «Команде».</p>}
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
    <div className="head"><h2>Каталог референсов</h2>{!c.is_head && !form && <button className="mini" onClick={() => setForm({ title: '', style: '', url: '', works: '', authors: [me.id] })}>+ Новый</button>}</div>
    <p className="small muted">Собрал каталог (60+ работ) — отправь HEAD. После «утверждаю» {money(c.amount)} в «Кабинет»; двое исполнителей — пополам.</p>
    {form && <div className="warnbox">
      <input placeholder="Название" value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} />
      <input placeholder="Стиль" value={form.style || ''} onChange={e => setForm({ ...form, style: e.target.value })} />
      <input placeholder="Ссылка на папку или рефборд" value={form.url || ''} onChange={e => setForm({ ...form, url: e.target.value })} />
      <input inputMode="numeric" placeholder="Сколько работ внутри (60+)" value={form.works ?? ''} onChange={e => setForm({ ...form, works: e.target.value.replace(/\D/g, '') })} />
      <label className="muted small">Исполнители (1–2)</label>
      <div className="chips">{team.filter(t => t.id).map(t => { const on = form.authors.includes(t.id)
        return <button key={t.id} className={on ? 'on' : ''} onClick={() => setForm({ ...form, authors: on ? form.authors.filter(a => a !== t.id) : [...form.authors, t.id].slice(-2) })}>{t.full_name}</button> })}</div>
      <div className="seg"><button className="ghost" onClick={() => setForm(null)}>Отмена</button>
        <button disabled={form.title.trim().length < 2 || !form.authors.length} onClick={() => api(form.id ? `/design/catalogs/${form.id}` : '/design/catalogs', { method: 'POST', body: { ...form, works: form.works === '' || form.works == null ? null : +form.works } })
          .then(() => { setForm(null); load() }, ex => setMsg(ex.message))}>Сохранить</button></div>
    </div>}
    {msg && <p className="small why">{msg}</p>}
    {c.rows.map(r => <div key={r.id} className="row">
      <div><b>{r.title}</b>
        <div className="small muted">{[r.style, r.works ? works(r.works) : '', (r.author_names || []).join(' + '), r.authors.length > 1 ? 'пополам' : ''].filter(Boolean).join(' · ')}</div>
        <div className={'small ' + (r.status === 'approved' ? 'ok' : r.status === 'returned' ? 'why' : 'muted')}>{c.is_head && r.status === 'sent' ? 'ждёт вашего решения' : CST[r.status]}</div>
        {!r.url && <div className="small why">Ссылки нет — верните с просьбой добавить</div>}
        {c.is_head && r.status === 'sent' && r.works > 0 && r.works < 60 && <div className="small why">Меньше 60 работ</div>}
        {r.comment && <div className="small">HEAD: {r.comment}</div>}</div>
      <div className="qbtns">{r.url && <button className="ghost mini catopen" onClick={() => openUrl(r.url)}>Посмотреть ↗{host(r.url) ? <small>{host(r.url)}</small> : null}</button>}
        {mine(r) && ['draft', 'returned'].includes(r.status) && <>
          <button className="ghost mini" onClick={() => setForm({ id: r.id, title: r.title, style: r.style, url: r.url, works: r.works ?? '', authors: r.authors })}>Править</button>
          <button className="mini" onClick={() => act(`/design/catalogs/${r.id}/send`)}>Отправить HEAD</button></>}
        {c.is_head && r.status === 'sent' && <>
          <button className="mini" onClick={() => act(`/design/catalogs/${r.id}/decide`, { approve: true })}>Утверждаю</button>
          <button className="ghost mini" onClick={() => { const t = prompt('Что поправить?'); if (t && t.trim()) act(`/design/catalogs/${r.id}/decide`, { approve: false, comment: t.trim() }) }}>Вернуть</button></>}
      </div>
    </div>)}
    {!c.rows.length && !form && <p className="small muted">Каталогов пока нет.</p>}
  </div>
}
