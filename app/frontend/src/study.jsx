import React, { useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api.js'
import './study.css'

// «Учёба» МОП (HEAD 28.11: «учебник — шляпа, сделать очень стильно»; «тестов очень много — пойдут в геймификацию»).
// Учебник — раздел приложения в тёмном стиле книги бренда: на компьютере три колонки (оглавление · глава · тест и прогресс),
// на телефоне одна колонка и лента глав сверху. Тесты — раундами по 10 вопросов, проверяет сервер (study.py), разбор сразу,
// ошибка возвращается на следующий день. Уровни вопросов — ступени «Моего пути»: МОП → VIP МОП → Руководитель продаж.

const PARTS = [['Продукт', ['01', '02', '03', '04']], ['Цены', ['05']], ['Клиент и дизайн', ['06', '07', '08']],
  ['Диалог', ['09', '10']], ['CRM и допуск', ['11', '12', '13']]]
const PART_OF = Object.fromEntries(PARTS.flatMap(([t, l], i) => l.map(n => [n, [i + 1, t]])))
const LINE = { '01': 'снимаем у клиента хаос', '02': 'знай, что продаёшь', '03': 'из чего рождается стена', '04': 'стена решает всё',
  '05': 'цифры без страха', '06': 'пойми, кто перед тобой', '07': 'от брифа к эскизу', '08': 'покажи — и поверят',
  '09': 'слова, которые продают', '10': 'ответ на каждое «но»', '11': 'нет в CRM — значит, не было', '12': 'готов к допуску',
  '13': 'говорим на одном языке' }
const SHORT = { 'Руководитель продаж': 'Рук. продаж' }
const KONST = /\s*\(?по константам от ([\d.]+)\)?/
const KIND = { fact: 'факт', case: 'ситуация', calc: 'расчёт', error: 'найди ошибку' }
const strip = s => String(s || '').replace(/<[^>]+>/g, '')
const plural = (n, a, b, c) => { const m = n % 10, h = n % 100; return m === 1 && h !== 11 ? a : m >= 2 && m <= 4 && (h < 10 || h >= 20) ? b : c }
const fmt = n => Number(n || 0).toLocaleString('ru-RU')
const KEY = 'artgame.study'
const mem = () => { try { return JSON.parse(localStorage.getItem(KEY) || '{}') } catch { return {} } }
const remember = o => { try { localStorage.setItem(KEY, JSON.stringify({ ...mem(), ...o })) } catch { /* без памяти */ } }

function blockText(b) {
  if (b.t === 'table') return [...b.head, ...b.rows.flat()].join(' ')
  if (b.t === 'callout') return [b.title, ...(b.body || [])].join(' ')
  if (b.t === 'walls') return b.items.map(i => i.n + ' ' + i.d).join(' ')
  return b.x || ''
}
const minutes = m => Math.max(2, Math.round(m.blocks.map(blockText).join(' ').length / 1000))

// ссылки внутри текста учебника: #s08 — глава, #p5-2 / #m05-3 — место в главе
function target(href) {
  let m = /^#s(\d\d)$/.exec(href); if (m) return { ch: m[1] }
  m = /^#p(\d+)-\d+$/.exec(href); if (m) return { ch: m[1].padStart(2, '0'), id: href.slice(1) }
  m = /^#m(\d\d)(-.+)?$/.exec(href); if (m) return { ch: m[1], id: m[2] ? href.slice(1) : '' }
  return null
}

export function Study({ place, isHead }) {
  const [book, setBook] = useState(null)
  const [err, setErr] = useState('')
  const [prog, setProg] = useState(null)
  const [tab, setTab] = useState(() => mem().tab || 'book')
  const [ch, setCh] = useState(() => mem().ch || '')
  const [jump, setJump] = useState('')
  const [q, setQ] = useState('')
  const top = useRef(null)
  const load = () => api('/study/mop/me').then(setProg, () => {})
  useEffect(() => { api('/study/mop').then(setBook, e => setErr(e.message)); load() }, [])
  useEffect(() => { remember({ tab, ch }) }, [tab, ch])
  const open = (n, id = '') => { setTab('book'); setCh(n); setJump(id); setQ(''); if (!id) top.current?.scrollIntoView?.({ block: 'start' }) }
  if (err) return <div className="stu"><div className="stu-empty">Учебник не открылся: {err}</div></div>
  if (!book) return <div className="stu"><div className="stu-empty">Загрузка учебника…</div></div>
  const mods = book.mods
  const img = s => (book.img_base && s ? book.img_base + s : '')
  const read = new Set(prog?.read || [])
  const lv = book.levels
  const tabs = [['book', 'Учебник'], ['test', 'Тесты'], ['tasks', 'Задачи'], ['dict', 'Словарь'], ...(isHead ? [['team', 'Команда']] : [])]
  const passed = prog ? Object.values(prog.chapters).filter(c => c.passed).length : 0
  return <div className="stu" ref={top}>
    <div className="stu-bar">
      <div className="stu-tabs">{tabs.map(([k, t]) => <button key={k} className={tab === k ? 'on' : ''} onClick={() => { setTab(k); setQ('') }}>{t}
        {k === 'test' && prog?.due > 0 && <i className="stu-dot">{prog.due}</i>}</button>)}</div>
      <div className="stu-me">
        {prog && <span className="stu-stat">{read.size} из {mods.length} глав · тесты {passed} из {mods.length}</span>}
        {prog && <span className="stu-rank"><Ring v={passed / mods.length} />{lv[prog.rank - 1]}{prog.rank < lv.length ? ' → ' + lv[prog.rank] : ''}<b>{fmt(prog.points)}</b></span>}
        <input className="stu-search" placeholder="Найти в учебнике…" value={q} onChange={e => setQ(e.target.value)} />
      </div>
    </div>
    {q.trim().length > 1 ? <Search mods={mods} q={q.trim()} open={open} /> :
      tab === 'test' ? <Tests mods={mods} book={book} prog={prog} reload={load} open={open} /> :
      tab === 'tasks' ? <Tasks tasks={book.tasks || []} open={open} /> :
      tab === 'dict' ? <Dict mod={mods.find(m => m.n === '13')} /> :
      tab === 'team' ? <Team total={Object.values(book.qcount).reduce((a, b) => a + b, 0)} chapters={mods.length} /> :
      ch && mods.some(m => m.n === ch) ? <Chapter key={ch} m={mods.find(m => m.n === ch)} mods={mods} book={book} img={img} prog={prog} read={read}
        jump={jump} open={open} toTest={() => { setTab('test'); setCh(ch); remember({ quiz: ch }) }} onRead={n => api('/study/mop/read', { method: 'POST', body: { ch: n } }).then(load, () => {})} /> :
      <Cover book={book} img={img} prog={prog} read={read} open={open} />}
  </div>
}

function Ring({ v = 0, size = 24 }) {
  return <s className="stu-ring" style={{ width: size, height: size, background: `conic-gradient(var(--accent) 0 ${Math.round(v * 100)}%, #34303a 0)` }} />
}

// ---------- обложка учебника: все главы по частям ----------
function Cover({ book, img, prog, read, open }) {
  const mods = book.mods
  const total = Object.values(book.qcount).reduce((a, b) => a + b, 0)
  return <>
    <section className="stu-hero cover">
      {img('img/cover_team.jpg') && <img src={img('img/cover_team.jpg')} alt="" />}
      <div className="in">
        <div className="crumb">ARTGAME · ОТДЕЛ ПРОДАЖ · 2026</div>
        <h1>Учебник МОП</h1>
        <p className="script">продаём результат, а не краску</p>
        <p className="about">{strip(book.about)}</p>
        <div className="meta"><span className="chip red">{mods.length} глав</span><span className="chip">{total} вопросов в тестах</span>
          <span className="chip">цифры по константам</span></div>
        <div className="btns"><button onClick={() => open(mods.find(m => !read.has(m.n))?.n || '01')}>{read.size ? 'Продолжить →' : 'Начать с главы 1 →'}</button></div>
      </div>
    </section>
    <div className="stu-page">
      {book.rule && <div className="stu-rule"><div className="lb">Главное правило</div><p dangerouslySetInnerHTML={{ __html: book.rule }} /></div>}
      {PARTS.map(([t, list], i) => <section key={t} className="stu-part">
        <h2 className="stu-h"><em>Часть {i + 1}</em>{t}</h2>
        <div className="stu-cards">{list.map(n => { const m = mods.find(x => x.n === n); if (!m) return null
          const c = prog?.chapters?.[n]
          return <button key={n} className="stu-card" onClick={() => open(n)}>
            <div className="im">{img(m.img) && <img src={img(m.img)} alt="" loading="lazy" />}<span className="n">{n}</span>
              {c?.passed ? <span className="st ok">Тест сдан</span> : read.has(n) ? <span className="st">Прочитано</span> : null}</div>
            <div className="tx"><b>{m.title}</b><span>{minutes(m)} мин · {book.qcount[n] || 0} вопросов</span>
              {c && c.total > 0 && <i className="bar"><i style={{ width: Math.round(c.ok / c.total * 100) + '%' }} /></i>}</div>
          </button> })}</div>
      </section>)}
    </div>
  </>
}

// ---------- глава ----------
function Chapter({ m, mods, book, img, prog, read, jump, open, toTest, onRead }) {
  const art = useRef(null)
  const idx = mods.findIndex(x => x.n === m.n)
  const prev = mods[idx - 1], next = mods[idx + 1]
  const [pn, pt] = PART_OF[m.n] || [1, '']
  const heads = m.blocks.filter(b => b.t === 'h2')
  const c = prog?.chapters?.[m.n]
  const nq = book.qcount[m.n] || 0
  useEffect(() => {
    if (!jump) { window.scrollTo?.(0, 0); return }
    const t = setTimeout(() => document.getElementById('stu-' + jump)?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 60)
    return () => clearTimeout(t)
  }, [jump, m.n])
  const onClick = e => {
    const a = e.target.closest?.('a[href^="#"]')
    if (!a) return
    e.preventDefault()
    const t = target(a.getAttribute('href'))
    if (t) open(t.ch, t.id)
  }
  const go = id => document.getElementById('stu-' + id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  return <>
    <div className="stu-chips">{mods.map(x => <button key={x.n} className={x.n === m.n ? 'on' : read.has(x.n) ? 'done' : ''} onClick={() => open(x.n)}>{x.n} {x.title.split(/[,:]/)[0]}</button>)}</div>
    <section className="stu-hero">
      {img(m.img) && <img src={img(m.img)} alt="" />}
      <div className="in">
        <div className="crumb"><a onClick={() => open('')}>Учебник</a> · ЧАСТЬ {pn} · {pt.toUpperCase()} · <b>ГЛАВА {Number(m.n)} ИЗ {mods.length}</b></div>
        <h1>{m.title}</h1>
        {LINE[m.n] && <p className="script">{LINE[m.n]}</p>}
        <div className="meta"><span className="chip red">~{minutes(m)} мин</span>{heads.length > 1 && <span className="chip">{heads.length} {plural(heads.length, 'тема', 'темы', 'тем')}</span>}
          {nq > 0 && <span className="chip">тест: {nq} вопросов</span>}{read.has(m.n) && <span className="chip ok">✓ прочитано</span>}</div>
      </div>
      <div className="num">{m.n}</div>
    </section>
    <div className="stu-cols">
      <div className="stu-toc">{PARTS.map(([t, list], i) => <React.Fragment key={t}>
        <div className="part">ЧАСТЬ {i + 1} · {t.toUpperCase()}</div>
        {list.map(n => { const x = mods.find(y => y.n === n); if (!x) return null
          return <a key={n} className={(n === m.n ? 'on ' : '') + (read.has(n) ? 'done' : '')} onClick={() => open(n)}>
            <em>{n}</em><span>{x.title}</span>{prog?.chapters?.[n]?.passed ? <i>★</i> : read.has(n) ? <i>✓</i> : null}</a> })}
      </React.Fragment>)}</div>
      <article className="stu-read" ref={art} onClick={onClick}>
        <Blocks blocks={m.blocks} img={img} hero={m.ch?.[0]} />
        <div className="stu-end">
          {!read.has(m.n) ? <button onClick={() => onRead(m.n)}>✓ Глава прочитана</button> : <span className="ok">✓ Глава прочитана</span>}
          {nq > 0 && <button className="ghost" onClick={toTest}>Пройти тест главы · {nq} вопросов</button>}
        </div>
        <div className="stu-next">
          {prev ? <a onClick={() => open(prev.n)}><small>← Назад</small>{prev.n} · {prev.title}</a> : <a onClick={() => open('')}><small>← Назад</small>Обложка учебника</a>}
          {next && <a className="go" onClick={() => open(next.n)}><small>Дальше →</small>{next.n} · {next.title}</a>}
        </div>
      </article>
      <aside className="stu-rail">
        {nq > 0 && <div className="test">
          <h4>ТЕСТ ГЛАВЫ {m.n}</h4>
          <div className="big">{nq} вопросов</div>
          <p>Освой {Math.round((book.pass || .8) * 100)} % — глава засчитана. Ошибки вернутся завтра.</p>
          <Ladder c={c} levels={book.levels} />
          <button onClick={toTest}>{c?.ok ? 'Продолжить тест →' : 'Пройти тест →'}</button>
        </div>}
        {heads.length > 1 && <div className="ins"><h4>В ЭТОЙ ГЛАВЕ</h4>
          {heads.map((h, i) => <a key={i} onClick={() => go(h.id)}>{h.no ? <em>{h.no}</em> : null}{strip(h.x)}</a>)}</div>}
        {prog && <div className="ins"><h4>ПРОГРЕСС</h4>
          <i className="bar"><i style={{ width: Math.round(read.size / mods.length * 100) + '%' }} /></i>
          <span className="small">Прочитано {read.size} из {mods.length} · очки знаний {fmt(prog.points)}</span></div>}
      </aside>
    </div>
  </>
}

function Ladder({ c, levels }) {
  return <div className="stu-ladder">{levels.map((t, i) => { const l = c?.lv?.[String(i + 1)]
    const v = l && l[1] ? l[0] / l[1] : 0
    return <span key={t} className={v >= .8 ? 'done' : v > 0 ? 'go' : ''} title={l ? `${l[0]} из ${l[1]}` : ''}>
      <i style={{ width: Math.round(v * 100) + '%' }} /><b>{SHORT[t] || t}</b>{l ? <small>{l[0]}/{l[1]}</small> : <small>—</small>}</span> })}</div>
}

// ---------- блоки главы ----------
function Blocks({ blocks, img, hero }) {
  const out = []
  let firstP = true, firstCall = true
  for (let i = 0; i < blocks.length; i++) {
    const b = blocks[i]
    if (b.t === 'li') {
      const run = [b]
      while (blocks[i + 1]?.t === 'li') run.push(blocks[++i])
      const short = run.length >= 3 && run.every(x => strip(x.x).length < 110 && !/^Пример/.test(strip(x.x)))
      out.push(short ? <div key={i} className="stu-grid">{run.map((x, j) => <div key={j}><b>{String(j + 1).padStart(2, '0')}</b>
        <span dangerouslySetInnerHTML={{ __html: x.x.replace(/;$|\.$/, '') }} /></div>)}</div> :
        <ul key={i} className="stu-ul">{run.map((x, j) => /^Пример/.test(strip(x.x)) ? <li key={j} className="ex"><Example x={x.x} /></li> :
          <li key={j} dangerouslySetInnerHTML={{ __html: x.x }} />)}</ul>)
      continue
    }
    if (b.t === 'p') {
      if (/^Пример/.test(strip(b.x))) { out.push(<div key={i} className="stu-ex"><Example x={b.x} /></div>); continue }
      out.push(<p key={i} className={firstP ? 'stu-lead' : ''} dangerouslySetInnerHTML={{ __html: b.x }} />); firstP = false; continue
    }
    if (b.t === 'h2') { out.push(<h2 key={i} id={'stu-' + b.id} className="stu-h">{b.no ? <em>{b.no}</em> : null}<span dangerouslySetInnerHTML={{ __html: b.x }} /></h2>); continue }
    if (b.t === 'h3') { out.push(<h3 key={i} className="stu-h3" dangerouslySetInnerHTML={{ __html: b.x }} />); continue }
    if (b.t === 'h4') { out.push(<h4 key={i} className="stu-h4" dangerouslySetInnerHTML={{ __html: b.x }} />); continue }
    if (b.t === 'note') {
      out.push(/^Пример/.test(strip(b.x)) ? <div key={i} className="stu-ex"><Example x={b.x} /></div> :
        <div key={i} className="stu-note" dangerouslySetInnerHTML={{ __html: b.x }} />); continue
    }
    if (b.t === 'callout') {
      const big = firstCall && hero
      firstCall = false
      out.push(<div key={i} className={'stu-call' + (b.red ? ' red' : '') + (big ? ' hero' : '')}>
        {big && img(hero) && <img src={img(hero)} alt="" />}
        {b.title && <div className="lb">{strip(b.title)}</div>}
        {(b.body || []).map((x, j) => <p key={j} dangerouslySetInnerHTML={{ __html: x.replace(/^•\s*/, '') }} />)}
      </div>); continue
    }
    if (b.t === 'table') { out.push(<Table key={i} b={b} />); continue }
    if (b.t === 'walls') {
      out.push(<div key={i} className="stu-walls">{b.items.map((w, j) => <figure key={j}>{img(w.img) && <img src={img(w.img)} alt="" loading="lazy" />}
        <figcaption><b>{w.n}</b>{w.d}</figcaption></figure>)}</div>); continue
    }
  }
  return out
}

function Example({ x }) {
  const m = /^(Пример[^:]*):\s*([\s\S]*)$/.exec(strip(x))
  const head = m ? m[1] : 'Пример', body = m ? m[2] : strip(x)
  const k = /по константам от [\d.]+/.exec(head)
  return <><div className="t"><span>{head.replace(/\s*по константам от [\d.]+/, '') || 'Пример'}</span>{k && <i>{k[0]}</i>}</div><p>{body}</p></>
}

function Table({ b }) {
  // путь по шагам (первая колонка — номер): линия шагов вместо таблицы
  if (b.head[0] === '№' && b.rows.length <= 12 && b.head.length >= 3) {
    return <div className="stu-steps">{b.rows.map((r, i) => <div key={i} className={/МОП/.test(strip(r[2])) ? 'me' : ''} data-n={strip(r[0])}>
      <b dangerouslySetInnerHTML={{ __html: r[1] }} />{r[2] && <span className="who">{strip(r[2])}</span>}
      {r.slice(3).map((c, j) => <span key={j} className="res" dangerouslySetInnerHTML={{ __html: c }} />)}</div>)}</div>
  }
  const num = b.rows.every(r => r.slice(1).every(c => strip(c).length <= 14))
  return <div className={'stu-tw' + (num ? ' num' : '')}><table><thead><tr>{b.head.map((h, i) => <th key={i} dangerouslySetInnerHTML={{ __html: h }} />)}</tr></thead>
    <tbody>{b.rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} className={strip(c).length <= 14 ? 'nw' : ''} data-h={strip(b.head[j])} dangerouslySetInnerHTML={{ __html: c }} />)}</tr>)}</tbody></table></div>
}

