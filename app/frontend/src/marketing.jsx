import React, { useEffect, useState } from 'react'
import { api, uuid, webToken } from './api.js'
import { Viewer, download, uploadBig, sendToGoogle } from './objects.jsx'
import { Sheet } from './ui.jsx'
import { Kit, StoryHome } from './mktkit.jsx'

// Рабочее место маркетинга (HEAD 14.11): «План» — контент-план месяца, «Медиа» — материал с объектов,
// HEAD — «На утверждение». Каждую публикацию утверждает HEAD: черновик → «Отправить HEAD» → «Утверждаю» / «Вернуть»
// → после выхода «Опубликовано» со ссылкой. Неутверждённое отметить вышедшим нельзя (проверяет сервер).
const ST = { draft: ['черновик', ''], check: ['на проверке', 'warn'], pending: ['у HEAD', 'warn'], approved: ['утверждено', 'ok'], rejected: ['вернул', 'hot'], published: ['вышло', 'ok'] }
const MTYPES = [['reels', 'Рилс'], ['video', 'Видео'], ['photo', 'Фото']]
const ymNow = () => new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Almaty' }).slice(0, 7)
const shift = (ym, d) => { const [y, m] = ym.split('-').map(Number); const t = new Date(y, m - 1 + d, 1); return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}` }
const monthName = ym => { const [y, m] = ym.split('-').map(Number); return new Date(y, m - 1, 1).toLocaleDateString('ru-RU', { month: 'long' }) + ' ' + y }
const day = s => s ? new Date(s + 'T00:00').toLocaleDateString('ru-RU', { weekday: 'short', day: 'numeric', month: 'short' }) : 'Без даты'

// Задача в отделе (HEAD 14.11): руководитель видит всё и проверяет первой; остальные — свои вкладки и свои действия.
const JOB = { lead: 'Руководитель отдела', smm: 'Контент и публикации', stories: 'Сторис и баннеры', target: 'Таргет', video: 'Съёмка' }
const TABS = { stories: ['plan', 'story', 'media', 'brand'], target: ['ads', 'plan', 'brand'], video: ['shoots', 'ideas', 'media', 'plan', 'brand'] }
const ABOUT = { lead: 'Ты видишь всё. Публикации коллег сначала приходят тебе в «Проверку», после твоего «Проверено» уходят HEAD.',
  smm: 'Поставь публикацию в план: где, когда, текст и материал. Отправь на утверждение, после «Утверждаю» выкладывай и отметь «Вышло» со ссылкой.',
  stories: 'Собери сторис во вкладке «Сторис» из рамок и элементов бренда или загрузи готовую, поставь в публикацию и отправь на утверждение. Выкладывать можно только утверждённое.',
  target: 'В «Рекламе» — расход и заявки по площадкам. Новую рекламу ставь в план форматом «Реклама»: запускать можно только после «Утверждаю».',
  video: 'В «Съёмках» — что, где и когда снимать. В «Идеях» — сценарии. Материал с объектов — в «Медиа».' }

export function Marketing({ me, pending }) {
  const head = me.role_code === 'head'
  const job = head ? 'head' : (me.mkt_job || null)
  const can = { post: head || [null, 'lead', 'smm', 'stories', 'target'].includes(job), onlyAd: job === 'target', all: head || [null, 'lead', 'smm'].includes(job),
    idea: job !== 'target', shoot: head || [null, 'lead', 'smm', 'video'].includes(job), result: head || [null, 'lead', 'smm', 'target'].includes(job) }
  const tabs = [['plan', 'План'], ...(can.post && !can.onlyAd ? [['story', 'Сторис']] : []), ['shoots', 'Съёмки'], ['ideas', 'Идеи'], ['media', 'Медиа'], ['ads', 'Реклама'], ['brand', 'Бренд']].filter(([k]) => !TABS[job] || TABS[job].includes(k))
    .sort((a, b) => TABS[job] ? TABS[job].indexOf(a[0]) - TABS[job].indexOf(b[0]) : 0)
  const [toCheck, setToCheck] = useState(0)
  const [view, setView] = useState(head && pending ? 'review' : tabs[0][0])
  const [edit, setEdit] = useState(null)   // {} — новая, {…post} — правка
  const [open, setOpen] = useState(null)
  const [tick, setTick] = useState(0)
  const reload = () => setTick(t => t + 1)
  // Сторис из редактора: файл уходит в «Готовые публикации»; дальше — в новую публикацию или просто скачать
  const publishStory = async (file, how) => { const f = await uploadReady(file, () => {}); how === 'post' ? setEdit({ kind: 'stories', files: [f] }) : download(f) }
  useEffect(() => { if (job === 'lead') api('/mkt/posts?status=check').then(d => setToCheck(d.items.length), () => {}) }, [tick, view])
  return <>
    <div className="card dark prodhead"><span className="kick">Маркетинг{JOB[job] ? ` · ${JOB[job]}` : ''}</span>
      <h2>{head ? 'Публикации и материал' : job === 'video' ? 'Что и где снимать' : job === 'target' ? 'Реклама' : 'Контент-план'}</h2>
      <p className="small muted">{head ? 'Каждая публикация выходит только после твоего «Утверждаю». Ниже — что ждёт решения и план месяца.' : ABOUT[job] || ABOUT.smm}</p>
    </div>
    <div className="segf mktnav">
      {head && <button className={view === 'review' ? 'on' : ''} onClick={() => setView('review')}>На утверждение{pending ? <span>{pending}</span> : null}</button>}
      {job === 'lead' && <button className={view === 'check' ? 'on' : ''} onClick={() => setView('check')}>Проверка{toCheck ? <span>{toCheck}</span> : null}</button>}
      {tabs.map(([k, t]) => <button key={k} className={view === k ? 'on' : ''} onClick={() => setView(k)}>{t}</button>)}
    </div>
    {view === 'review' || view === 'check' ? <Review key={view + tick} lead={view === 'check'} onOpen={setOpen} /> : view === 'media' ? <Media canUp={job !== 'target'} /> : view === 'brand' ? <Brand canPost={can.post && !can.onlyAd} onPublish={publishStory} /> : view === 'ads' ? <Ads /> : view === 'story' ? <StoryHome canPost onPublish={publishStory} /> :
      view === 'shoots' ? <Shoots can={can.shoot} /> : view === 'ideas' ? <Ideas can={can.idea} /> : <Plan key={view + tick} can={can.post} onOpen={setOpen} onNew={() => setEdit({})} />}
    {edit && <Editor post={edit} onlyAd={can.onlyAd} onClose={() => setEdit(null)} onSaved={x => { setEdit(null); setOpen(x); reload() }} />}
    {open && !edit && <PostSheet post={open} head={head} mine={can.post && (can.all || open.author_id === me.id)} canResult={can.result} onClose={() => setOpen(null)} onEdit={() => setEdit(open)}
      onChanged={x => { setOpen(x.status === 'cancelled' ? null : x); reload() }} />}
  </>
}

// «Бренд»: книга бренда и паки из папки Диска «06 МАРКЕТИНГ / 01 Бренд» — смотреть и скачивать, без доступа к Диску.
const fsize = b => !b ? '' : b > 1e6 ? (b / 1e6).toFixed(1) + ' МБ' : Math.ceil(b / 1e3) + ' КБ'
// «Бренд» (HEAD 14.11): книга как история по главам + полки по задачам. Из главы — сразу к нужной полке и скачать.
export function Brand({ canPost, onPublish }) {
  const [kit, setKit] = useState(false)
  const [root, setRoot] = useState(null)
  const [ch, setCh] = useState(null)        // открытая глава
  const [shelf, setShelf] = useState('')
  useEffect(() => { api('/mkt/brand').then(setRoot, e => setRoot({ err: e.message, shelves: [], book: [] })) }, [])
  const top = () => window.scrollTo(0, 0)
  if (!root) return <div className="card"><p className="muted">Загрузка…</p></div>
  if (kit) return <Kit canPost={canPost} onPublish={onPublish} onBack={() => { setKit(false); top() }} />
  if (shelf) return <Shelf k={shelf} sources={root.sources} onBack={() => { setShelf(''); top() }} />
  const names = Object.fromEntries(root.shelves.map(x => [x.key, x]))
  if (ch) {
    const i = root.book.findIndex(x => x.key === ch), c = root.book[i]
    return <div className="card bbook">
      <div className="mktcrumbs"><button className="ghost mini" onClick={() => { setCh(null); top() }}>‹ Книга бренда</button><span>Глава {c.n} из {root.book.length}</span></div>
      <div className="bbcover"><span className="bbnum">{String(c.n).padStart(2, '0')}</span><h2>{c.title}</h2><em>{c.word}</em><img src={'/kit/' + c.art} alt="" /></div>
      <p className="bblead">{c.lead}</p>
      {c.blocks.map((b, j) => <Block key={j} b={b} />)}
      <div className="bbrules"><b>Из этого следует</b>{c.rules.map((r, j) => <div key={j}><i>{j + 1}</i><span>{r}</span></div>)}</div>
      {c.shelves.length > 0 && <div className="bbget"><b>Что скачать к этой главе</b>
        {c.shelves.map(k => <div key={k} className="mktfolder" onClick={() => { setShelf(k); top() }}><span className="bbico">{names[k].icon}</span><b>{names[k].title}</b><i>⬇</i></div>)}</div>}
      <div className="seg">{i > 0 && <button className="ghost" onClick={() => { setCh(root.book[i - 1].key); top() }}>‹ Назад</button>}
        {i < root.book.length - 1 ? <button onClick={() => { setCh(root.book[i + 1].key); top() }}>Дальше ›</button> : <button onClick={() => { setCh(null); top() }}>К полкам</button>}</div>
    </div>
  }
  return <>
    {root.err && <div className="card"><p className="small why">{root.err}</p></div>}
    <div className="card bbhome">
      <div className="bbhero"><img className="bblogo" src="/kit/t_logo/logo_pill_outline_white.png" alt="ARTGAME" /><h2>Книга <span>бренда</span></h2><em>искусство, которое живёт на стенах</em>
        <img className="bbst a" src="/kit/t_stickers/star_3d_crimson.png" alt="" /><img className="bbst b" src="/kit/t_stickers/cloud_white_1.png" alt="" /></div>
      <p className="small muted">Восемь коротких глав. По ней строится каждая публикация и каждая реклама.</p>
      <div className="bbchs">{root.book.map(c => <button key={c.key} className="bbch" onClick={() => { setCh(c.key); top() }}><i>{String(c.n).padStart(2, '0')}</i><img src={'/kit/' + c.art.replace('t_stickers/', 't/t_stickers/').replace('.png', '.webp')} alt="" /><b>{c.title}</b></button>)}</div>
    </div>
    <div className="card">
      <h3>Пак элементов</h3>
      <p className="small muted">Стикеры, плашки, логотипы в плашке, рамки сторис, фоны, элементы для видео. Каждый можно скачать отдельно{canPost ? '. Сторис собирается во вкладке «Сторис».' : ' или собрать сторис прямо здесь.'}</p>
      <button onClick={() => { setKit(true); top() }}>Открыть пак элементов</button>
    </div>
    <div className="card">
      <h3>Скачать для работы</h3>
      <p className="small muted">{root.sources ? 'Готовые файлы и исходники. Берём только отсюда.' : 'Готовые файлы для работы. Берём только отсюда, ничего не рисуем заново.'}</p>
      <div className="bbshelves">{root.shelves.map(x => <button key={x.key} className="bbshelf" onClick={() => { setShelf(x.key); top() }}>
        <span className="bbico">{x.icon}</span><b>{x.title}</b><span className="small muted">{x.hint}</span>
        {x.who !== 'all' && <span className="badge">{x.who === 'head' ? 'только HEAD' : 'дизайн и HEAD'}</span>}</button>)}</div>
    </div>
  </>
}

function Block({ b }) {
  if (b.t === 'h') return <h4>{b.x}</h4>
  if (b.t === 'ok' || b.t === 'no') return <div className={'bbsay ' + b.t}><u>{b.t === 'ok' ? 'Так' : 'Не так'}</u><span>{b.x}</span>{b.why && <em>{b.why}</em>}</div>
  if (b.t === 'imgs') return <div className={'bbimgs' + (b.tall ? ' tall' : '')}>{b.x.map(([f, t]) => <figure key={f}><img src={'/kit/' + f} alt="" loading="lazy" /><figcaption>{t}</figcaption></figure>)}</div>
  if (b.t === 'colors') return <div className="bbcolors">{b.x.map(([n, hex, use]) => <div key={hex}><i style={{ background: hex }} /><b>{n}</b><span className="small muted">{hex} · {use}</span></div>)}</div>
  if (b.t === 'steps') return <ol className="bbsteps">{b.x.map((x, i) => <li key={i}>{x}</li>)}</ol>
  if (b.t === 'zone') return <div className={'bbzone ' + b.c}><b>{b.title}</b><ul>{b.x.map((x, i) => <li key={i}>{x}</li>)}</ul></div>
  if (b.t === 'test') return <Test items={b.x} />
  return <p>{b.x}</p>
}

function Test({ items }) {
  const [on, setOn] = useState({})
  const n = items.filter((_, i) => on[i]).length
  return <div className="bbtest">{items.map((x, i) => <label key={i} className="check"><input type="checkbox" checked={!!on[i]} onChange={e => setOn({ ...on, [i]: e.target.checked })} /> <span>{x}</span></label>)}
    <div className={'bbverdict ' + (n === items.length ? 'ok' : '')}>{n === items.length ? 'Все семь на месте. Можно отправлять на утверждение.' : `Отмечено ${n} из ${items.length}. Не публикуем.`}</div></div>
}

function Shelf({ k, sources, onBack }) {
  const [folder, setFolder] = useState('')
  const [d, setD] = useState(null)
  const [view, setView] = useState(null)
  useEffect(() => { setD(null); api(`/mkt/brand?shelf=${k}` + (folder ? `&folder=${encodeURIComponent(folder)}` : '')).then(setD, e => setD({ err: e.message, path: [], folders: [], files: [] })) }, [k, folder])
  return <div className="card">
    <div className="mktcrumbs"><button className="ghost mini" onClick={onBack}>‹ Бренд</button>
      {d?.shelf && <><span>›</span><button className={'ghost mini' + (!folder ? ' on' : '')} onClick={() => setFolder('')}>{d.shelf.title}</button></>}
      {d?.path.map(x => <React.Fragment key={x.id}><span>›</span><button className={'ghost mini' + (x.id === folder ? ' on' : '')} onClick={() => setFolder(x.id)}>{x.name}</button></React.Fragment>)}</div>
    {d?.shelf && !folder && <p className="small muted">{d.shelf.hint}</p>}
    {!d ? <p className="muted">Загрузка…</p> : d.err ? <p className="small why">{d.err}</p> : !d.folders.length && !d.files.length ? <p className="muted small">{d.hidden ? 'Здесь только исходники. Они у дизайнеров.' : 'Здесь пока пусто.'}</p> : <>
      {d.folders.map(x => <div key={x.id} className="mktfolder" onClick={() => setFolder(x.id)}><span>📁</span><b>{x.name}</b><i>›</i></div>)}
      {d.files.length > 0 && <div className="mktgrid">{d.files.map(f => <div key={f.id} className="mktfile">
        <button className="mthumb" onClick={() => setView(f)}>{f.thumb ? <img src={f.thumb} alt="" loading="lazy" onError={e => { e.target.style.display = 'none' }} /> : null}<span>{(f.name.split('.').pop() || '').slice(0, 4).toUpperCase()}</span></button>
        <div className="small">{f.name}</div><div className="small muted">{fsize(f.size)}{f.source ? ' · исходник' : ''}</div>
        <button className="ghost mini" onClick={() => download(f)}>⬇ Скачать</button></div>)}</div>}
      {d.hidden > 0 && <p className="small muted">Исходники ({d.hidden}) лежат у дизайнеров. Нужен исходник: напиши в чат HEAD.</p>}</>}
    <Viewer f={view} onClose={() => setView(null)} />
  </div>
}

// «Реклама» (HEAD 14.11): по каждой площадке — расход, заявки, сделки, цена заявки; что работает, а что сливает бюджет.
const tg = n => Math.round(n || 0).toLocaleString('ru-RU') + ' ₸'
const VERDICT = { works: ['работает', 'ok'], weak: ['заявки есть, сделок нет', 'warn'], burns: ['сливает бюджет', 'hot'] }
function AdChannels() {
  const [ym, setYm] = useState(ymNow())
  const [d, setD] = useState(null)
  const [edit, setEdit] = useState(null)   // площадка: расход, фраза, ссылка
  const [phone, setPhone] = useState(null)
  const [msg, setMsg] = useState('')
  const load = () => api(`/mkt/ads?ym=${ym}`).then(setD, e => setD({ items: [], err: e.message, unknown: { leads: 0 }, total: { leads: 0, spend: 0 } }))
  useEffect(() => { setD(null); load() }, [ym])
  return <div className="card">
    <div className="mktmonth"><button className="ghost mini" aria-label="Прошлый месяц" onClick={() => setYm(shift(ym, -1))}>‹</button>
      <b>{monthName(ym)}</b><button className="ghost mini" aria-label="Следующий месяц" onClick={() => setYm(shift(ym, 1))}>›</button></div>
    {!d ? <p className="muted">Загрузка…</p> : <>
      {d.err && <p className="small why">{d.err}</p>}
      <div className="mstats mkt4 mkt2"><div><b>{tg(d.total.spend)}</b><span>расход за месяц</span></div><div><b>{d.total.leads}</b><span>заявок всего</span></div></div>
      {d.unknown.leads > 0 && <p className="small why">Без площадки: {d.unknown.leads} из {d.total.leads} заявок. МОП отмечает «Откуда клиент» в лиде, а со своих ссылок площадка ставится сама.</p>}
      {d.can_edit && !d.wa_phone && <p className="small muted">Чтобы площадки считались сами, укажи номер WhatsApp для заявок. <a onClick={() => setPhone('')}>Указать</a></p>}
      {d.items.map(x => <div key={x.id} className="mktad" onClick={() => d.can_edit && setEdit(x)}>
        <div className="mktadh"><b>{x.title}</b>{VERDICT[x.verdict] && <span className={'badge ' + VERDICT[x.verdict][1]}>{VERDICT[x.verdict][0]}</span>}</div>
        <div className="mktadn"><div><b>{x.paid ? tg(x.spend) : '—'}</b><span>расход</span></div><div><b>{x.leads}</b><span>заявки</span></div>
          <div><b>{x.deals}</b><span>сделки</span></div><div><b>{x.cpl ? tg(x.cpl) : '—'}</b><span>цена заявки</span></div></div>
        {x.won > 0 && <div className="small muted">Выиграно: {x.won} на {tg(x.won_sum)}</div>}
        {x.paid && !x.spend && d.can_edit && <div className="small muted">Расход не внесён. Нажми, чтобы внести.</div>}
      </div>)}
      {d.can_edit && <div className="seg"><button className="ghost" onClick={() => setEdit({ paid: true, active: true })}>+ Площадка</button>
        {d.wa_phone && <button className="ghost" onClick={() => setPhone(d.wa_phone)}>Номер WhatsApp</button>}</div>}
      <p className="small muted">Заявки и сделки берутся из Битрикса. Расход «Таргет Instagram» приходит из Meta сам каждую ночь, по остальным площадкам вносится раз в месяц.</p>
    </>}
    <MetaBox ym={ym} onChange={load} />
    {msg && <p className="small muted">{msg}</p>}
    {edit && <AdSheet x={edit} ym={ym} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load() }} />}
    {phone !== null && <Sheet title="Номер WhatsApp для заявок" onClose={() => setPhone(null)}>
      <p className="small muted">Номер, на который пишут клиенты. По нему собираются ссылки для объявлений.</p>
      <input inputMode="tel" placeholder="7 705 123 45 67" value={phone} onChange={e => setPhone(e.target.value)} />
      <button onClick={() => api('/mkt/wa_phone', { method: 'POST', body: { phone } }).then(() => { setPhone(null); load() }, e => setMsg(e.message))}>Сохранить</button>
    </Sheet>}
  </div>
}

// «Реклама» целиком (HEAD 24.11: «чтобы у меня всегда была статистика по всем процессам и рекомендации у таргетолога»):
// сверху подсказки «антислив», ниже — площадки, кампании Meta или отчёт за неделю/месяц.
function Ads() {
  const [tab, setTab] = useState('ch')
  return <>
    <AdHints />
    <div className="chips adtabs">{[['ch', 'Площадки'], ['camp', 'Кампании'], ['rep', 'Отчёт']].map(([k, t]) =>
      <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{t}</button>)}</div>
    {tab === 'ch' ? <AdChannels /> : tab === 'camp' ? <AdCampaigns /> : <AdReport />}
  </>
}

function AdHints() {
  const [d, setD] = useState(null)
  const [msg, setMsg] = useState('')
  const load = () => api('/mkt/adstats?days=7').then(setD, () => setD(null))
  useEffect(() => { load() }, [])
  if (!d || (!d.hints.length && !d.missing.length)) return null
  return <div className="card adhints">
    {d.hints.length > 0 && <div className="mktadh"><b>Подсказки по рекламе</b><span className="badge hot">{d.hints.length}</span></div>}
    {d.hints.map(h => <div key={h.id} className="adhint">
      <div className="mktadh"><b>{h.rule_ru}</b><span className="small muted">{new Date(h.created_at).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })}</span></div>
      <p className="small">{h.text}</p>
      <p className="small why">Что сделать: {h.advice}</p>
      {d.can_edit && <button className="ghost mini" onClick={() => api(`/mkt/adhints/${h.id}/done`, { method: 'POST', body: {} }).then(load, e => setMsg(e.message))}>Сделано</button>}
    </div>)}
    {d.missing.length > 0 && <p className="small muted">{d.missing.length === 5 ? 'Подсказки пока молчат' : 'Часть подсказок молчит'}: в листе «Значения» не заданы {d.missing.map(m => m.what).join('; ')}.</p>}
    {msg && <p className="small why">{msg}</p>}
  </div>
}

function AdCampaigns() {
  const [days, setDays] = useState(7)
  const [d, setD] = useState(null)
  const [open, setOpen] = useState(null)
  useEffect(() => { setD(null); api(`/mkt/adstats?days=${days}`).then(setD, e => setD({ campaigns: [], err: e.message })) }, [days])
  const nums = x => <div className="mktadn"><div><b>{tg(x.spend)}</b><span>расход</span></div><div><b>{x.results}</b><span>обращения</span></div>
    <div><b>{x.cpr ? tg(x.cpr) : '—'}</b><span>цена обращения</span></div><div><b>{x.ctr != null ? x.ctr + '%' : '—'}</b><span>CTR</span></div></div>
  return <div className="card">
    <div className="chips">{[[1, 'Сегодня'], [7, '7 дней'], [30, '30 дней']].map(([k, t]) => <button key={k} className={days === k ? 'on' : ''} onClick={() => setDays(k)}>{t}</button>)}</div>
    {!d ? <p className="muted">Загрузка…</p> : <>
      {d.err && <p className="small why">{d.err}</p>}
      {d.plan_cpl && <p className="small muted">Плановая цена заявки: {tg(d.plan_cpl)}</p>}
      {!d.campaigns.length && <p className="muted">За этот период в Meta нет расхода. Данные обновляются каждую ночь.</p>}
      {d.campaigns.map(c => <div key={c.campaign_id} className="mktad" onClick={() => setOpen(open === c.campaign_id ? null : c.campaign_id)}>
        <div className="mktadh"><b>{c.name}</b>{c.ads.some(a => a.hint) && <span className="badge hot">есть подсказка</span>}</div>
        {nums(c)}
        <div className="small muted">{num(c.impressions)} показов · {num(c.clicks)} кликов · объявлений: {c.ads.length}{open === c.campaign_id ? '' : ' · нажми, чтобы раскрыть'}</div>
        {open === c.campaign_id && c.ads.map(a => <div key={a.ad_id} className="adrow">
          <div className="mktadh"><span>{a.ad_name || a.ad_id}</span>{a.hint && <span className="badge hot">проверь</span>}</div>
          {nums(a)}
          <div className="small muted">{a.adset_name || ''}{a.frequency ? ` · частота ${a.frequency.toFixed(1)}` : ''} · {num(a.clicks)} кликов</div>
        </div>)}
      </div>)}
      <p className="small muted">Обращения считает сама Meta: начатые переписки и заявки с форм. Заявки и продажи по Битриксу смотри в «Отчёте».</p>
    </>}
  </div>
}

const dm = iso => new Date(iso).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })
function AdReport() {
  const [period, setPeriod] = useState('week')
  const [shiftN, setShiftN] = useState(0)
  const [r, setR] = useState(null)
  useEffect(() => { setR(null); api(`/mkt/report?period=${period}&shift=${shiftN}`).then(setR, e => setR({ err: e.message, channels: [], total: {}, unknown: {}, meta: {}, ig: {} })) }, [period, shiftN])
  return <div className="card">
    <div className="chips">{[['week', 'Неделя'], ['month', 'Месяц']].map(([k, t]) => <button key={k} className={period === k ? 'on' : ''} onClick={() => { setPeriod(k); setShiftN(0) }}>{t}</button>)}</div>
    <div className="mktmonth"><button className="ghost mini" aria-label="Раньше" onClick={() => setShiftN(shiftN - 1)}>‹</button>
      <b>{r && r.from ? `${dm(r.from)} — ${dm(r.to)}` : '…'}</b><button className="ghost mini" aria-label="Позже" disabled={shiftN >= 0} onClick={() => setShiftN(shiftN + 1)}>›</button></div>
    {!r ? <p className="muted">Загрузка…</p> : <>
      {r.err && <p className="small why">{r.err}</p>}
      <div className="repflow"><div><b>{tg(r.total.spend)}</b><span>потрачено</span></div><i>→</i><div><b>{r.total.leads ?? 0}</b><span>заявок</span></div><i>→</i>
        <div><b>{r.total.won ?? 0}</b><span>продаж</span></div><i>→</i><div><b>{r.total.cpl ? tg(r.total.cpl) : '—'}</b><span>цена заявки</span></div></div>
      {r.total.won_sum > 0 && <p className="small muted">Продано на {tg(r.total.won_sum)}</p>}
      {r.channels.map(c => <div key={c.id} className="mktad static">
        <div className="mktadh"><b>{c.title}</b>{c.paid && c.spend > 0 && !c.leads && <span className="badge hot">расход без заявок</span>}</div>
        <div className="mktadn"><div><b>{c.spend ? (c.approx ? '≈ ' : '') + tg(c.spend) : '—'}</b><span>потрачено</span></div><div><b>{c.leads}</b><span>заявок</span></div>
          <div><b>{c.won}</b><span>продаж</span></div><div><b>{c.cpl ? tg(c.cpl) : '—'}</b><span>цена заявки</span></div></div>
        {c.won > 0 && <div className="small muted">Продано на {tg(c.won_sum)}{c.cps ? ` · цена продажи ${tg(c.cps)}` : ''}</div>}
      </div>)}
      {r.unknown.leads > 0 && <p className="small why">Без площадки: {r.unknown.leads} заявок. Пока МОП не отметит «Откуда клиент», цена заявки по площадкам занижена.</p>}
      {r.channels.some(c => c.approx) && <p className="small muted">«≈» — расход внесён раз в месяц, на неделю взята его доля по дням.</p>}
      <div className="mktadh"><b>Meta и Instagram за период</b></div>
      <div className="mktadn"><div><b>{num(r.meta.impressions)}</b><span>показы рекламы</span></div><div><b>{num(r.meta.clicks)}</b><span>клики</span></div>
        <div><b>{num(r.meta.results)}</b><span>обращения</span></div><div><b>{r.ig.delta != null ? (r.ig.delta >= 0 ? '+' : '') + r.ig.delta : '—'}</b><span>подписчики</span></div></div>
      <div className="mktadn"><div><b>{num(r.ig.reach)}</b><span>охват Instagram</span></div><div><b>{num(r.ig.views)}</b><span>просмотры</span></div>
        <div><b>{num(r.ig.profile_views)}</b><span>в профиль</span></div><div><b>{num(r.ig.followers)}</b><span>всего подписчиков</span></div></div>
      <p className="small muted">Заявки и продажи — из Битрикса по дате заявки. По понедельникам отчёт за прошлую неделю сам ложится файлом на Диск в «04 ОТЧЁТЫ / Неделя».</p>
    </>}
  </div>
}

// Meta напрямую (HEAD 24.11): расход кабинета и статистика Instagram, собирается ночью и по кнопке.
const num = n => n == null ? '—' : Math.round(n).toLocaleString('ru-RU')
const when = iso => new Date(iso).toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
function MetaBox({ ym, onChange }) {
  const [m, setM] = useState(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const load = () => api(`/mkt/meta?ym=${ym}`).then(setM, () => setM(null))
  useEffect(() => { load() }, [ym])
  if (!m) return null
  const run = (url, ok) => { setBusy(true); setMsg(''); api(url, { method: 'POST' }).then(r => { setMsg(r.errors?.length ? '' : ok); load(); onChange() }, e => setMsg(e.message)).finally(() => setBusy(false)) }
  const kzt = m.ads.find(a => a.currency === 'KZT'), other = m.ads.filter(a => a.currency !== 'KZT')
  const w = m.ig.week
  return <div className="metabox">
    <div className="mktadh"><b>Meta и Instagram</b>{m.last && <span className={'badge ' + (m.last.ok && !m.last.errors.length ? 'ok' : 'warn')}>{m.last.ok && !m.last.errors.length ? 'собрано' : 'собрано не всё'}</span>}</div>
    {!m.on ? <p className="small why">Токен Meta на сервере не найден, цифры не обновляются.</p> : !m.last && <p className="small muted">Ещё ни разу не собиралось. Первый сбор пройдёт ночью.</p>}
    {m.last && <p className="small muted">Обновлено {when(m.last.at)}</p>}
    {(m.last?.errors || []).map((e, i) => <p key={i} className="small why">{e}</p>)}
    {kzt && <><div className="mktadn"><div><b>{tg(kzt.spend)}</b><span>расход в Meta</span></div><div><b>{num(kzt.impressions)}</b><span>показы</span></div>
      <div><b>{num(kzt.clicks)}</b><span>клики</span></div><div><b>{kzt.clicks ? tg(kzt.spend / kzt.clicks) : '—'}</b><span>цена клика</span></div></div>
      <p className="small muted">За {monthName(ym)}, данные по {kzt.upto.slice(8)}-е число.</p></>}
    {other.map(a => <p key={a.currency} className="small why">Кабинет в валюте {a.currency || '?'}: {a.spend.toLocaleString('ru-RU')} {a.currency}. В расход в тенге не добавлено.</p>)}
    {m.manual && <p className="small why">За этот месяц расход «Таргет Instagram» внесён руками, Meta его не меняет.
      {m.can_edit && <> <a onClick={() => run(`/mkt/meta/take?ym=${ym}`, 'Расход взят из Meta.')}>Взять из Meta</a></>}</p>}
    {m.ig.followers != null && <div className="mktadn"><div><b>{num(m.ig.followers)}</b><span>подписчики{m.ig.delta7 != null ? ` (${m.ig.delta7 >= 0 ? '+' : ''}${m.ig.delta7} за 7 дн.)` : ''}</span></div>
      <div><b>{num(w.reach)}</b><span>охват, {w.days || 0} дн.</span></div><div><b>{num(w.views)}</b><span>просмотры</span></div><div><b>{num(w.profile_views)}</b><span>в профиль</span></div></div>}
    {m.ig.top.length > 0 && <><p className="small muted">Лучшее за 30 дней по просмотрам</p>
      {m.ig.top.map(t => <a key={t.id} className="metatop" href={t.permalink} target="_blank" rel="noreferrer">
        <span>{t.kind === 'REELS' ? 'Рилс' : 'Пост'} · {(t.caption || 'без подписи').slice(0, 40)}</span><b>{num(t.views)}</b></a>)}</>}
    {m.can_edit && m.on && <button className="ghost" disabled={busy} onClick={() => run('/mkt/meta/sync', 'Обновлено.')}>{busy ? 'Собираю, до минуты…' : 'Обновить сейчас'}</button>}
    {msg && <p className="small muted">{msg}</p>}
  </div>
}

function AdSheet({ x, ym, onClose, onSaved }) {
  const [b, setB] = useState({ title: x.title || '', phrase: x.phrase || '', paid: x.paid !== false, active: x.active !== false, amount: x.spend ? String(x.spend) : '' })
  const [msg, setMsg] = useState('')
  const save = async () => {
    if (b.title.trim().length < 2) return setMsg('Назови площадку.')
    try {
      const r = await api(x.id ? `/mkt/channels/${x.id}` : '/mkt/channels', { method: 'POST', body: { title: b.title, phrase: b.phrase || null, paid: b.paid, active: b.active } })
      if (b.paid && b.amount !== '' && +b.amount !== (x.spend || 0)) await api('/mkt/spend', { method: 'POST', body: { channel_id: r.id, ym, amount: +b.amount || 0 } })
      onSaved()
    } catch (e) { setMsg(e.message) }
  }
  return <Sheet title={x.id ? x.title : 'Новая площадка'} onClose={onClose}>
    <label className="muted small">Название</label>
    <input value={b.title} placeholder="Например: Крыша.kz" onChange={e => setB({ ...b, title: e.target.value })} />
    <label className="small muted check"><input type="checkbox" checked={b.paid} onChange={e => setB({ ...b, paid: e.target.checked })} /> Платная площадка</label>
    {b.paid && <><label className="muted small">Расход за {monthName(ym)}, ₸</label>
      <input inputMode="numeric" placeholder="0" value={b.amount} onChange={e => setB({ ...b, amount: e.target.value.replace(/[^\d]/g, '') })} /></>}
    <label className="muted small">Первая фраза клиента в ссылке</label>
    <textarea rows={2} placeholder="Здравствуйте! Пишу с …" value={b.phrase} onChange={e => setB({ ...b, phrase: e.target.value })} />
    {x.link && <><label className="muted small">Ссылка для объявления</label><p className="mktcap mktlink">{x.link}</p>
      <button className="ghost" onClick={() => copyText(x.link).then(ok => setMsg(ok ? 'Ссылка скопирована. Поставь её в объявление кнопкой «Написать в WhatsApp».' : 'Выдели ссылку и скопируй вручную.'))}>Скопировать ссылку</button></>}
    {x.id && <label className="small muted check"><input type="checkbox" checked={b.active} onChange={e => setB({ ...b, active: e.target.checked })} /> Площадка работает <span>· выключенная пропадает из списка, история остаётся</span></label>}
    {msg && <p className="small why">{msg}</p>}
    <button onClick={save}>Сохранить</button>
  </Sheet>
}

const isVid = f => (f.mime || '').startsWith('video/') || (!(f.mime || '').startsWith('image/') && (f.media_type === 'video' || f.media_type === 'reels'))
const copyText = t => { try { return navigator.clipboard.writeText(t).then(() => true, () => false) } catch { return Promise.resolve(false) } }

// Готовый файл от агентства — прямо в Google, в «06 МАРКЕТИНГ / 04 Готовые публикации»; сервер сверяет результат.
function uploadReady(file, onProgress) {
  return api('/mkt/uploads', { method: 'POST', body: { client_uid: uuid(), name: file.name, mime: file.type || 'application/octet-stream', size: file.size } })
    .then(r => r.done ? r.file : new Promise((ok, fail) => {
      const x = new XMLHttpRequest()
      x.open('PUT', r.upload_url)
      x.upload.onprogress = e => onProgress(e.loaded / e.total)
      x.onload = () => x.status < 300 ? ok(JSON.parse(x.responseText)) : fail(new Error('Google ' + x.status))
      x.onerror = () => fail(new Error('нет сети'))
      x.send(file)
    }).then(g => api(`/mkt/uploads/${r.file_id}/done`, { method: 'POST', body: { drive_id: g.id } })))
}

// HEAD: лента «На утверждение» вместо WhatsApp — публикация на весь экран, «Утверждаю» / «Вернуть», следующая сама.
function Review({ onOpen, lead }) {
  const [d, setD] = useState(null)
  const [i, setI] = useState(0)
  const [fi, setFi] = useState(0)
  const [back, setBack] = useState(false)
  const [note, setNote] = useState('')
  const [msg, setMsg] = useState('')
  const load = () => api(`/mkt/posts?status=${lead ? 'check' : 'pending'}`).then(setD, e => setD({ items: [], err: e.message }))
  useEffect(() => { load() }, [])
  if (!d) return <div className="card"><p className="muted">Загрузка…</p></div>
  if (d.err) return <div className="card"><p className="small why">{d.err}</p></div>
  if (!d.items.length) return <div className="card"><p className="muted small">{lead ? 'Всё проверено. Новое от коллег появится здесь.' : 'Всё утверждено. Новое появится здесь.'}</p></div>
  const n = d.items.length, x = d.items[Math.min(i, n - 1)], f = x.files[Math.min(fi, x.files.length - 1)]
  const sameDay = d.items.filter(y => y.plan_date === x.plan_date).length
  const go = k => { setI(Math.max(0, Math.min(n - 1, k))); setFi(0); setBack(false); setNote(''); setMsg('') }
  const drop = ids => { const items = d.items.filter(y => !ids.includes(y.id)); setD({ ...d, items }); setI(v => Math.max(0, Math.min(v, items.length - 1))); setFi(0); setBack(false); setNote(''); setMsg(''); window.dispatchEvent(new Event('artgame:pulse')) }
  const review = body => api(`/mkt/posts/${x.id}/${lead ? 'check' : 'review'}`, { method: 'POST', body }).then(() => drop([x.id]), e => setMsg(e.message))
  const all = () => api('/mkt/review_day', { method: 'POST', body: { plan_date: x.plan_date } })
    .then(() => drop(d.items.filter(y => y.plan_date === x.plan_date).map(y => y.id)), e => setMsg(e.message))
  return <div className="card mktfeed">
    <div className="mktbars">{d.items.map((y, k) => <span key={y.id} className={k === Math.min(i, n - 1) ? 'on' : ''} onClick={() => go(k)} />)}</div>
    <div className="mktstage">
      {!f ? <div className="mkttext">{x.caption}</div> : isVid(f) ? <video key={f.id} src={f.url} controls playsInline preload="metadata" /> : <img key={f.id} src={f.url} alt="" />}
      <div className="mkttop"><b>{d.kinds[x.kind]} · {x.author}</b><span>{d.channels[x.channel]} · выход {day(x.plan_date)}</span></div>
      {n > 1 && <><button className="mktarr l" aria-label="Назад" disabled={i === 0} onClick={() => go(i - 1)}>‹</button>
        <button className="mktarr r" aria-label="Дальше" disabled={i >= n - 1} onClick={() => go(i + 1)}>›</button></>}
    </div>
    {x.files.length > 1 && <div className="mktfiles">{x.files.map((y, k) => <button key={y.id} className={'mthumb' + (k === fi ? ' on' : '')} onClick={() => setFi(k)}>
      {y.thumb ? <img src={y.thumb} alt="" loading="lazy" /> : <span>▶</span>}</button>)}</div>}
    <b className="mkttitle" onClick={() => onOpen(x)}>{x.title}{x.object_title ? ` · №${x.object_id} ${x.object_title}` : ''}</b>
    {f && x.caption && <p className="mktcap">{x.caption}</p>}
    {msg && <p className="small why">{msg}</p>}
    {back ? <><input autoFocus placeholder="Что не так — увидит автор" value={note} onChange={e => setNote(e.target.value)} />
      <div className="seg"><button onClick={() => note.trim() ? review({ approve: false, note }) : setMsg('Напиши, что поправить.')}>Вернуть на доработку</button>
        <button className="ghost" onClick={() => { setBack(false); setMsg('') }}>Отмена</button></div></> :
      <div className="seg"><button onClick={() => review({ approve: true })}>{lead ? 'Проверено' : 'Утверждаю'}</button><button className="ghost" onClick={() => setBack(true)}>Вернуть</button></div>}
    {!back && !lead && sameDay > 1 && <button className="ghost" onClick={all}>Утвердить все {sameDay} на {day(x.plan_date)}</button>}
    <p className="small muted mktcount">{Math.min(i, n - 1) + 1} из {n}{x.checked ? ` · проверено: ${x.checked}` : ''}</p>
  </div>
}

function Plan({ can, onOpen, onNew }) {
  const review = false
  const [ym, setYm] = useState(ymNow())
  const [d, setD] = useState(null)
  useEffect(() => { setD(null); api(review ? '/mkt/posts?status=pending' : `/mkt/posts?ym=${ym}`).then(setD, e => setD({ items: [], err: e.message })) }, [ym, review])
  const groups = d ? [...d.items.reduce((m, x) => m.set(x.plan_date || '', [...(m.get(x.plan_date || '') || []), x]), new Map())] : []
  return <div className="card">
    {!review && <div className="mktmonth"><button className="ghost mini" aria-label="Прошлый месяц" onClick={() => setYm(shift(ym, -1))}>‹</button>
      <b>{monthName(ym)}</b><button className="ghost mini" aria-label="Следующий месяц" onClick={() => setYm(shift(ym, 1))}>›</button></div>}
    {d && !review && <div className="mstats mkt4">
      <div><b>{d.counts.draft + d.counts.rejected}</b><span>черновики</span></div><div><b>{d.counts.pending + (d.counts.check || 0)}</b><span>на утверждении</span></div>
      <div><b>{d.counts.approved}</b><span>к выходу</span></div><div><b>{d.counts.published}</b><span>вышло</span></div></div>}
    {d?.norms?.length > 0 && <div className="mktnorms"><span className="small muted">Объём месяца по договору</span>
      {d.norms.map(n => <div key={n.kind} className="mktnorm"><div><b>{n.title}{n.behind && <span className="badge hot">отстаёт</span>}</b><span className="small muted">в плане {n.planned} из {n.per_month} · вышло {n.done}</span></div>
        <i><em className={n.planned >= n.per_month ? 'ok' : ''} style={{ width: Math.min(100, n.per_month ? n.planned / n.per_month * 100 : 0) + '%' }} /><u style={{ width: Math.min(100, n.per_month ? n.done / n.per_month * 100 : 0) + '%' }} /></i></div>)}</div>}
    <div className="seg">{can && <button onClick={onNew}>+ Публикация</button>}<button className="ghost" onClick={() => exportCsv(ym)}>⬇ Выгрузить</button></div>
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
      {x.status === 'rejected' && x.review_note && <div className="small why">{x.reviewer || 'HEAD'}: {x.review_note}</div>}
    </div>
  </div>
}

function PostSheet({ post, head, mine, canResult, onClose, onEdit, onChanged }) {
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
    {x.review_note && <p className="small why">{x.reviewer || 'HEAD'}: {x.review_note}</p>}
    {x.checked && <p className="small muted">Проверено: {x.checked}</p>}
    {x.url && <p className="small"><a href={x.url} target="_blank" rel="noreferrer">Открыть публикацию ›</a></p>}
    {msg && <p className="small why">{msg}</p>}
    {head && x.status === 'pending' && <>
      <div className="seg"><button onClick={() => act('review', { approve: true })}>Утверждаю</button>
        <button className="ghost" onClick={() => note.trim() ? act('review', { approve: false, note }) : setMsg('Напиши, что не так, — увидит автор.')}>Вернуть</button></div>
      <input placeholder="Что не так (для «Вернуть»)" value={note} onChange={e => setNote(e.target.value)} /></>}
    {mine && ['draft', 'rejected'].includes(x.status) && <div className="seg"><button onClick={() => act('submit')}>Отправить на утверждение</button><button className="ghost" onClick={onEdit}>Править</button></div>}
    {mine && x.status === 'approved' && <><label className="muted small">Ссылка на вышедшую публикацию</label>
      <input placeholder="https://instagram.com/…" value={url} onChange={e => setUrl(e.target.value)} />
      <button onClick={() => act('published', { url })}>Вышло</button></>}
    {['approved', 'published'].includes(x.status) && x.files.some(isVid) && <button className="ghost" onClick={() => {
      download(x.files.find(isVid)); copyText(x.caption || '').then(ok => setMsg(ok ? 'Видео скачивается, текст скопирован. Открой TikTok и вставь.' : 'Видео скачивается. Текст скопируй из блока выше.')) }}>♪ Для TikTok: видео и текст</button>}
    {canResult && x.status === 'published' && <Result x={x} act={act} />}
    {mine && x.status !== 'published' && <button className="ghost mini" onClick={() => act('cancel')}>Отменить публикацию</button>}
    <Viewer f={view} onClose={() => setView(null)} />
  </Sheet>
}

function Editor({ post, onlyAd, onClose, onSaved }) {
  const [d, setD] = useState(null)
  const [objs, setObjs] = useState([])
  const [b, setB] = useState({ title: post.title || '', channel: post.channel || 'instagram', kind: post.kind || (onlyAd ? 'ad' : 'reels'), plan_date: post.plan_date || '',
    caption: post.caption || '', object_id: post.object_id || '', files: post.files || [] })
  const [pick, setPick] = useState(false)
  const [msg, setMsg] = useState('')
  const [up, setUp] = useState(null)   // доля загруженного, пока файл идёт на Диск
  const addReady = async list => {
    setMsg('')
    for (const file of list) {
      setUp(0)
      try { const f = await uploadReady(file, setUp); setB(s => ({ ...s, files: [...s.files, f] })) }
      catch (e) { setMsg(`${file.name}: ${e.message}`) }
    }
    setUp(null)
  }
  useEffect(() => { api('/mkt/dict').then(setD, e => setMsg(e.message)); api('/objects').then(setObjs, () => {}) }, [])
  const set = (k, v) => setB(s => ({ ...s, [k]: v }))
  const save = () => {
    if (up !== null) return setMsg('Дождись конца загрузки.')
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
      <div className="chips">{Object.entries(d.kinds).filter(([k]) => !onlyAd || k === 'ad').map(([k, t]) => <button key={k} className={b.kind === k ? 'on' : ''} onClick={() => set('kind', k)}>{t}</button>)}</div></>}
    <label className="muted small">Дата выхода</label>
    <input type="date" value={b.plan_date} onChange={e => set('plan_date', e.target.value)} />
    <label className="muted small">Текст публикации</label>
    <textarea rows={4} placeholder="Подпись, хэштеги, призыв" value={b.caption} onChange={e => set('caption', e.target.value)} />
    <label className="muted small">Проект (если про объект)</label>
    <select value={b.object_id} onChange={e => set('object_id', e.target.value)}><option value="">Не про проект</option>
      {objs.map(o => <option key={o.id} value={o.id}>№{o.id} {o.title}</option>)}</select>
    <label className="muted small">Материал · {b.files.length}</label>
    {b.files.length > 0 && <div className="mktfiles">{b.files.map(f => <span key={f.id} className="mthumb">{f.thumb ? <img loading="lazy" src={f.thumb} alt="" /> : <span>▶</span>}
      <button className="mktdel" aria-label="Убрать" onClick={() => set('files', b.files.filter(x => x.id !== f.id))}>×</button></span>)}</div>}
    <label className={'photo mktup' + (up !== null ? ' busy' : '')}>{up !== null ? `Загрузка… ${Math.round(up * 100)}%` : '⬆ Загрузить готовое (рилс, сторис, баннер)'}
      <input type="file" accept="video/*,image/*" multiple hidden disabled={up !== null} onChange={e => { const fs = [...e.target.files]; e.target.value = ''; addReady(fs) }} /></label>
    <button className="ghost" onClick={() => setPick(true)}>🎬 Выбрать из «Медиа»</button>
    {msg && <p className="small why">{msg}</p>}
    <button onClick={save}>Сохранить</button>
    <p className="small muted">Сохранится черновиком. На утверждение уйдёт, когда нажмёшь «Отправить на утверждение».</p>
  </Sheet>
}

// «Медиа»: весь материал с объектов от команды (кроме возвращённого HEAD); «Лучшее» — только утверждённое HEAD (Продакшн).
// С onPick — выбор материала для публикации.
// Исходник от агентства — прямо в рубрику на Диске («02 КОНТЕНТ / рубрика / Исходники / дата название»), частями, с докачкой.
function uploadSrc(file, where, onProgress) {
  return api('/mkt/src/uploads', { method: 'POST', body: { client_uid: uuid(), name: file.name, mime: file.type || 'application/octet-stream', size: file.size, ...where } })
    .then(r => r.done ? r : sendToGoogle(r.upload_url, file, onProgress).then(g => api(`/mkt/src/uploads/${r.file_id}/done`, { method: 'POST', body: { drive_id: g.id } })))
}

function Media({ picked, onPick, canUp }) {
  const [up, setUp] = useState(null)   // {mode: obj|rub, obj, rub, title, type, pct, msg}
  const [objsAll, setObjsAll] = useState(null)
  const [type, setType] = useState('reels')
  const [best, setBest] = useState(false)
  const [d, setD] = useState(null)
  const [f, setF] = useState({ q: '', year: '', city: '', tag: '' })    // поиск и фильтры (HEAD 24.11)
  const [tagsOf, setTagsOf] = useState(null)
  const [open, setOpen] = useState(null)
  const [sel, setSel] = useState(picked || [])
  const [tick, setTick] = useState(0)
  useEffect(() => {
    const t = setTimeout(() => {
      const qs = new URLSearchParams({ type, ...(best ? { best: 1 } : {}), ...Object.fromEntries(Object.entries(f).filter(([, v]) => v)) })
      api('/mkt/library?' + qs).then(setD, e => setD({ items: [], err: e.message, rubrics: [], years: [], cities: [] }))
    }, f.q ? 350 : 0)
    return () => clearTimeout(t)
  }, [type, best, f, tick])
  const items = d ? d.items : []
  const rname = id => (d?.rubrics || []).find(r => r.id === id)?.title
  const on = x => sel.some(s => s.id === x.id)
  const flip = x => setSel(s => on(x) ? s.filter(y => y.id !== x.id) : [...s, x])
  const send = async e => {
    const fs = [...e.target.files]; e.target.value = ''; let msg = ''
    for (const file of fs) {
      setUp(u => ({ ...u, pct: 0 }))
      try {
        if (up.mode === 'rub') await uploadSrc(file, { rubric_id: +up.rub, title: up.title }, pct => setUp(u => ({ ...u, pct })))
        else await uploadBig(+up.obj, 'media', file, pct => setUp(u => ({ ...u, pct })), { media_type: up.type })
      } catch (err) { msg = `${file.name}: ${err.message}` }
    }
    setUp(u => ({ ...u, pct: null, msg: msg || `Загружено: ${fs.length}. ${up.mode === 'rub' ? 'Лежит в папке рубрики «Исходники».' : 'Лежит в папке сделки «МЕДИА / Отчёты».'}` }))
    setType(up.type); setBest(false); setTick(t => t + 1)
  }
  return <div className={onPick ? '' : 'card'}>
    {!onPick && <p className="small muted">Материал с объектов и исходники по рубрикам. Ищи по проекту, городу, году или метке. «Лучшее» — то, что HEAD утвердил в «Продакшн».</p>}
    {!onPick && canUp && !up && <button className="ghost" onClick={() => { setUp({ mode: 'rub', obj: '', rub: '', title: '', type: 'video', pct: null, msg: '' }); if (!objsAll) api('/objects').then(setObjsAll, () => setObjsAll([])) }}>⬆ Загрузить снятое</button>}
    {up && <div className="mktupbox">
      <div className="chips">{[['rub', 'В рубрику'], ['obj', 'На объект']].map(([k, t]) => <button key={k} className={up.mode === k ? 'on' : ''} onClick={() => setUp({ ...up, mode: k, msg: '' })}>{t}</button>)}</div>
      {up.mode === 'rub' ? <>
        <label className="muted small">Рубрика</label>
        <select value={up.rub} onChange={e => setUp({ ...up, rub: e.target.value })}><option value="">— выбери рубрику —</option>
          {(d?.rubrics || []).filter(r => !r.project).map(r => <option key={r.id} value={r.id}>{r.title}</option>)}</select>
        <label className="muted small">Что снимали</label>
        <input placeholder="Например: интервью с художником" maxLength={80} value={up.title} onChange={e => setUp({ ...up, title: e.target.value })} />
      </> : <>
        <label className="muted small">Проект</label>
        <select value={up.obj} onChange={e => setUp({ ...up, obj: e.target.value })}><option value="">— выбери проект —</option>
          {(objsAll || []).map(o => <option key={o.id} value={o.id}>№{o.id} {o.title}</option>)}</select>
      </>}
      <div className="chips">{[['video', 'Видео'], ['photo', 'Фото']].map(([k, t]) => <button key={k} className={up.type === k ? 'on' : ''} onClick={() => setUp({ ...up, type: k })}>{t}</button>)}</div>
      {(up.mode === 'rub' ? up.rub && up.title.trim() : up.obj) ? <label className={'photo mktup' + (up.pct !== null ? ' busy' : '')}>{up.pct !== null ? `Загрузка… ${Math.round(up.pct * 100)}%` : '⬆ Выбрать файлы'}
        <input type="file" accept={up.type === 'photo' ? 'image/*' : 'video/*'} multiple hidden disabled={up.pct !== null} onChange={send} /></label>
        : <p className="small muted">{up.mode === 'rub' ? 'Выбери рубрику и напиши, что снимали: так назовётся папка.' : 'Выбери проект.'}</p>}
      {up.msg && <p className="small muted">{up.msg}</p>}
      <button className="ghost mini" onClick={() => setUp(null)}>Закрыть</button></div>}
    <div className="seg">{MTYPES.map(([k, t]) => <button key={k} className={type === k ? '' : 'ghost'} onClick={() => setType(k)}>{t}</button>)}</div>
    <input className="mktsearch" type="search" placeholder="Поиск: проект, город, название" value={f.q} onChange={e => setF({ ...f, q: e.target.value })} />
    <div className="mktfilters">
      <select aria-label="Рубрика" value={f.tag} onChange={e => setF({ ...f, tag: e.target.value })}><option value="">Рубрика</option>
        {(d?.rubrics || []).map(r => <option key={r.id} value={r.id}>{r.title}</option>)}</select>
      <select aria-label="Год" value={f.year} onChange={e => setF({ ...f, year: e.target.value })}><option value="">Год</option>
        {(d?.years || []).map(y => <option key={y} value={y}>{y}</option>)}</select>
      <select aria-label="Город" value={f.city} onChange={e => setF({ ...f, city: e.target.value })}><option value="">Город</option>
        {(d?.cities || []).map(c => <option key={c} value={c}>{c}</option>)}</select></div>
    <div className="chips"><button className={best ? '' : 'on'} onClick={() => setBest(false)}>Всё</button><button className={best ? 'on' : ''} onClick={() => setBest(true)}>Лучшее</button></div>
    {!d ? <p className="muted">Загрузка…</p> : d.err ? <p className="small why">{d.err}</p> : !items.length ? <p className="muted small">Пока пусто.</p> :
      items.map(x => <div key={x.id} className={'mitem' + (onPick && on(x) ? ' picked' : '')}>
        <button className="mthumb" onClick={() => onPick ? flip(x) : setOpen(x)}>{x.thumb ? <img src={x.thumb} alt="" loading="lazy" /> : <span>{onPick && on(x) ? '✓' : '▶'}</span>}</button>
        <div className="mbody"><a onClick={() => onPick ? flip(x) : setOpen(x)}><b>{x.name}</b></a>
          <div className="small muted">{x.kind === 'src' ? `Исходники · ${x.src_folder}` : `№${x.object_id} ${x.object_title}`} · {x.by} · {new Date(x.created_at).toLocaleDateString('ru-RU')}{x.review === 'approved' ? ' · в Продакшн' : ''}</div>
          {(x.tags.length > 0 || (d.can_tag && !onPick)) && <div className="mtags">{x.tags.map(t => <span key={t}>{rname(t)}</span>)}
            {d.can_tag && !onPick && <a onClick={() => setTagsOf(x)}>{x.tags.length ? 'изменить' : '+ метка'}</a>}</div>}</div>
        {onPick ? <button className={'mini' + (on(x) ? '' : ' ghost')} aria-label="Выбрать" onClick={() => flip(x)}>{on(x) ? '✓' : '+'}</button>
          : <button className="ghost mini" aria-label="Скачать" onClick={() => download(x)}>⬇</button>}
      </div>)}
    {onPick && <button onClick={() => onPick(sel)}>Готово · выбрано {sel.length}</button>}
    {tagsOf && <Sheet title="Метки" onClose={() => setTagsOf(null)}>
      <p className="small muted">{tagsOf.name}</p>
      <div className="chips">{d.rubrics.map(r => <button key={r.id} className={tagsOf.tags.includes(r.id) ? 'on' : ''}
        onClick={() => setTagsOf({ ...tagsOf, tags: tagsOf.tags.includes(r.id) ? tagsOf.tags.filter(t => t !== r.id) : [...tagsOf.tags, r.id] })}>{r.title}</button>)}</div>
      <button onClick={() => api(`/mkt/files/${tagsOf.id}/tags`, { method: 'POST', body: { rubric_ids: tagsOf.tags } }).then(() => { setTagsOf(null); setTick(t => t + 1) })}>Сохранить</button>
    </Sheet>}
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
const IST = { new: ['черновик', ''], pending: ['у HEAD', 'warn'], approved: ['утверждено', 'ok'], rejected: ['вернул', 'hot'], work: ['в съёмке', ''], done: ['снято', 'ok'], dropped: ['отложено', ''] }
function Ideas({ can }) {
  const [d, setD] = useState(null)
  const [edit, setEdit] = useState(null)
  const load = () => api('/mkt/ideas').then(setD, e => setD({ items: [], err: e.message }))
  useEffect(() => { load() }, [])
  return <div className="card">
    <p className="small muted">Сценарии и задумки. Путь: черновик → «На утверждение» → HEAD → «В съёмку»: ставится дата и на Диске появляется папка исходников со сценарием.</p>
    {can && <button onClick={() => setEdit({})}>+ Идея</button>}
    {!d ? <p className="muted">Загрузка…</p> : d.err ? <p className="small why">{d.err}</p> : !d.items.length ? <p className="muted small">Идей пока нет.</p> :
      d.items.map(x => <div key={x.id} className="mktidea" onClick={() => (can || d.head) && setEdit(x)}>
        <b>{x.title}</b> <span className={'badge ' + IST[x.status][1]}>{IST[x.status][0]}</span>
        <div className="small muted">{d.kinds[x.kind]}{x.rubric ? ` · ${x.rubric}` : ''}{x.object_title ? ` · №${x.object_id} ${x.object_title}` : ''} · {x.author}</div>
        {x.status === 'rejected' && x.review_note && <p className="small why">HEAD: {x.review_note}</p>}
        {x.text && <p className="small mktclip">{x.text}</p>}</div>)}
    {edit && <IdeaEditor x={edit} d={d} can={can} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load() }} />}
  </div>
}

function IdeaEditor({ x, d, can, onClose, onSaved }) {
  const kinds = d?.kinds || {}
  const [b, setB] = useState({ title: x.title || '', text: x.text || '', kind: x.kind || 'reels', object_id: x.object_id || '', rubric_id: x.rubric_id || '' })
  const [objs, setObjs] = useState([])
  const [msg, setMsg] = useState('')
  const [note, setNote] = useState(null)      // HEAD возвращает: что поправить
  const [shoot, setShoot] = useState(null)    // «В съёмку»: дата, время, место
  useEffect(() => { api('/objects').then(setObjs, () => {}) }, [])
  const set = (k, v) => setB(s => ({ ...s, [k]: v }))
  const st = x.status || 'new'
  const body = () => ({ ...b, object_id: b.object_id ? +b.object_id : null, rubric_id: b.rubric_id ? +b.rubric_id : null })
  const fail = e => setMsg(e.message)
  const save = (then) => b.title.trim() ? api(x.id ? `/mkt/ideas/${x.id}` : '/mkt/ideas', { method: 'POST', body: body() }).then(r => then ? then(r.id) : onSaved(), fail) : setMsg('Назови идею.')
  const submit = () => !b.text.trim() ? setMsg('Напиши сценарий.') : !b.rubric_id ? setMsg('Выбери рубрику.') : save(id => api(`/mkt/ideas/${id}/submit`, { method: 'POST' }).then(onSaved, fail))
  const review = approve => api(`/mkt/ideas/${x.id}/review`, { method: 'POST', body: { approve, note } }).then(onSaved, fail)
  const toShoot = () => shoot.shoot_date ? api(`/mkt/ideas/${x.id}/shoot`, { method: 'POST', body: { shoot_date: shoot.shoot_date, at_time: shoot.at_time || null, place: shoot.place || null } })
    .then(r => r.warn ? setMsg(r.warn) || setShoot({ done: r }) : setShoot({ done: r }), fail) : setMsg('Поставь дату съёмки.')
  if (shoot?.done) return <Sheet title="Съёмка поставлена" onClose={onSaved}>
    <p>Папка исходников на Диске:</p><p className="mktcap">{shoot.done.folder}</p>
    <p className="small muted">Внутри лежит сценарий. Снятое грузи в «Медиа → Загрузить снятое» или прямо в эту папку.</p>
    {msg && <p className="small why">{msg}</p>}
    <button onClick={onSaved}>Готово</button></Sheet>
  return <Sheet title={x.id ? 'Идея' : 'Новая идея'} onClose={onClose}>
    {x.id && <p className="small muted">Статус: {IST[st][0]}{x.author ? ` · ${x.author}` : ''}</p>}
    {st === 'rejected' && x.review_note && <p className="small why">HEAD вернул: {x.review_note}</p>}
    <input placeholder="Например: говорящая голова — как мы рисуем" value={b.title} onChange={e => set('title', e.target.value)} />
    <div className="chips">{Object.entries(kinds).map(([k, t]) => <button key={k} className={b.kind === k ? 'on' : ''} onClick={() => set('kind', k)}>{t}</button>)}</div>
    <select aria-label="Рубрика" value={b.rubric_id} onChange={e => set('rubric_id', e.target.value)}><option value="">— рубрика —</option>
      {(d?.rubrics || []).map(r => <option key={r.id} value={r.id}>{r.title}</option>)}</select>
    <textarea rows={7} placeholder="Сценарий: кадры, текст, музыка, кто в кадре" value={b.text} onChange={e => set('text', e.target.value)} />
    <select value={b.object_id} onChange={e => set('object_id', e.target.value)}><option value="">Вне проектов</option>
      {objs.map(o => <option key={o.id} value={o.id}>№{o.id} {o.title}</option>)}</select>
    {(st === 'pending' || st === 'approved') && !d?.head && <p className="small muted">Если поменять сценарий, он снова уйдёт в черновики и на утверждение.</p>}
    {msg && <p className="small why">{msg}</p>}
    {d?.head && st === 'pending' ? (note === null ? <div className="seg"><button onClick={() => review(true)}>Утверждаю</button><button className="ghost" onClick={() => setNote('')}>Вернуть</button></div>
      : <><textarea rows={2} placeholder="Что поправить" value={note} onChange={e => setNote(e.target.value)} />
        <div className="seg"><button disabled={!note.trim()} onClick={() => review(false)}>Вернуть автору</button><button className="ghost" onClick={() => setNote(null)}>Отмена</button></div></>)
      : st === 'approved' && d?.can_shoot ? (shoot ? <>
        <label className="muted small">Дата съёмки</label><input type="date" value={shoot.shoot_date || ''} onChange={e => setShoot({ ...shoot, shoot_date: e.target.value })} />
        <input placeholder="Время, например 10:00" value={shoot.at_time || ''} onChange={e => setShoot({ ...shoot, at_time: e.target.value })} />
        <input placeholder="Место" value={shoot.place || ''} onChange={e => setShoot({ ...shoot, place: e.target.value })} />
        <button onClick={toShoot}>Поставить съёмку</button></> : <button onClick={() => setShoot({})}>В съёмку</button>)
      : null}
    {(can || d?.head) && ['new', 'rejected', 'dropped'].includes(st) && <button onClick={submit}>{d?.head ? 'Утвердить и сохранить' : 'На утверждение HEAD'}</button>}
    {(can || d?.head) && <button className="ghost" onClick={() => save()}>{['new', 'rejected', 'dropped'].includes(st) ? 'Сохранить черновик' : 'Сохранить'}</button>}
  </Sheet>
}

// «Съёмки»: график на месяц — что, когда, где, кто снимает; по проекту или вне проектов (студия, интервью).
function Shoots({ can }) {
  const [ym, setYm] = useState(ymNow())
  const [d, setD] = useState(null)
  const [edit, setEdit] = useState(null)
  const [hints, setHints] = useState(null)
  const [plan, setPlan] = useState(null)   // подсказка, по которой предлагаем съёмку
  const loadHints = () => api('/mkt/hints').then(setHints, () => setHints(null))
  useEffect(() => { loadHints() }, [])
  const load = () => api(`/mkt/shoots?ym=${ym}`).then(setD, e => setD({ items: [], team: [], err: e.message }))
  useEffect(() => { setD(null); load() }, [ym])
  const groups = d ? [...d.items.reduce((m, x) => m.set(x.shoot_date, [...(m.get(x.shoot_date) || []), x]), new Map())] : []
  return <>{hints && (hints.items.length > 0 || hints.ideas.length > 0) && <div className="card mkthints"><h3>Что снять на этой неделе</h3>
    <p className="small muted">Подсказки по проектам в работе. Съёмку на объекте подтверждает ГИП.</p>
    {hints.items.map(x => <div key={x.object_id} className="mkthint">
      <div><span className={'badge ' + (x.why === 'final' ? 'hot' : x.why === 'process' ? '' : 'warn')} style={{ marginLeft: 0 }}>{x.label}</span>
        <b>№{x.object_id} {x.title}</b>
        <div className="small muted">{[x.city, x.address, x.gip && `ГИП ${x.gip}`].filter(Boolean).join(' · ')}</div>
        <div className="small">{x.what}</div>
        {x.ask_client && <div className="small why">Клиента о публикации ещё не спросили. Уточни у МОП.</div>}</div>
      {can && <button className="mini" onClick={() => setPlan(x)}>Предложить</button>}</div>)}
    {hints.ideas.length > 0 && <><div className="small muted mkthsub">Идеи без съёмки</div>
      {hints.ideas.map(i => <div key={i.id} className="mkthint"><div><b>{i.title}</b></div>
        {can && <button className="mini ghost" onClick={() => setEdit({ title: i.title, idea_id: i.id })}>В график</button>}</div>)}</>}
  </div>}
  <div className="card">
    <div className="mktmonth"><button className="ghost mini" aria-label="Прошлый месяц" onClick={() => setYm(shift(ym, -1))}>‹</button>
      <b>{monthName(ym)}</b><button className="ghost mini" aria-label="Следующий месяц" onClick={() => setYm(shift(ym, 1))}>›</button></div>
    {can && <button onClick={() => setEdit({})}>+ Съёмка</button>}
    {!d ? <p className="muted">Загрузка…</p> : d.err ? <p className="small why">{d.err}</p> : !d.items.length ? <p className="muted small">Съёмок в этом месяце нет.</p> :
      groups.map(([dt, list]) => <div key={dt} className="mktday"><h3>{day(dt)}</h3>
        {list.map(x => <div key={x.id} className="mktidea" onClick={() => can && setEdit(x)}>
          <b>{x.at_time ? `${x.at_time} · ` : ''}{x.title}</b>{x.status === 'done' && <span className="badge ok">снято</span>}{x.status === 'proposed' && <span className="badge warn">{x.alt_date ? 'ГИП предлагает ' + x.alt_date.slice(8, 10) + '.' + x.alt_date.slice(5, 7) : 'ждёт ГИП'}</span>}
          <div className="small muted">{x.object_title ? `№${x.object_id} ${x.object_title}` : 'вне проектов'}{x.place ? ` · ${x.place}` : ''}</div>
          {x.crew_names && <div className="small">🎥 {x.crew_names.join(', ')}</div>}
          {x.idea_title && <div className="small muted">Идея: {x.idea_title}</div>}</div>)}</div>)}
    {edit && <ShootEditor x={edit} team={d?.team || []} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load(); loadHints() }} />}
    {plan && <HintSheet x={plan} onClose={() => setPlan(null)} onSaved={() => { setPlan(null); load(); loadHints() }} />}
  </div></>
}

// Съёмка по подсказке: дата и время → предложение ГИП объекта (он подтверждает или называет другую дату в карточке проекта).
function HintSheet({ x, onClose, onSaved }) {
  const [b, setB] = useState({ shoot_date: '', at_time: '', note: '' })
  const [msg, setMsg] = useState('')
  const save = () => !b.shoot_date ? setMsg('Поставь дату.') :
    api(`/objects/${x.object_id}/shoots`, { method: 'POST', body: { title: `${x.label}: ${x.title}`.slice(0, 200), shoot_date: b.shoot_date, at_time: b.at_time || null, note: b.note || null } })
      .then(onSaved, e => setMsg(e.message))
  return <Sheet title={`Съёмка · №${x.object_id} ${x.title}`} onClose={onClose}>
    <p className="small muted">{x.what}</p>
    <label className="muted small">Когда</label>
    <input type="date" value={b.shoot_date} onChange={e => setB({ ...b, shoot_date: e.target.value })} />
    <input placeholder="Время, например 11:00" value={b.at_time} onChange={e => setB({ ...b, at_time: e.target.value })} />
    <textarea rows={2} placeholder="Что нужно от бригады (необязательно)" value={b.note} onChange={e => setB({ ...b, note: e.target.value })} />
    {msg && <p className="small why">{msg}</p>}
    <button onClick={save}>Предложить ГИП</button>
    <p className="small muted">ГИП объекта получит сообщение и подтвердит или предложит другую дату.</p>
  </Sheet>
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
