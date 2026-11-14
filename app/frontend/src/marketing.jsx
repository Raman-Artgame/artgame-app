import React, { useEffect, useState } from 'react'
import { api } from './api.js'
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
    <div className="segf">
      {head && <button className={view === 'review' ? 'on' : ''} onClick={() => setView('review')}>На утверждение{pending ? <span>{pending}</span> : null}</button>}
      <button className={view === 'plan' ? 'on' : ''} onClick={() => setView('plan')}>План</button>
      <button className={view === 'media' ? 'on' : ''} onClick={() => setView('media')}>Медиа</button>
    </div>
    {view === 'media' ? <Media /> : <Plan key={view + tick} review={view === 'review'} onOpen={setOpen} onNew={() => setEdit({})} />}
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
    {!review && <button onClick={onNew}>+ Публикация</button>}
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