// ---------- поиск ----------
function Search({ mods, q, open }) {
  const ql = q.toLowerCase()
  const hits = []
  for (const m of mods) {
    let sec = ''
    for (const b of m.blocks) {
      if (b.t === 'h2') sec = b.id
      const t = strip(blockText(b))
      const at = t.toLowerCase().indexOf(ql)
      if (at >= 0) hits.push({ m, sec, t: t.slice(Math.max(0, at - 60), at + q.length + 90), at: at > 60 })
      if (hits.length > 60) break
    }
  }
  return <div className="stu-page narrow"><h2 className="stu-h">Найдено: {hits.length}</h2>
    {!hits.length && <p className="muted">Ничего не нашлось. Попробуй другое слово.</p>}
    {hits.map((h, i) => <button key={i} className="stu-hit" onClick={() => open(h.m.n, h.sec)}><em>{h.m.n} · {h.m.title}</em>
      <span>{h.at ? '…' : ''}{h.t}…</span></button>)}</div>
}

// ---------- задачи ----------
function Tasks({ tasks, open }) {
  const [shown, setShown] = useState({})
  return <div className="stu-page narrow">
    <h2 className="stu-h"><em>Практика</em>Задачи на расчёт</h2>
    <p className="muted">Посчитай в голове или на бумаге, потом открой ответ. Итог клиенту всегда — из калькулятора, разбор — в <a onClick={() => open('05')}>главе 5</a>.</p>
    <div className="stu-tasks">{tasks.map((t, i) => <div key={i} className={'stu-task' + (shown[i] ? ' open' : '')}>
      <b>{String(i + 1).padStart(2, '0')}</b><p dangerouslySetInnerHTML={{ __html: t.q }} />
      {shown[i] ? <div className="a" dangerouslySetInnerHTML={{ __html: t.a }} /> : <button className="ghost" onClick={() => setShown({ ...shown, [i]: 1 })}>Показать ответ</button>}
    </div>)}</div>
  </div>
}

