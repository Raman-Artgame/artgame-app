import React, { useEffect, useState } from 'react'
import { api } from './api.js'

// «Написать обращение» (HEAD 08.11): у всех в «Кабинете» — ошибка, доработка, вопрос. HEAD видит в «Пульте», ответ приходит сюда и в бот.
const KIND = [['bug', '🐞 Ошибка'], ['idea', '💡 Доработка'], ['question', '❓ Вопрос'], ['other', '✉️ Другое']]
const KT = Object.fromEntries(KIND)
const ST = { new: 'отправлено', work: 'в работе', done: 'готово' }
const dm = s => new Date(s).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })

export function Feedback() {
  const [open, setOpen] = useState(false)
  const [v, set] = useState({ kind: 'bug', text: '', place: '' })
  const [items, setItems] = useState([])
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const load = () => api('/feedback/my').then(r => setItems(r.items), () => setItems([]))
  useEffect(() => { load() }, [])
  const send = () => {
    setBusy(true); setMsg('')
    api('/feedback', { method: 'POST', body: { ...v, text: v.text.trim() } })
      .then(() => { set({ kind: 'bug', text: '', place: '' }); setOpen(false); setMsg('Отправлено HEAD. Ответ придёт сюда и в бот.'); load() }, e => setMsg(e.message))
      .finally(() => setBusy(false))
  }
  return <div className="card fb">
    <div className="head"><div><h3>Написать обращение</h3><p className="small muted">Нашёл ошибку, есть идея, как сделать удобнее, или вопрос — напиши HEAD.</p></div>
      {!open && <button className="mini" onClick={() => setOpen(true)}>Написать</button>}</div>
    {open && <div className="fbform">
      <div className="chips">{KIND.map(([k, t]) => <button key={k} className={v.kind === k ? 'on' : ''} onClick={() => set({ ...v, kind: k })}>{t}</button>)}</div>
      <input placeholder="Где: вкладка или экран (например, «Смена»)" value={v.place} onChange={e => set({ ...v, place: e.target.value })} />
      <textarea rows={4} placeholder={v.kind === 'bug' ? 'Что сделал и что пошло не так' : 'Опиши коротко'} value={v.text} onChange={e => set({ ...v, text: e.target.value })} />
      <div className="seg"><button className="ghost" onClick={() => setOpen(false)}>Отмена</button>
        <button disabled={busy || v.text.trim().length < 3} onClick={send}>{busy ? 'Отправляю…' : 'Отправить'}</button></div>
    </div>}
    {msg && <p className="small ok">{msg}</p>}
    {items.length > 0 && <div className="fblist">{items.map(f => <div key={f.id} className="fbrow">
      <div className="small muted">{KT[f.kind]} · {dm(f.created_at)}{f.place ? ' · ' + f.place : ''}</div>
      <div>{f.text}</div>
      {f.answer && <div className="fbans"><b>HEAD:</b> {f.answer}</div>}
      <span className={'tag' + (f.status === 'done' ? ' st-approved' : '')}>{ST[f.status]}</span>
    </div>)}</div>}
  </div>
}

// В «Пульте» HEAD: новые и в работе — ответить, взять в работу, закрыть.
export function FeedbackInbox({ items, reload }) {
  const [ans, setAns] = useState({})
  if (!items?.length) return null
  const act = (id, body) => api(`/feedback/${id}`, { method: 'POST', body }).then(reload, e => alert(e.message))
  return <div className="card fb"><h3>Обращения · {items.length}</h3>
    {items.map(f => <div key={f.id} className="fbrow">
      <div className="small muted">{KT[f.kind]} · {f.full_name}{f.role_title ? ' · ' + f.role_title : ''} · {dm(f.created_at)}{f.place ? ' · ' + f.place : ''}</div>
      <div>{f.text}</div>
      <textarea rows={2} placeholder="Ответ (придёт человеку в бот)" value={ans[f.id] || ''} onChange={e => setAns({ ...ans, [f.id]: e.target.value })} />
      <div className="qbtns">
        {f.status === 'new' && <button className="ghost mini" onClick={() => act(f.id, { status: 'work', answer: ans[f.id] || null })}>В работу</button>}
        <button className="mini" onClick={() => act(f.id, { status: 'done', answer: ans[f.id] || null })}>Готово</button>
        {f.status === 'work' && <span className="tag">в работе</span>}
      </div>
    </div>)}
  </div>
}
