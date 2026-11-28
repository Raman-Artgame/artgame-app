import React, { useEffect, useState } from 'react'
import { api } from './api.js'

// «Итоги» маркетинга (HEAD 26.11): что залетело по рубрикам и форматам и куда двигаться. Публикация плана связана с постом
// Instagram по ссылке из «Вышло»; цифры — из ночного сбора Meta. Видят HEAD и руководитель агентства.
const num = n => n == null ? '—' : Math.round(n).toLocaleString('ru-RU')
const dm = s => String(s).slice(0, 10).split('-').reverse().slice(0, 2).join('.')

function Groups({ title, list }) {
  const max = Math.max(1, ...list.map(g => g.views_avg || 0))
  if (!list.length) return null
  return <div className="mktnorms"><span className="small muted">{title}</span>
    {list.map(g => <div key={g.title || '-'} className="mktnorm"><div><b>{g.title || 'Без рубрики'}</b></div>
      <span className="small muted">{g.posts} публ. · {g.linked ? `${num(g.views_avg)} просм. в среднем` : 'нет цифр'}{g.er != null ? ` · реакций ${g.er}%` : ''}{g.leads ? ` · заявок ${g.leads}` : ''}</span>
      <i><u style={{ width: (g.views_avg || 0) / max * 100 + '%' }} /></i>
      {g.best && g.best.url && <a className="small muted" href={g.best.url} target="_blank" rel="noreferrer">лучшее: {g.best.title} · {num(g.best.views)}</a>}</div>)}
  </div>
}

function Week({ s, onSaved }) {
  const [f, setF] = useState(null)
  const [msg, setMsg] = useState('')
  const save = () => api('/mkt/reports', { method: 'POST', body: f }).then(() => { setF(null); setMsg('Сохранено.'); onSaved() }, e => setMsg(e.message))
  return <div className="card">
    <div className="head"><h3>Недельный вывод</h3>{s.can_write && !f && <button className="mini" onClick={() => setF({ worked: '', next_step: '' })}>+ За прошлую неделю</button>}</div>
    <p className="small muted">Раз в неделю: что сработало и что делаем дальше. Цифры выше приложение считает само, здесь — выводы агентства.</p>
    {f && <div className="warnbox">
      <textarea rows="3" placeholder="Что сработало и что нет (по цифрам выше)" value={f.worked} onChange={e => setF({ ...f, worked: e.target.value })} />
      <textarea rows="3" placeholder="Что делаем на следующей неделе" value={f.next_step} onChange={e => setF({ ...f, next_step: e.target.value })} />
      <div className="seg"><button className="ghost" onClick={() => setF(null)}>Отмена</button>
        <button disabled={f.worked.trim().length < 3 || f.next_step.trim().length < 3} onClick={save}>Сохранить</button></div></div>}
    {msg && <p className="small muted">{msg}</p>}
    {!s.weeks.length && !f && <p className="small muted">Выводов пока нет.</p>}
    {s.weeks.map(w => <div key={w.week} className="shoot"><b>Неделя с {dm(w.week)}</b>
      <div className="small">Сработало: {w.worked}</div><div className="small">Дальше: {w.next_step}</div>
      <div className="small muted">{w.author}</div></div>)}
  </div>
}

export function Stats() {
  const [days, setDays] = useState(30)
  const [s, setS] = useState(null)
  const [tick, setTick] = useState(0)
  useEffect(() => { api(`/mkt/stats?days=${days}`).then(setS, e => setS({ err: e.message })) }, [days, tick])
  if (!s) return <div className="card"><p className="muted">Загрузка…</p></div>
  if (s.err) return <div className="card"><p className="small why">{s.err}</p></div>
  const t = s.totals
  return <>
    <div className="card">
      <div className="head"><h3>Итоги</h3><span className="small muted">{dm(s.from)}–{dm(s.to)}</span></div>
      <div className="segf">{[7, 30, 90].map(n => <button key={n} className={days === n ? 'on' : ''} onClick={() => setDays(n)}>{n} дн.</button>)}</div>
      <div className="mstats mkt4"><div><b>{t.posts}</b><span>вышло по плану</span></div><div><b>{t.linked}</b><span>с цифрами Instagram</span></div>
        <div><b>{num(t.views)}</b><span>просмотры</span></div><div><b>{t.leads}</b><span>заявки</span></div></div>
      <div className="warnbox"><b>Куда двигаться</b>{s.advice.map((a, i) => <p key={i} className="small">{a}</p>)}</div>
      <Groups title="По рубрикам" list={s.by_rubric} />
      <Groups title="По форматам" list={s.by_kind} />
      {s.top.length > 0 && <><p className="small muted">Лучшее за период</p>
        {s.top.map(x => <a key={x.id} className="metatop" href={x.url || undefined} target="_blank" rel="noreferrer"><span>{x.kind} · {x.title}</span><b>{num(x.views)}</b></a>)}</>}
      {s.weak.length > 0 && <><p className="small muted">Слабее всего</p>
        {s.weak.map(x => <a key={x.id} className="metatop" href={x.url || undefined} target="_blank" rel="noreferrer"><span>{x.kind} · {x.title}</span><b>{num(x.views)}</b></a>)}</>}
      <p className="small muted">Цифры приходят из Instagram ночью. Публикация попадает сюда, когда в «Вышло» вставлена ссылка на пост.</p>
    </div>
    <Week s={s} onSaved={() => setTick(x => x + 1)} />
  </>
}
