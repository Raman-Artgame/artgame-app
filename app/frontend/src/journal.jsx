import React, { useEffect, useState } from 'react'
import { api } from './api.js'

const clean = (id, t) => (t || '').replace(new RegExp(`^№?\\s*${id}\\s*·?\\s*`), '')
export const LABEL = {
  deal_open: d => `Открыл сделку № ${d.entity_id}${d.data?.title ? ' · ' + clean(d.entity_id, d.data.title) : ''}${d.data?.via === 'kp' ? ' (КП)' : ''}`,
  place_download: d => `Скачал ${d.data?.name || 'файл'}`,
  shift_add: () => 'Отправил смену',
  expense_add: () => 'Отправил расход',
  shift_cancel: () => 'Отменил смену',
  expense_cancel: () => 'Отменил расход',
  bx_write: d => `Записал в Битрикс: сделка № ${d.entity_id}${d.data?.what ? ' · ' + d.data.what : ''}`,
  file_add: d => `Загрузил файл${d.data?.name ? ' ' + d.data.name : ''}`,
  place_doc_set: d => `Изменил документ ${d.entity_id}`,
  view_as_start: d => `Смотрел приложение как ${d.data?.name || d.data?.target || 'сотрудник'}`,
  view_as_stop: () => 'Вернулся к себе',
}
const day = s => new Date(s).toLocaleDateString('ru-RU', { weekday: 'short', day: 'numeric', month: 'long' })
const tm = s => new Date(s).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })

// Мой журнал: свои действия по дням. HEAD видит сводку по МОП и журнал любого из них. Это тот же журнал действий в базе.
export function Journal({ me }) {
  const [person, setPerson] = useState(null)
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => { setData(null); api(`/journal${person ? `?person=${person}` : ''}`).then(setData, e => setErr(e.message)) }, [person])
  if (err) return <div className="card muted">{err}</div>
  if (!data) return <div className="card muted">Загрузка…</div>
  const groups = {}
  data.items.forEach(it => { (groups[day(it.at)] ||= []).push(it) })
  const who = data.summary?.find(s => s.id === person)
  return <>
    {data.summary && <div className="card"><h2>МОП сегодня</h2>
      {!data.summary.length && <p className="muted">Пока никто из МОП не заходил.</p>}
      {data.summary.map(s => <div key={s.id} className="row" onClick={() => setPerson(s.id === person ? null : s.id)}>
        <div><b>{s.full_name}</b><div className="muted small">сделок {s.deals_today} · файлов {s.files_today} · действий {s.today}</div></div>
        <a>{s.id === person ? 'мой журнал' : 'журнал'}</a>
      </div>)}
    </div>}
    <div className="card"><h2>{who ? `Журнал: ${who.full_name}` : 'Мой журнал'}</h2>
      {!data.items.length && <p className="muted">За 30 дней действий нет.</p>}
      {Object.entries(groups).map(([d, items]) => <div key={d}>
        <div className="dealstage">{d}</div>
        {items.map(it => <div key={it.id} className="row"><div>{(LABEL[it.action] || (() => it.action))(it)}
          {it.data?.bx && <span className={`tag ${it.data.bx === 'ok' ? '' : 'st-rejected'}`}>{it.data.bx === 'ok' ? 'в Битриксе' : 'не записано'}</span>}</div>
          <span className="muted small">{tm(it.at)}</span></div>)}
      </div>)}
    </div>
  </>
}