// ---------- словарь ----------
function Dict({ mod }) {
  const [q, setQ] = useState('')
  const t = mod?.blocks.find(b => b.t === 'table')
  if (!t) return <div className="stu-page narrow muted">Словаря пока нет.</div>
  const rows = t.rows.filter(r => !q || strip(r.join(' ')).toLowerCase().includes(q.toLowerCase()))
  return <div className="stu-page narrow">
    <h2 className="stu-h"><em>Глава 13</em>Словарь терминов</h2>
    <input className="stu-find" placeholder="Найти термин…" value={q} onChange={e => setQ(e.target.value)} />
    <div className="stu-dict">{rows.map((r, i) => <div key={i}><b dangerouslySetInnerHTML={{ __html: r[0] }} /><p dangerouslySetInnerHTML={{ __html: r.slice(1).join(' · ') }} /></div>)}</div>
  </div>
}

// ---------- тесты ----------
function Tests({ mods, book, prog, reload, open }) {
  const [run, setRun] = useState(null)   // { ch, mode, q: [...] }
  const [busy, setBusy] = useState(false)
  const start = (ch, mode = '') => {
    setBusy(true)
    api(`/study/mop/round?ch=${ch || ''}&mode=${mode}`).then(r => { setRun({ ch, mode, q: r.q }); window.scrollTo?.(0, 0) }, () => {}).finally(() => setBusy(false))
  }
  useEffect(() => { const c = mem().quiz; if (c && book.qcount[c]) { remember({ quiz: '' }); start(c) } }, [])
  if (run) return <Round run={run} mods={mods} levels={book.levels} done={() => { setRun(null); reload() }} again={() => start(run.ch, run.mode)} open={open} />
  const chs = prog?.chapters || {}
  const ok = Object.values(chs).reduce((a, c) => a + c.ok, 0), all = Object.values(book.qcount).reduce((a, b) => a + b, 0)
  return <div className="stu-page">
    <section className="stu-qhero">
      <div><div className="crumb">ТЕСТЫ ПО УЧЕБНИКУ</div><h1>Проверь себя</h1>
        <p>Раунд — {10} вопросов. Сначала новые и вчерашние ошибки, потом повтор. Каждый вопрос с разбором и ссылкой на главу.</p>
        <div className="meta"><span className="chip red">освоено {ok} из {all}</span><span className="chip">очки знаний {fmt(prog?.points)}</span>
          <span className="chip">ответов всего {fmt(prog?.answers)}</span></div></div>
      <div className="acts">
        {prog?.due > 0 && <button disabled={busy} onClick={() => start('', 'due')}>Повторить ошибки · {prog.due}</button>}
        <button className={prog?.due > 0 ? 'ghost' : ''} disabled={busy} onClick={() => start('')}>Раунд по всему учебнику →</button>
      </div>
    </section>
    <div className="stu-lvls">{book.levels.map((t, i) => <div key={t} className={prog?.rank === i + 1 ? 'me' : ''}><em>Уровень {i + 1}</em><b>{t}</b>
      <span>{['Факты и правила: цены, этапы, что можно и нельзя', 'Ситуации с клиентом и расчёты', 'Сложные случаи, поиск ошибок, как учить других'][i]}</span></div>)}</div>
    <div className="stu-qgrid">{mods.map(m => { const n = book.qcount[m.n] || 0, c = chs[m.n]
      return <div key={m.n} className={'stu-qch' + (!n ? ' soon' : '') + (c?.passed ? ' passed' : '')}>
        <div className="h"><span className="n">{m.n}</span><b>{m.title}</b>{c?.passed && <i>★ сдан</i>}</div>
        {n ? <>
          <Ladder c={c} levels={book.levels} />
          <div className="f"><span>{c ? `${c.ok} из ${c.total} освоено` : `${n} вопросов`}{c?.wrong ? ` · ошибок ${c.wrong}` : ''}</span>
            <button disabled={busy} onClick={() => start(m.n)}>{c?.ok ? 'Ещё раунд' : 'Начать'}</button></div>
        </> : <div className="f"><span>Вопросы к главе готовятся</span><a onClick={() => open(m.n)}>Читать главу</a></div>}
      </div> })}</div>
  </div>
}

