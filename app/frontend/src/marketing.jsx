import React, { useEffect, useState } from 'react'
import { api, webToken } from './api.js'
import { Viewer, download } from './objects.jsx'
import { Sheet } from './ui.jsx'

// Рабочее место маркетинга (HEAD 14.11): «План» — контент-план месяца, «Медиа» — материал с объектов,
// HEAD — «На утверждение». Каждую публикацию утверждает HEAD: черновик → «Отправить HEAD» → «Утверждаю» / «Вернуть»
// → после выхода «Опубликовано» со ссылкой. Неутверждённое отметить вышедшим нельзя (проверяет сервер).
const ST = { draft: ['черновик', ''], pending: ['у HEAD', 'warn'], approved: ['утверждено', 'ok'], rejected: ['вернул', 'hot'], published: ['вышло', 'ok'] }
const MTYPES = [['reels', 'Рилс'], ['video', 'Видео'], ['photo', 'Фото']]
const ymNow = () => new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Almaty' }).slice(0, 7)
const shift = (ym, d) => { const [y, m] = ym.split('-').map(Number); const t = new Date(y, m - 1 + d, 1); return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}` }
const monthName = ym => { const [y, m] = ym.split('-').map(Number); return new Date(y, m - 1, 1).toLocaleDateString('ru-RU', { month: 'long' }) + ' ' + y }
const day = s => s ? new Date(s + 'T00:00').toLocaleDateString('ru-RU', { weekday: 'short', day: 'numeric', month: 'short' }) : 'Без даты'

export function Marketing({ me, pending }) {
  const head = me.role_code === 'head'
  const [view, setView] = useState(head && pending ? 'review' : 'plan')
  const [edit, setEdit] = useState(null)   // {} — новая, {…post} — правка
  const [open, setOpen] = useState(null)
  const [tick, setTick] = useState(0)
  const reload = () => setTick(t => t + 1)
  return <>
    <div className="card dark prodhead"><span className="kick">Маркетинг</span>
      <h2>{head ? 'Публикации и материал' : 'Контент-план'}</h2>
      <p className="small muted">{head ? 'Каждая публикация выходит только после твоего «Утверждаю». Ниже — что ждёт решения и план месяца.'
        : 'Поставь публикацию в план: где, когда, текст и материал из «Медиа». Отправь HEAD — после «Утверждаю» выкладывай и отметь «Вышло» со ссылкой.'}</p>
    </div>
    <div className="segf mktnav">
      {head && <button className={view === 'review' ? 'on' : ''} onClick={() => setView('review')}>На утверждение{pending ? <span>{pending}</span> : null}</button>}
      {[['plan', 'План'], ['shoots', 'Съёмки'], ['ideas', 'Идеи'], ['media', 'Медиа']].map(([k, t]) =>
        <button key={k} className={view === k ? 'on' : ''} onClick={() => setView(k)}>{t}</button>)}
    </div>
    {view === 'media' ? <Media /> : view === 'shoots' ? <Shoots /> : view === 'ideas' ? <Ideas /> : <Plan key={view + tick} review={view === 'review'} onOpen={setOpen} onNew={() => setEdit({})} />}
    {edit && <Editor post={edit} onClose={() => setEdit(null)} onSaved={x => { setEdit(null); setOpen(x); reload() }} />}
    {open && !edit && <PostSheet post={open} head={head} onClose={() => setOpen(null)} onEdit={() => setEdit(open)}
      onChanged={x => { setOpen(x.status === 'cancelled' ? null : x); reload() }} />}
  </>
}

function Plan({ review, onOpen, onNew }) {
  const [ym, setYm] = useState(ymNow())
  const [d, setD] = useState(null)
  useEffect(() => { setD(null); api(review ? '/mkt/posts?status=pending' : `/mkt/posts?ym=${ym}`).then(setD, e => setD({ items: [], err: e.message })) }, [ym, review])
  const groups = d ? [...d.items.reduce((m, x) => m.set(x.plan_date || '', [...(m.get(x.plan_date || '') || []), x]), new Map())] : []
  return <div className="card">
    {!review && <div className="mktmonth"><button className="ghost mini" aria-label="Прошлый месяц" onClick={() => setYm(shift(ym, -1))}>‹</button>
      <b>{monthName(ym)}</b><button className="ghost mini" aria-label="Следующий месяц" onClick={() => setYm(shift(ym, 1))}>›</button></div>}
    {d && !review && <div className="mstats mkt4">
      <div><b>{d.counts.draft + d.counts.rejected}</b><span>черновики</span></div><div><b>{d.counts.pending}</b><span>у HEAD</span></div>
      <div><b>{d.counts.approved}</b><span>к выходу</span></div><div><b>{d.counts.published}</b><span>вышло</span></div></div>}
    {!review && <div className="seg"><button onClick={onNew}>+ Публикация</button><button className="ghost" onClick={() => exportCsv(ym)}>⬇ Выгрузить</button></div>}
    {!d ? <p className="muted">Загрузка…</p> : d.err ? <p className="small why">{d.err}</p> :
      !d.items.length ? <p className="muted small">{review ? 'Всё утверждено.' : 'В этом месяце пока пусто.'}</p> :
      groups.map(([dt, list]) => <div key={dt} className="mktday"><h3>{day(dt)}</h3>
        {list.map(x => <PostRow key={x.id} x={x} d={d} onOpen={onOpen} />)}</div>)}
  </div>
}

function PostRow({ x, d, onOpen }) {
  const f = x.files[0]
  return <div className="mitem mktrow" onClick={() => onOpen(x)}>
    <span className="mthumb">{f?.thumb ? <img src={f.thumb} alt="" loading="lazy" /> : <span>{x.kind === 'stories' ? '◐' : x.kind === 'post' || x.kind === 'carousel' ? '▦' : '▶'}</span>}</span>
    <div className="mbody"><b>{x.title}</b>
      <div className="small muted">{d.channels[x.channel]} · {d.kinds[x.kind]}{x.object_title ? ` · №${x.object_id} ${x.object_title}` : ''}</div>
      <span className={'badge ' + ST[x.status][1]} style={{ marginLeft: 0 }}>{ST[x.status][0]}</span>
      {x.result && <span className={'badge ' + (x.result === 'good' ? 'ok' : 'hot')}>{x.result === 'good' ? 'дала результат' : 'без результата'}</span>}
      {x.status === 'rejected' && x.review_note && <div className="small why">HEAD: {x.review_note}</div>}
    </div>
  </div>
}

function PostSheet({ post, head, onClose, onEdit, onChanged }) {
  const [d, setD] = useState(null)
  const [msg, setMsg] = useState('')
  const [url, setUrl] = useState('')
  const [note, setNote] = useState('')
  const [view, setView] = useState(null)
  useEffect(() => { api('/mkt/dict').then(setD, () => setD({ channels: {}, kinds: {} })) }, [])
  const x = post
  const act = (path, body) => { setMsg(''); api(`/mkt/posts/${x.id}/${path}`, { method: 'POST', body: body || {} }).then(onChanged, e => setMsg(e.message)) }
  return <Sheet title={x.title} onClose={onClose}>
    <span className={'badge ' + ST[x.status][1]} style={{ marginLeft: 0 }}>{ST[x.status][0]}</span>
    <p className="small muted">{day(x.plan_date)} · {d?.channels[x.channel]} · {d?.kinds[x.kind]}{x.object_title ? ` · №${x.object_id} ${x.object_title}` : ''} · {x.author}</p>
    {x.caption && <p className="mktcap">{x.caption}</p>}
    {x.files.length > 0 && <div className="mktfiles">{x.files.map(f => <button key={f.id} className="mthumb" onClick={() => setView(f)}>
      {f.thumb ? <img src={f.thumb} alt="" loading="lazy" /> : <span>▶</span>}</button>)}</div>}
    {x.review_note && <p className="small why">HEAD: {x.review_note}</p>}
    {x.url && <p className="small"><a href={x.url} target="_blank" rel="noreferrer">Открыть публикацию ›</a></p>}
    {msg && <p className="small why">{msg}</p>}
    {head && x.status === 'pending' && <>
      <div className="seg"><button onClick={() => act('review', { approve: true })}>Утверждаю</button>
        <button className="ghost" onClick={() => note.trim() ? act('review', { approve: false, note }) : setMsg('Напиши, что не так, — увидит автор.')}>Вернуть</button></div>
      <input placeholder="Что не так (для «Вернуть»)" value={note} onChange={e => setNote(e.target.value)} /></>}
    {['draft', 'rejected'].includes(x.status) && <div className="seg"><button onClick={() => act('submit')}>Отправить HEAD</button><button className="ghost" onClick={onEdit}>Править</button></div>}
    {x.status === 'approved' && <><label className="muted small">Ссылка на вышедшую публикацию</label>
      <input placeholder="https://instagram.com/…" value={url} onChange={e => setUrl(e.target.value)} />
      <button onClick={() => act('published', { url })}>Вышло</button></>}
    {x.status === 'published' && <Result x={x} act={act} />}
    {x.status !== 'published' && <button className="ghost mini" onClick={() => act('cancel')}>Отменить публикацию</button>}
    <Viewer f={view} onClose={() => setView(null)} />
  </Sheet>
}

function Editor({ post, onClose, onSaved }) {
  const [d, setD] = useState(null)
  const [objs, setObjs] = useState([])
  const [b, setB] = useState({ title: post.title || '', channel: post.channel || 'instagram', kind: post.kind || 'reels', plan_date: post.plan_date || '',
    caption: post.caption || '', object_id: post.object_id || '', files: post.files || [] })
  const [pick, setPick] = useState(false)
  const [msg, setMsg] = useState('')
  useEffect(() => { api('/mkt/dict').then(setD, e => setMsg(e.message)); api('/objects').then(setObjs, () => {}) }, [])
  const set = (k, v) => setB(s => ({ ...s, [k]: v }))
  const save = () => {
    if (!b.title.trim()) return setMsg('Напиши, что это за публикация.')
    const body = { title: b.title, channel: b.channel, kind: b.kind, plan_date: b.plan_date || null, caption: b.caption || null,
      object_id: b.object_id ? +b.object_id : null, file_ids: b.files.map(f => f.id) }
    api(post.id ? `/mkt/posts/${post.id}` : '/mkt/posts', { method: 'POST', body }).then(onSaved, e => setMsg(e.message))
  }
  if (pick) return <Sheet title="Материал из «Медиа»" onClose={() => setPick(false)}>
    <Media picked={b.files} onPick={files => { set('files', files); setPick(false) }} /></Sheet>
  return <Sheet title={post.id ? 'Правка публикации' : 'Новая публикация'} onClose={onClose}>
    <label className="muted small">Что выходит</label>
    <input placeholder="Например: рилс «Кафе до/после»" value={b.title} onChange={e => set('title', e.target.value)} />
    {d && <><label className="muted small">Где</label>
      <div className="chips">{Object.entries(d.channels).map(([k, t]) => <button key={k} className={b.channel === k ? 'on' : ''} onClick={() => set('channel', k)}>{t}</button>)}</div>
      <label className="muted small">Формат</label>
      <div className="chips">{Object.entries(d.kinds).map(([k, t]) => <button key={k} className={b.kind === k ? 'on' : ''} onClick={() => set('kind', k)}>{t}</button>)}</div></>}
    <label className="muted small">Дата выхода</label>
    <input type="date" value={b.plan_date} onChange={e => set('plan_date', e.target.value)} />
    <label className="muted small">Текст публикации</label>
    <textarea rows={4} placeholder="Подпись, хэштеги, призыв" value={b.caption} onChange={e => set('caption', e.target.value)} />
    <label className="muted small">Проект (если про объект)</label>
    <select value={b.object_id} onChange={e => set('object_id', e.target.value)}><option value="">Не про проект</option>
      {objs.map(o => <option key={o.id} value={o.id}>№{o.id} {o.title}</option>)}</select>
    <label className="muted small">Материал · {b.files.length}</label>
    {b.files.length > 0 && <div className="mktfiles">{b.files.map(f => <span key={f.id} className="mthumb">{f.thumb ? <img src={f.thumb} alt="" /> : <span>▶</span>}</span>)}</div>}
    <button className="ghost" onClick={() => setPick(true)}>🎬 Выбрать из «Медиа»</button>
    {msg && <p className="small why">{msg}</p>}
    <button onClick={save}>Сохранить</button>
    <p className="small muted">Сохранится черновиком. HEAD увидит, когда нажмёшь «Отправить HEAD».</p>
  </Sheet>
}

// «Медиа»: весь материал с объектов от команды (кроме возвращённого HEAD); «Лучшее» — только утверждённое HEAD (Продакшн).
// С onPick — выбор материала для публикации.
function Media({ picked, onPick }) {
  const [type, setType] = useState('reels')
  const [best, setBest] = useState(false)
  const [d, setD] = useState(null)
  const [obj, setObj] = useState('')
  const [open, setOpen] = useState(null)
  const [sel, setSel] = useState(picked || [])
  useEffect(() => { setD(null); api(`/media?scope=library&type=${type}${best ? '&best=1' : ''}`).then(setD, e => setD({ items: [], err: e.message })) }, [type, best])
  const objs = d ? [...new Map(d.items.map(x => [x.object_id, `№${x.object_id} ${x.object_title}`])).entries()] : []
  const items = d ? d.items.filter(x => !obj || x.object_id === +obj) : []
  const on = x => sel.some(s => s.id === x.id)
  const flip = x => setSel(s => on(x) ? s.filter(y => y.id !== x.id) : [...s, x])
  return <div className={onPick ? '' : 'card'}>
    {!onPick && <p className="small muted">Материал с объектов от команды. «Лучшее» — то, что HEAD утвердил в «Продакшн».</p>}
    <div className="seg">{MTYPES.map(([k, t]) => <button key={k} className={type === k ? '' : 'ghost'} onClick={() => { setType(k); setObj('') }}>{t}</button>)}</div>
    <div className="chips"><button className={best ? '' : 'on'} onClick={() => setBest(false)}>Всё</button><button className={best ? 'on' : ''} onClick={() => setBest(true)}>Лучшее</button></div>
    {objs.length > 1 && <select value={obj} onChange={e => setObj(e.target.value)}><option value="">Все объекты</option>
      {objs.map(([id, t]) => <option key={id} value={id}>{t}</option>)}</select>}
    {!d ? <p className="muted">Загрузка…</p> : d.err ? <p className="small why">{d.err}</p> : !items.length ? <p className="muted small">Пока пусто.</p> :
      items.map(x => <div key={x.id} className={'mitem' + (onPick && on(x) ? ' picked' : '')}>
        <button className="mthumb" onClick={() => onPick ? flip(x) : setOpen(x)}>{x.thumb ? <img src={x.thumb} alt="" loading="lazy" /> : <span>{onPick && on(x) ? '✓' : '▶'}</span>}</button>
        <div className="mbody"><a onClick={() => onPick ? flip(x) : setOpen(x)}><b>{x.name}</b></a>
          <div className="small muted">№{x.object_id} {x.object_title} · {x.by} · {new Date(x.created_at).toLocaleDateString('ru-RU')}{x.review === 'approved' ? ' · в Продакшн' : ''}</div></div>
        {onPick ? <button className={'mini' + (on(x) ? '' : ' ghost')} aria-label="Выбрать" onClick={() => flip(x)}>{on(x) ? '✓' : '+'}</button>
          : <button className="ghost mini" aria-label="Скачать" onClick={() => download(x)}>⬇</button>}
      </div>)}
    {onPick && <button onClick={() => onPick(sel)}>Готово · выбрано {sel.length}</button>}
    <Viewer f={open} onClose={() => setOpen(null)} />
  </div>
}

// Итог вышедшей публикации (HEAD 14.11: «что даёт результат, а что нет»): просмотры, заявки, «дала результат» / «без результата».
function Result({ x, act }) {
  const [v, setV] = useState({ views: x.views ?? '', leads: x.leads ?? '', note: x.result_note || '' })
  const num = t => t === '' ? null : Math.max(0, parseInt(t, 10) || 0)
  const save = result => act('result', { result, views: num(v.views), leads: num(v.leads), note: v.note || null })
  return <div className="mktres"><h3>Итог</h3>
    <div className="seg"><input inputMode="numeric" placeholder="Просмотры" value={v.views} onChange={e => setV({ ...v, views: e.target.value })} />
      <input inputMode="numeric" placeholder="Заявки" value={v.leads} onChange={e => setV({ ...v, leads: e.target.value })} /></div>
    <input placeholder="Что сработало / что нет" value={v.note} onChange={e => setV({ ...v, note: e.target.value })} />
    <div className="seg"><button className={x.result === 'good' ? '' : 'ghost'} onClick={() => save('good')}>Дала результат</button>
      <button className={x.result === 'weak' ? '' : 'ghost'} onClick={() => save('weak')}>Без результата</button></div>
  </div>
}

// Выгрузка плана месяца в таблицу (CSV: Excel, Google Таблицы)
async function exportCsv(ym) {
  const init = window.Telegram?.WebApp?.initData
  const h = init ? { 'X-Telegram-Init-Data': init } : webToken() ? { Authorization: `Bearer ${webToken()}` } : {}
  const r = await fetch(`/api/mkt/posts.csv?ym=${ym}`, { headers: h })
  if (!r.ok) return
  const a = document.createElement('a'); a.href = URL.createObjectURL(await r.blob()); a.download = `content-plan-${ym}.csv`
  document.body.appendChild(a); a.click(); a.remove()
}

// «Идеи»: сценарии и задумки (по проекту и вне). Взяли в съёмку — «в работе», сняли — «снято».
const IST = { new: ['новая', 'warn'], work: ['в работе', ''], done: ['снято', 'ok'], dropped: ['отложено', 'hot'] }
function Ideas() {
  const [d, setD] = useState(null)
  const [edit, setEdit] = useState(null)
  const load = () => api('/mkt/ideas').then(setD, e => setD({ items: [], err: e.message }))
  useEffect(() => { load() }, [])
  return <div className="card">
    <p className="small muted">Сценарии, задумки, раскадровки. Из идеи потом ставится съёмка и публикация.</p>
    <button onClick={() => setEdit({})}>+ Идея</button>
    {!d ? <p className="muted">Загрузка…</p> : d.err ? <p className="small why">{d.err}</p> : !d.items.length ? <p className="muted small">Идей пока нет.</p> :
      d.items.map(x => <div key={x.id} className="mktidea" onClick={() => setEdit(x)}>
        <b>{x.title}</b><span className={'badge ' + IST[x.status][1]}>{IST[x.status][0]}</span>
        <div className="small muted">{d.kinds[x.kind]}{x.object_title ? ` · №${x.object_id} ${x.object_title}` : ' · вне проектов'} · {x.author}</div>
        {x.text && <p className="small mktclip">{x.text}</p>}</div>)}
    {edit && <IdeaEditor x={edit} kinds={d?.kinds || {}} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load() }} />}
  </div>
}

function IdeaEditor({ x, kinds, onClose, onSaved }) {
  const [b, setB] = useState({ title: x.title || '', text: x.text || '', kind: x.kind || 'reels', object_id: x.object_id || '', status: x.status || 'new' })
  const [objs, setObjs] = useState([])
  const [msg, setMsg] = useState('')
  useEffect(() => { api('/objects').then(setObjs, () => {}) }, [])
  const set = (k, v) => setB(s => ({ ...s, [k]: v }))
  const save = () => b.title.trim() ? api(x.id ? `/mkt/ideas/${x.id}` : '/mkt/ideas', { method: 'POST', body: { ...b, object_id: b.object_id ? +b.object_id : null } })
    .then(onSaved, e => setMsg(e.message)) : setMsg('Назови идею.')
  return <Sheet title={x.id ? 'Идея' : 'Новая идея'} onClose={onClose}>
    <input placeholder="Например: говорящая голова — как мы рисуем" value={b.title} onChange={e => set('title', e.target.value)} />
    <div className="chips">{Object.entries(kinds).map(([k, t]) => <button key={k} className={b.kind === k ? 'on' : ''} onClick={() => set('kind', k)}>{t}</button>)}</div>
    <textarea rows={7} placeholder="Сценарий: кадры, текст, музыка, кто в кадре" value={b.text} onChange={e => set('text', e.target.value)} />
    <select value={b.object_id} onChange={e => set('object_id', e.target.value)}><option value="">Вне проектов</option>
      {objs.map(o => <option key={o.id} value={o.id}>№{o.id} {o.title}</option>)}</select>
    {x.id && <div className="chips">{Object.entries(IST).map(([k, [t]]) => <button key={k} className={b.status === k ? 'on' : ''} onClick={() => set('status', k)}>{t}</button>)}</div>}
    {msg && <p className="small why">{msg}</p>}
    <button onClick={save}>Сохранить</button>
  </Sheet>
}

// «Съёмки»: график на месяц — что, когда, где, кто снимает; по проекту или вне проектов (студия, интервью).
function Shoots() {
  const [ym, setYm] = useState(ymNow())
  const [d, setD] = useState(null)
  const [edit, setEdit] = useState(null)
  const load = () => api(`/mkt/shoots?ym=${ym}`).then(setD, e => setD({ items: [], team: [], err: e.message }))
  useEffect(() => { setD(null); load() }, [ym])
  const groups = d ? [...d.items.reduce((m, x) => m.set(x.shoot_date, [...(m.get(x.shoot_date) || []), x]), new Map())] : []
  return <div className="card">
    <div className="mktmonth"><button className="ghost mini" aria-label="Прошлый месяц" onClick={() => setYm(shift(ym, -1))}>‹</button>
      <b>{monthName(ym)}</b><button className="ghost mini" aria-label="Следующий месяц" onClick={() => setYm(shift(ym, 1))}>›</button></div>
    <button onClick={() => setEdit({})}>+ Съёмка</button>
    {!d ? <p className="muted">Загрузка…</p> : d.err ? <p className="small why">{d.err}</p> : !d.items.length ? <p className="muted small">Съёмок в этом месяце нет.</p> :
      groups.map(([dt, list]) => <div key={dt} className="mktday"><h3>{day(dt)}</h3>
        {list.map(x => <div key={x.id} className="mktidea" onClick={() => setEdit(x)}>
          <b>{x.at_time ? `${x.at_time} · ` : ''}{x.title}</b>{x.status === 'done' && <span className="badge ok">снято</span>}{x.status === 'proposed' && <span className="badge warn">{x.alt_date ? 'ГИП предлагает ' + x.alt_date.slice(8, 10) + '.' + x.alt_date.slice(5, 7) : 'ждёт ГИП'}</span>}
          <div className="small muted">{x.object_title ? `№${x.object_id} ${x.object_title}` : 'вне проектов'}{x.place ? ` · ${x.place}` : ''}</div>
          {x.crew_names && <div className="small">🎥 {x.crew_names.join(', ')}</div>}
          {x.idea_title && <div className="small muted">Идея: {x.idea_title}</div>}</div>)}</div>)}
    {edit && <ShootEditor x={edit} team={d?.team || []} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load() }} />}
  </div>
}

function ShootEditor({ x, team, onClose, onSaved }) {
  const [b, setB] = useState({ title: x.title || '', shoot_date: x.shoot_date || '', at_time: x.at_time || '', object_id: x.object_id || '',
    place: x.place || '', crew: x.crew || [], idea_id: x.idea_id || '', note: x.note || '', status: x.status || 'planned' })
  const [objs, setObjs] = useState([])
  const [ideas, setIdeas] = useState([])
  const [msg, setMsg] = useState('')
  useEffect(() => { api('/objects').then(setObjs, () => {}); api('/mkt/ideas').then(r => setIdeas(r.items.filter(i => i.status !== 'dropped')), () => {}) }, [])
  const set = (k, v) => setB(s => ({ ...s, [k]: v }))
  const flip = id => set('crew', b.crew.includes(id) ? b.crew.filter(c => c !== id) : [...b.crew, id])
  const save = (status = b.status) => {
    if (!b.title.trim() || !b.shoot_date) return setMsg('Нужны название и дата.')
    api(x.id ? `/mkt/shoots/${x.id}` : '/mkt/shoots', { method: 'POST', body: { ...b, status, object_id: b.object_id ? +b.object_id : null,
      idea_id: b.idea_id ? +b.idea_id : null, at_time: b.at_time || null, place: b.place || null, note: b.note || null } }).then(onSaved, e => setMsg(e.message))
  }
  return <Sheet title={x.id ? 'Съёмка' : 'Новая съёмка'} onClose={onClose}>
    <input placeholder="Что снимаем" value={b.title} onChange={e => set('title', e.target.value)} />
    <label className="muted small">Дата и время</label>
    <input type="date" value={b.shoot_date} onChange={e => set('shoot_date', e.target.value)} />
    <input placeholder="Время, например 11:00" value={b.at_time} onChange={e => set('at_time', e.target.value)} />
    <select value={b.object_id} onChange={e => set('object_id', e.target.value)}><option value="">Вне проектов</option>
      {objs.map(o => <option key={o.id} value={o.id}>№{o.id} {o.title}</option>)}</select>
    <input placeholder="Место (адрес, студия)" value={b.place} onChange={e => set('place', e.target.value)} />
    <label className="muted small">Кто снимает</label>
    <div className="chips">{team.map(t => <button key={t.id} className={b.crew.includes(t.id) ? 'on' : ''} onClick={() => flip(t.id)}>{t.full_name}</button>)}</div>
    {ideas.length > 0 && <select value={b.idea_id} onChange={e => set('idea_id', e.target.value)}><option value="">Без идеи</option>
      {ideas.map(i => <option key={i.id} value={i.id}>{i.title}</option>)}</select>}
    <textarea rows={3} placeholder="Что взять, кого позвать, план кадров" value={b.note} onChange={e => set('note', e.target.value)} />
    {msg && <p className="small why">{msg}</p>}
    <button onClick={() => save()}>Сохранить</button>
    {x.id && b.status === 'planned' && <div className="seg"><button className="ghost" onClick={() => save('done')}>Снято ✓</button>
      <button className="ghost" onClick={() => save('cancelled')}>Отменить</button></div>}
  </Sheet>
}
