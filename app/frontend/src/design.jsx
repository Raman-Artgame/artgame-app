import React, { useEffect, useState } from 'react'
import { api } from './api.js'
import { Sheet } from './ui.jsx'
import { bxLink, usePortal } from './crm.jsx'
import { DealFiles, TaskBoard, useTaskCount } from './designtasks.jsx'

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
  const [pick, setView] = useState(initial || '')
  const n = useTaskCount(), team = useTeam()
  // HEAD 25.11: доска задач — в этой же вкладке, новых вкладок нет. Есть открытые задачи — открываем сразу её.
  // HEAD 28.11: вкладки «Единицы» нет — единицы видны в задачах, подробный список по кнопке «Подробнее» и в «Кабинете» дизайнера
  // HEAD 28.11: воронка «Дизайн РК» закрыта, сделки переехали в «Продажи РК» — вкладки «Сделки» больше нет, работа идёт в «Задачах»
  const view = pick === 'deals' ? 'tasks' : pick || 'tasks'
  if (!pick && n === null) return <div className="card"><p className="muted">Загружаю…</p></div>
  return <>
    <div className="card"><div className="segf">
      <button className={view === 'tasks' ? 'on' : ''} onClick={() => setView('tasks')}>Задачи{n ? <span>{n}</span> : null}</button>
      <button className={view === 'cat' ? 'on' : ''} onClick={() => setView('cat')}>Каталоги</button>
    </div></div>
    {view === 'tasks' ? <TaskBoard team={team} me={me} onUnits={() => setView('units')} /> : view === 'units' ? <><button className="ghost mini dtbackb" onClick={() => setView('tasks')}>← К задачам</button><Units /></> : <Catalogs me={me} />}
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
    how: 'Запросить у МОП через сделку. Фото и размеры загрузи в карточку, референсы — из каталогов.', want: 'Полная задача без догадок — тогда «Взято в работу».' },
  PREPARATION: { color: '#30afff', todo: 'Делать макет и эскиз.',
    how: 'Стиль — по каталогу референсов. На макете для клиента — поля 50 см у краёв; что печать, что руками — отметить. Готовое загрузи в карточку сделки кнопкой «Загрузить эскиз».',
    want: 'Макет к сроку дизайна, загружен в карточку.' },
  PREPAYMENT_INVOIC: { color: '#00c0d5', todo: 'Макет у клиента — ждём ответ.',
    how: 'Клиенту напрямую не пишем: всё через МОП и Битрикс. Тишина больше суток — напомнить МОП.', want: '«Утверждаю» — или список правок от МОП.' },
  EXECUTING: { color: '#31c469', todo: 'Внести правки клиента.',
    how: 'Правки — списком от МОП, все за один раз. Каждый вход в «Правки» — новый круг, без доплаты.', want: 'Исправленный макет быстро и без нового круга.' },
  UC_LC1X2T: { color: '#00c4fb', todo: 'Макет у МОП: КП и договор.',
    how: 'Проверь, что утверждённый эскиз загружен в карточку.', want: 'МОП закрывает с клиентом — стадия «УТВЕРЖДЕНО».' },
  WON: { color: '#7bd500', todo: 'Утверждено — единица засчитана.', how: 'Нужны размер, дизайнер и загруженный эскиз.', want: 'Эскиз уходит в производство.' },
}
const code = id => String(id || '').split(':')[1] || ''
const today = () => new Date(new Date().toDateString())
const daysLeft = s => s ? Math.round((new Date(s) - today()) / 864e5) : null
// «Горит» (HEAD 09.11) — только срок и срочность: просрочено, сегодня, завтра, «Срочный заказ», второй круг правок.
// Нет дизайнера, размера или срока — не «горит», а «Назначить» (у Главного дизайнера и HEAD).
// «Ждём клиента» (HEAD 22.11): сделка не горит, срок — с учётом дней ожидания (deadline_eff).
const dl = x => x.deadline_eff || x.deadline
function hot(x) {
  if (x.wait) return []
  const d = daysLeft(dl(x)), r = []
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

function Deals({ me }) {
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
  const waiting = d.deals.filter(x => x.wait).sort((a, b) => b.wait.days - a.wait.days)
  const todo = d.can_assign ? d.deals.map(x => ({ x, why: lacks(x) })).filter(f => f.why.length) : []
  const stages = d.stages.filter(s => code(s.id) !== 'WON')
  const v = view || 'stages'   // вкладку «Горит» убрали (HEAD 24.11); срок и срочность видны меткой на карточке сделки
  const toggle = () => { setGuide(!guide); try { localStorage.setItem('artgame.dzguide', guide ? '0' : '1') } catch { /* без памяти */ } }
  const Card = ({ x, why, need }) => { const g = GUIDE[code(x.stage)] || {}
    const i = stages.findIndex(s => s.id === x.stage)
    return <div className="dzcard" style={{ '--sc': g.color || 'var(--line)' }} onClick={() => setOpen(x)}>
      <div className="dztop"><span className="tag">№ {x.id}</span>{x.wait ? <span className="due wait">⏳ ждём {x.wait.days} дн</span> : <Due s={dl(x)} />}</div>
      <b className="dztitle">{x.title || 'Сделка ' + x.id}</b>
      <div className="small muted">{[x.designer || 'дизайнер не назначен', x.size ? x.size.toUpperCase() + ' · ' + String(x.units).replace('.', ',') + ' ед.' : '', x.city].filter(Boolean).join(' · ')}</div>
      {x.wait && <div className="small dzwait">{x.wait.reason}</div>}
      {(why?.length || need?.length) ? <div>{(why || []).map(w => <span key={w} className="miss hotm">{w}</span>)}{(need || []).map(w => <span key={w} className="miss">{w}</span>)}</div> : null}
      <div className="dzst"><span className="dzdots">{stages.map((s, k) => <i key={s.id} className={k < i ? 'done' : k === i ? 'on' : ''} />)}</span>
        <span className="small muted">{stages[i]?.name || x.stage_name}</span></div>
    </div> }
  const tabs = [...(d.can_assign ? [['todo', 'Назначить', todo.length]] : []), ['wait', '⏳ Ждём клиента', waiting.length], ['stages', 'По стадиям', d.deals.length]]
  return <>
    <div className="card dzhero">
      <div className="head"><h2>Воронка «Дизайн РК»</h2><button className="ghost mini" onClick={() => { setD(null); load(1) }}>Обновить</button></div>
      <p className="small muted">Единица — когда проект с твоим дизайном ушёл в работу. Связь с клиентом — кнопкой в карточке сделки, через Битрикс. Эскизы загружайте файлом в карточке сделки.</p>
      {!d.bx && <p className="small why">Запись в Битрикс выключена — изменения пишутся только в журнал.</p>}
      <div className="segf dztabs">{tabs.map(([k, t, n]) => <button key={k} className={v === k ? 'on' : ''} onClick={() => { setView(k); setOnly('') }}>{t}<b>{n}</b></button>)}</div>
    </div>
    {v === 'wait' && <div className="card dzwaitc"><h3>⏳ Ждём клиента · {waiting.length}</h3>
      <p className="small muted">Клиент не отвечает — просрочка не копится. Через 7 дней МОП получает напоминание. Ответил — открой сделку и нажми «Клиент ответил»: срок сдвинется на дни ожидания.</p>
      {waiting.length ? <div className="dzgrid">{waiting.map(x => <Card key={x.id} x={x} />)}</div> : <p className="small muted">Никого не ждём.</p>}</div>}
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
    {open && <DealSheet x={open} d={d} team={team} me={me} onClose={() => setOpen(null)} onDone={() => { setOpen(null); load(1) }} />}
  </>
}

function DealSheet({ x, d, team, me, onClose, onDone }) {
  const portal = usePortal()
  const [v, set] = useState({ stage: x.stage, designer_bx: x.designer_bx || '', size: x.size || '', deadline: x.deadline || '' })
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const send = () => {
    const b = {}
    if (v.stage !== x.stage) b.stage = v.stage
    if (d.can_assign && String(v.designer_bx) !== String(x.designer_bx || '')) b.designer_bx = +v.designer_bx || 0
    if (d.can_assign && v.size && v.size !== x.size) b.size = v.size
    if (v.deadline && v.deadline !== x.deadline) b.deadline = v.deadline
    if (!Object.keys(b).length) return onClose()
    setBusy(true)
    api(`/design/deals/${x.id}`, { method: 'POST', body: b }).then(onDone, ex => { setMsg(ex.message); setBusy(false) })
  }
  const [why, setWhy] = useState(null)
  const act = (path, body) => { setBusy(true); setMsg('')
    api(`/design/deals/${x.id}/${path}`, { method: 'POST', body }).then(onDone, ex => { setMsg(ex.message); setBusy(false) }) }
  const won = d.stages.find(s => s.name.toUpperCase() === 'УТВЕРЖДЕНО')?.id
  const bxu = bxLink(portal, 'deal', x.id)
  return <Sheet title={x.title || 'Сделка ' + x.id} onClose={onClose}>
    <p className="small muted">№ {x.id}{x.rounds ? ` · правки: круг ${x.rounds}` : ''} · единица засчитывается на «УТВЕРЖДЕНО»</p>
    {bxu && <div className="dealbtns dzcontact">
      <a className="btn" href={bxu} target="_blank" rel="noreferrer">Связаться с клиентом · звонок и WhatsApp в Битриксе</a></div>}
    {bxu && <p className="small muted">Звонок и переписка идут из карточки Битрикса — так всё остаётся в сделке.</p>}
    {x.wait ? <div className="dzwaitbox">
      <b>⏳ Ждём клиента {x.wait.days} дн</b> <span className="small muted">с {dmy(x.wait.since)}</span>
      <div className="small">{x.wait.reason}</div>
      <button disabled={busy} onClick={() => act('resume')}>Клиент ответил — вернуть в работу</button>
      {x.wait.days > 0 && <p className="small muted">Срок сдвинется на {x.wait.days} дн.</p>}</div>
      : x.stage !== won && (why == null
        ? <button className="ghost" disabled={busy} onClick={() => setWhy('')}>⏳ Ждём клиента</button>
        : <div className="dzwaitbox"><label className="muted">Чего ждём от клиента?</label>
          <input autoFocus value={why} placeholder="например: молчит по эскизу, ждём размеры стены" onChange={e => setWhy(e.target.value)} />
          <div style={{ display: 'flex', gap: 8 }}><button style={{ flex: 2 }} disabled={busy || why.trim().length < 3} onClick={() => act('wait', { reason: why.trim() })}>Ждём клиента</button>
            <button className="ghost" style={{ flex: 1 }} onClick={() => setWhy(null)}>Отмена</button></div>
          <p className="small muted">Сделка уйдёт в «Ждём клиента», просрочка не копится. Через 7 дней МОП получит напоминание.</p></div>)}
    <label className="muted">Стадия</label>
    <select value={v.stage} onChange={e => set({ ...v, stage: e.target.value })}>{d.stages.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
    {v.stage === won && v.stage !== x.stage && <p className="small why">Перед «УТВЕРЖДЕНО» нужны размер, дизайнер и загруженный эскиз.</p>}
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
    {x.waited_days > 0 && x.deadline_eff && <p className="small muted">С учётом ожидания клиента (+{x.waited_days} дн): до {dmy(x.deadline_eff)}.</p>}
    <h3 className="dth">Эскизы и материалы</h3>
    <p className="small muted">Загрузите файл — он сам ляжет в папку сделки «ДИЗАЙН». МОП увидит его в карточке сделки.</p>
    <DealFiles dealId={x.id} me={me} />
    {msg && <p className="small why">{msg}</p>}
    <button disabled={busy} onClick={send}>Сохранить в Битрикс</button>
  </Sheet>
}

const unitsOf = (u, size) => (u.sizes || {})[size] ?? ''
export function Units() {
  const [m, setM] = useState(new Date().toISOString().slice(0, 7))
  const [u, setU] = useState(null)
  const load = () => api('/design/units?ym=' + m).then(setU, () => setU({ rows: [], mine: 0 }))
  useEffect(() => { setU(null); load() }, [m])
  const cancel = r => { const why = prompt('Почему снимаем единицу? (проект в работу не пошёл…)'); if (why && why.trim().length >= 3) api(`/design/units/${r.deal_id}/cancel`, { method: 'POST', body: { reason: why.trim() } }).then(load, ex => alert(ex.message)) }
  const decide = (x, approve) => { const reason = approve ? null : prompt('Что не так? Главный дизайнер увидит это в карточке проекта.')
    if (!approve && !(reason || '').trim()) return
    api(`/design/extra/${x.id}/decide`, { method: 'POST', body: { approve, reason } }).then(load, ex => alert(ex.message)) }
  return <>{u?.wait?.length > 0 && <div className="card"><h3>Дизайн с объектов на утверждение · {u.wait.length}</h3>
    <p className="small muted">Из карточки проекта: дизайн проекта или правка/докидка на объекте. После «Утверждаю» — единицы дизайнеру в этом месяце.</p>
    {u.wait.map(x => <div key={x.id} className="row">
      <div><b>№{x.object_id} · {x.object_title}</b>
        <div className="small muted">{[x.kind === 'fix' ? 'правка / докидка' : 'дизайн проекта', x.person_name, `${x.size.toUpperCase()} · ${String(unitsOf(u, x.size)).replace('.', ',')} ед.`].join(' · ')}</div>
        <div className="small">{x.note}</div>
        {x.url && <button className="ghost mini catopen" onClick={() => openUrl(x.url)}>Посмотреть ↗</button>}</div>
      {u.can_cancel && <div className="qbtns"><button className="mini" onClick={() => decide(x, true)}>Утверждаю</button><button className="ghost mini" onClick={() => decide(x, false)}>Вернуть</button></div>}
    </div>)}</div>}
  <div className="card">
    <div className="head"><h2>Единицы</h2><input type="month" value={m} onChange={e => setM(e.target.value)} style={{ width: 'auto' }} /></div>
    {u && <><div className="kv"><div><span className="muted small">Мои за месяц</span><b>{String(u.mine).replace('.', ',')}</b></div>
      <div><span className="muted small">Норма</span><b>{u.norm != null ? u.norm : 'ждёт решения HEAD'}</b></div></div>
      <p className="small muted">Единица засчитывается, когда проект с твоим дизайном ушёл в работу или завершён: сделка на «Выполнении проекта», «Оплата+закрывающие» или «Оплата получена», и в ней ты — ответственный дизайнер. Месяц — по дню, когда проект ушёл в работу.</p>
      {u.nosize > 0 && <p className="small why">Без размера (XS–XL): {u.nosize} — единицы по ним 0, пока Главный дизайнер или HEAD не поставит сложность в карточке проекта.</p>}
      {u.unit_over && <p className="small muted">Сверх нормы — {money(u.unit_over)} за единицу (Главный дизайнер). Правки — счётчик кругов, без доплаты.</p>}
      {u.rows.map(r => <div key={r.deal_id} className="row">
        <div><b>{r.title || 'Сделка ' + r.deal_id}</b>
          <div className="small muted">{[r.full_name || 'дизайнер не связан', r.size ? r.size.toUpperCase() : 'размер не указан', dmy(r.approved_at), r.rounds ? `кругов правок: ${r.rounds}` : 'без правок',
            r.status === 'cancelled' && 'снято: ' + r.reason].filter(Boolean).join(' · ')}</div></div>
        <div className="qbtns"><b className={r.status === 'cancelled' ? 'muted' : ''}>{String(+r.units).replace('.', ',')}</b>
          {u.can_cancel && r.status === 'active' && <button className="ghost mini" onClick={() => cancel(r)}>Снять</button>}</div>
      </div>)}
      {(u.extras || []).map(x => <div key={'x' + x.id} className="row">
        <div><b>№{x.object_id} · {x.object_title}</b>
          <div className="small muted">{[x.kind === 'fix' ? 'правка / докидка' : 'дизайн проекта', x.person_name, x.size.toUpperCase(), dmy(x.decided_at), x.note].filter(Boolean).join(' · ')}</div></div>
        <div className="qbtns"><b>{String(+x.units).replace('.', ',')}</b></div>
      </div>)}
      {!u.rows.length && !(u.extras || []).length && <p className="small muted">За этот месяц проектов, ушедших в работу, нет. Посмотри прошлые месяцы.</p>}</>}
  </div></>
}

function Catalogs({ me }) {
  const [c, setC] = useState(null)
  const [form, setForm] = useState(null)
  const [msg, setMsg] = useState('')
  const [tab, setTab] = useState('')
  const team = useTeam()
  const load = () => api('/design/catalogs').then(setC, ex => setMsg(ex.message))
  useEffect(() => { load() }, [])
  if (!c) return <div className="card muted">{msg || 'Загрузка…'}</div>
  const act = (path, body) => api(path, { method: 'POST', body }).then(() => { setMsg(''); load() }, ex => setMsg(ex.message))
  const mine = r => r.authors.includes(me.id) || r.created_by === me.id
  // Списки по статусу: HEAD просил не мешать утверждённые и возвращённые в одну ленту.
  const by = st => c.rows.filter(r => st.includes(r.status))
  const tabs = (c.is_head
    ? [['sent', 'На решении', ['sent']], ['returned', 'Вернул', ['returned']], ['approved', 'Утверждено', ['approved']], ['draft', 'Черновики', ['draft']]]
    : [['returned', 'На переделку', ['returned']], ['draft', 'Черновики', ['draft']], ['sent', 'У HEAD', ['sent']], ['approved', 'Утверждено', ['approved']]])
    .map(([k, t, st]) => [k, t, by(st)]).filter(([k, , l]) => l.length || k === 'sent' || k === 'approved')
  const cur = tabs.find(t => t[0] === tab) || tabs.find(t => t[2].length) || tabs[0]
  const shown = cur ? cur[2] : []
  const empty = { sent: c.is_head ? 'Новых каталогов на решение нет.' : 'Сейчас у HEAD ничего нет.', approved: 'Утверждённых пока нет.', returned: 'Возвратов нет.', draft: 'Черновиков нет.' }
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
    {c.rows.length > 0 && <div className="segf dztabs">{tabs.map(([k, t, l]) => <button key={k} className={cur[0] === k ? 'on' : ''} onClick={() => setTab(k)}>{t}<b>{l.length}</b></button>)}</div>}
    {cur && cur[0] === 'returned' && shown.length > 0 && <p className="small muted">{c.is_head ? 'Вы вернули — исполнители переделывают названные страницы и отправляют снова.' : 'HEAD вернул — поправь, что написано, и отправь снова.'}</p>}
    {c.rows.length > 0 && !shown.length && <p className="small muted">{empty[cur[0]]}</p>}
    {shown.map(r => <div key={r.id} className="row">
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