function Round({ run, mods, levels, done, again, open }) {
  const [i, setI] = useState(0)
  const [res, setRes] = useState({})   // id → {pick, ok, right, why, ref, points}
  const [err, setErr] = useState('')
  const [streak, setStreak] = useState(0)
  const q = run.q[i]
  if (!run.q.length) return <div className="stu-qwrap"><div className="stu-qcard"><h3>Здесь пока нечего повторять</h3>
    <p className="muted">Ошибок прошлых дней нет. Возьми раунд по главе.</p><button onClick={done}>К тестам</button></div></div>
  if (!q) {
    const r = Object.values(res), ok = r.filter(x => x.ok).length, pts = r.reduce((a, x) => a + (x.points || 0), 0)
    return <div className="stu-qwrap"><div className="stu-qcard sum">
      <div className="crumb">РАУНД ЗАВЕРШЁН</div>
      <div className="score"><b>{ok}</b>/{r.length}</div>
      <p>{ok === r.length ? 'Чисто! Ни одной ошибки.' : ok >= r.length * .8 ? 'Сильно. Ошибки вернутся завтра на повтор.' : 'Есть что подтянуть: перечитай главы по ссылкам в разборе.'}</p>
      <div className="meta"><span className="chip red">+{pts} очков знаний</span></div>
      <div className="stu-sumlist">{run.q.map(x => { const a = res[x.id]; return <div key={x.id} className={a?.ok ? 'ok' : 'no'}>
        <i>{a?.ok ? '✓' : '✗'}</i><span>{x.q}</span>{!a?.ok && a?.ref && <a onClick={() => { const t = target('#' + a.ref); t && open(t.ch, t.id) }}>к главе</a>}</div> })}</div>
      <div className="row2"><button onClick={again}>Ещё раунд →</button><button className="ghost" onClick={done}>К списку тестов</button></div>
    </div></div>
  }
  const a = res[q.id]
  const m = mods.find(x => x.n === q.ch)
  const pick = k => {
    if (a) return
    setErr('')
    api('/study/mop/answer', { method: 'POST', body: { qid: q.id, k } }).then(r => {
      setRes({ ...res, [q.id]: { ...r, pick: k } }); setStreak(r.ok ? streak + 1 : 0)
    }, e => setErr(e.status === 403 ? 'Режим просмотра: ответы не проверяются и не сохраняются.' : e.message))
  }
  return <div className="stu-qwrap">
    <div className="stu-qtop"><b>{i + 1}/{run.q.length}</b><i className="bar"><i style={{ width: Math.round((i + (a ? 1 : 0)) / run.q.length * 100) + '%' }} /></i>
      {streak >= 2 && <span className="combo">🔥 ×{streak} подряд</span>}<button className="ghost mini" onClick={done}>Выйти</button></div>
    <div className="stu-qcard">
      <div className="lvl"><span className="chip">Глава {q.ch}{m ? ' · ' + m.title.split(/[,:]/)[0] : ''}</span><span className="chip red">{levels[q.lvl - 1]}</span>
        <span className="chip">{KIND[q.kind] || q.kind}</span>{q.seen === 'wrong' && <span className="chip warn">повтор ошибки</span>}
        {KONST.test(q.q) && <span className="chip gold">по константам от {KONST.exec(q.q)[1]}</span>}</div>
      <h3>{q.q.replace(KONST, '')}</h3>
      {q.opts.map((o, j) => <button key={o.k} className={'stu-opt' + (a ? (o.k === a.right ? ' ok' : o.k === a.pick ? ' no' : ' dim') : '')} onClick={() => pick(o.k)}>
        <kbd>{'ABCD'[j]}</kbd><span>{o.t}</span></button>)}
      {err && <p className="stu-err">{err}</p>}
      {a && <div className={'stu-why' + (a.ok ? '' : ' no')}><b>{a.ok ? 'Верно.' : 'Не так.'}</b> {a.why}
        {a.ref && <a onClick={() => { const t = target('#' + a.ref); t && open(t.ch, t.id) }}> Открыть в главе →</a>}</div>}
    </div>
    <div className="stu-qbot"><span>{a ? (a.ok ? `+${a.points} очков` : 'Вопрос вернётся завтра') : 'Выбери вариант'}</span>
      <button disabled={!a} onClick={() => setI(i + 1)}>{i + 1 < run.q.length ? 'Дальше →' : 'Итог раунда'}</button></div>
  </div>
}

// ---------- HEAD: кто учится ----------
function Team({ total, chapters }) {
  const [d, setD] = useState(null)
  useEffect(() => { api('/study/mop/team').then(setD, () => setD({ people: [] })) }, [])
  if (!d) return <div className="stu-page narrow muted">Загрузка…</div>
  return <div className="stu-page narrow"><h2 className="stu-h"><em>HEAD</em>Кто учится</h2>
    {!d.people.length && <p className="muted">МОП пока нет.</p>}
    <div className="stu-team">{d.people.map(p => <div key={p.id}><b>{p.name}</b>
      <span>Прочитано {p.read} из {chapters}</span><span>Освоено {p.ok} из {d.total} вопросов</span>
      <i className="bar"><i style={{ width: Math.round(p.ok / Math.max(1, d.total) * 100) + '%' }} /></i>
      <small>{p.last ? 'Последний тест ' + new Date(p.last).toLocaleDateString('ru-RU') : 'Тесты ещё не проходил'}</small></div>)}</div>
  </div>
}
