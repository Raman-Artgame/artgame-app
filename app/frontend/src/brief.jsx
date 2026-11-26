import React, { useEffect, useState } from 'react'
import { shrink } from './work.jsx'
import './brief.css'

// Бриф клиента по ссылке (HEAD 26.11: «приятной и удобной ссылкой, чтобы клиенту нужно было просто потыкать»).
// Открывается без входа: /?brief=ТОКЕН. Шесть коротких шагов, RU/ҚАЗ, всё необязательно. Ответы уходят в задачу дизайнера.
// Значения вариантов хранятся по-русски (дизайнер читает их в задаче), казахский — только подписи.
// Вопросы — из документа ARTGAME «Бриф на разработку дизайна»; про цены и оплату здесь ничего нет.
const o = (v, kk) => ({ v, kk })
const STEPS = [
  { q: ['Что за объект?', 'Нысан қандай?'], key: 'place', one: true,
    opts: [o('Квартира или дом', 'Пәтер немесе үй'), o('Кафе, ресторан', 'Кафе, мейрамхана'), o('Офис', 'Кеңсе'), o('Школа, детский сад', 'Мектеп, балабақша'),
      o('Магазин, ТЦ', 'Дүкен, сауда орталығы'), o('Фасад здания', 'Ғимарат қасбеті'), o('Другое', 'Басқа')] },
  { q: ['Где стена?', 'Қабырға қайда?'], key: 'where', one: true, opts: [o('Внутри помещения', 'Ғимарат ішінде'), o('На улице', 'Сыртта')],
    text: [['size', ['Примерный размер стены', 'Қабырғаның шамамен өлшемі'], ['например, 6 × 3 м — можно не точно', 'мысалы, 6 × 3 м — дәл болмаса да болады']]] },
  { q: ['Для кого рисуем?', 'Кімге арналған?'], hint: ['Можно выбрать несколько', 'Бірнешеуін таңдауға болады'], key: 'who',
    opts: [o('Дети', 'Балалар'), o('Взрослые', 'Ересектер'), o('Сотрудники', 'Қызметкерлер'), o('Гости, клиенты', 'Қонақтар, клиенттер')] },
  { q: ['Какой стиль вам ближе?', 'Қандай стиль ұнайды?'], key: 'style',
    opts: [o('Графика', 'Графика'), o('Реализм', 'Реализм'), o('Минимализм', 'Минимализм'), o('Абстракция', 'Абстракция'), o('Граффити', 'Граффити'),
      o('Каллиграфия', 'Каллиграфия'), o('Не знаю, посоветуйте', 'Білмеймін, кеңес беріңіз')],
    more: { q: ['Какое настроение?', 'Қандай көңіл күй?'], key: 'mood',
      opts: [o('Энергия', 'Қуат'), o('Уют', 'Жайлылық'), o('Премиум', 'Премиум'), o('Детское', 'Балаларға'), o('Спокойное', 'Тыныш')] } },
  { q: ['Цвета и идея', 'Түстер мен идея'], key: 'colors',
    opts: [o('Тёплые', 'Жылы'), o('Холодные', 'Салқын'), o('Яркие', 'Ашық'), o('Спокойные', 'Жұмсақ'), o('Наши фирменные', 'Фирмалық түстеріміз')],
    text: [['idea', ['Что хотите видеть на стене?', 'Қабырғада не көргіңіз келеді?'], ['пара слов: тема, сюжет, герои', 'бір-екі сөз: тақырып, сюжет']],
      ['must', ['Что обязательно должно быть?', 'Міндетті түрде не болуы керек?'], ['логотип, слоган, символ', 'логотип, ұран, символ']],
      ['avoid', ['Чего точно не надо?', 'Не болмауы керек?'], ['цвета, темы, детали', 'түстер, тақырыптар']]] },
  { q: ['Фото стены и примеры', 'Қабырға суреті мен мысалдар'], hint: ['Снимите стену целиком. Можно добавить картинки, которые нравятся.', 'Қабырғаны толық түсіріңіз. Ұнаған суреттерді де қосуға болады.'], photos: true,
    text: [['name', ['Кто утверждает эскиз?', 'Эскизді кім бекітеді?'], ['имя', 'аты-жөні']], ['phone', ['Телефон для связи', 'Байланыс телефоны'], ['+7', '+7']]] },
]
const T = { next: ['Дальше', 'Әрі қарай'], back: ['Назад', 'Артқа'], send: ['Отправить', 'Жіберу'], title: ['Бриф на дизайн', 'Дизайнға бриф'],
  of: ['из', '/'], time: ['займёт 2 минуты', '2 минут алады'], skip: ['Не знаете — пропустите, это нормально.', 'Білмесеңіз — өткізіп жіберіңіз.'],
  done: ['Спасибо! Ответы у дизайнера', 'Рақмет! Жауаптар дизайнерде'], doneText: ['Мы подготовим эскиз и покажем его вам. Если что-то вспомните — напишите менеджеру.', 'Эскизді дайындап, сізге көрсетеміз. Тағы бірдеңе есіңізге түссе — менеджерге жазыңыз.'],
  again: ['Изменить ответы', 'Жауаптарды өзгерту'], bad: ['Ссылка не найдена. Попросите у менеджера новую.', 'Сілтеме табылмады. Менеджерден жаңасын сұраңыз.'],
  add: ['Добавить фото', 'Сурет қосу'], sending: ['Отправляю…', 'Жіберілуде…'], fail: ['Не отправилось. Проверьте интернет и нажмите ещё раз.', 'Жіберілмеді. Интернетті тексеріп, қайта басыңыз.'] }

export function ClientBriefPage({ token }) {
  const [kk, setKk] = useState(false)
  const [task, setTask] = useState(undefined)
  const [a, setA] = useState({})
  const [i, setI] = useState(0)
  const [pics, setPics] = useState([])   // [{url, state}]
  const [state, setState] = useState('')
  const L = x => x[kk ? 1 : 0]
  useEffect(() => { document.body.classList.add('cbpage'); document.title = 'ARTGAME — бриф на дизайн'
    fetch(`/api/brief/${encodeURIComponent(token)}`).then(r => r.ok ? r.json() : Promise.reject()).then(t => { setTask(t); setA(t.answers || {}); if (t.done) setState('done'); if (t.answers?.lang === 'kk') setKk(true) }, () => setTask(null)) }, [])
  if (task === undefined) return <div className="cb"><p className="cbmuted">…</p></div>
  const Lang = <div className="cblang"><button className={!kk ? 'on' : ''} onClick={() => setKk(false)}>RU</button><button className={kk ? 'on' : ''} onClick={() => setKk(true)}>ҚАЗ</button></div>
  const Top = <div className="cbtop"><b className="cblogo">ARTGAME</b>{Lang}</div>
  if (task === null) return <div className="cb">{Top}<div className="cbcard"><h1>{L(T.bad)}</h1></div></div>
  if (state === 'done') return <div className="cb">{Top}<div className="cbcard cbdone"><div className="cbok">✓</div><h1>{L(T.done)}</h1><p>{L(T.doneText)}</p>
    <button className="cbghost" onClick={() => { setState(''); setI(0) }}>{L(T.again)}</button></div></div>
  const s = STEPS[i], last = i === STEPS.length - 1
  const pick = (q, opt) => { const cur = a[q.key] || []; setA({ ...a, [q.key]: q.one ? (cur.includes(opt.v) ? [] : [opt.v]) : cur.includes(opt.v) ? cur.filter(x => x !== opt.v) : [...cur, opt.v].slice(-3) }) }
  const Opts = q => <div className="cbopts">{q.opts.map(x => <button key={x.v} className={(a[q.key] || []).includes(x.v) ? 'on' : ''} onClick={() => pick(q, x)}>{kk ? x.kk : x.v}</button>)}</div>
  const addPics = async files => { for (const f of [...files].slice(0, 10)) {
    const id = Math.random().toString(36).slice(2); const url = URL.createObjectURL(f)
    setPics(p => [...p, { id, url, state: 'up' }])
    try { const data = await shrink(f)
      const r = await fetch(`/api/brief/${encodeURIComponent(token)}/photo`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ data }) })
      setPics(p => p.map(x => x.id === id ? { ...x, state: r.ok ? 'ok' : 'bad' } : x))
    } catch { setPics(p => p.map(x => x.id === id ? { ...x, state: 'bad' } : x)) } } }
  const send = () => { setState('sending')
    fetch(`/api/brief/${encodeURIComponent(token)}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ answers: a, lang: kk ? 'kk' : 'ru' }) })
      .then(r => setState(r.ok ? 'done' : 'fail'), () => setState('fail')) }
  return <div className="cb">{Top}
    <div className="cbhead"><h1>{L(T.title)}</h1><p className="cbmuted">{task.title} · {i + 1} {L(T.of)} {STEPS.length} · {L(T.time)}</p>
      <div className="cbbar">{STEPS.map((_, k) => <i key={k} className={k <= i ? 'on' : ''} />)}</div></div>
    <div className="cbcard">
      <h2>{L(s.q)}</h2>{s.hint && <p className="cbmuted">{L(s.hint)}</p>}
      {s.opts && Opts(s)}
      {s.more && <><h2 className="cbh2">{L(s.more.q)}</h2>{Opts(s.more)}</>}
      {s.photos && <div className="cbpics">{pics.map(p => <span key={p.id} className={'cbpic ' + p.state}><img src={p.url} alt="" /></span>)}
        <label className="cbpic add"><span>＋</span><em>{L(T.add)}</em><input type="file" accept="image/*" multiple hidden onChange={e => { const f = e.target.files; f.length && addPics(f); e.target.value = '' }} /></label></div>}
      {(s.text || []).map(([k, label, ph]) => <label key={k} className="cbfield"><span>{L(label)}</span>
        <input value={a[k] || ''} maxLength={300} placeholder={L(ph)} inputMode={k === 'phone' ? 'tel' : 'text'} onChange={e => setA({ ...a, [k]: e.target.value })} /></label>)}
      <p className="cbmuted cbskip">{L(T.skip)}</p>
    </div>
    {state === 'fail' && <p className="cbfail">{L(T.fail)}</p>}
    <div className="cbnav">{i > 0 && <button className="cbghost" onClick={() => setI(i - 1)}>{L(T.back)}</button>}
      {last ? <button className="cbgo" disabled={state === 'sending' || pics.some(p => p.state === 'up')} onClick={send}>{state === 'sending' ? L(T.sending) : L(T.send)}</button>
        : <button className="cbgo" onClick={() => { setI(i + 1); window.scrollTo(0, 0) }}>{L(T.next)}</button>}</div>
  </div>
}
