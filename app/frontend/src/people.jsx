import React, { useEffect, useState } from 'react'
import { api } from './api.js'
import { startViewAs } from './head.jsx'

const ROLE_ZONE = { support: 'mural', artist: 'mural', artist_pro: 'mural', lead_artist: 'mural', print_operator: 'print', print_master: 'print',
  mop: 'sales', mop_vip: 'sales', lead_designer: 'design', designer_asst: 'design' }
const DZ_ROLES = new Set(['lead_designer', 'designer_asst'])
// Связь с пользователем Битрикса: МОП — свои сделки, дизайнеры — свои задачи воронки «Дизайн РК» (без неё «Дизайн» не открывается).
const BX_ROLES = new Set(['mop', 'mop_vip', ...DZ_ROLES])

// Только HEAD: назначить роль и зоны, закрыть вход ушедшему (история остаётся).
export function People({ ROLE, ZONE, openViewAs }) {
  const [list, setList] = useState(null)
  const [bx, setBx] = useState(null)
  const [err, setErr] = useState('')
  const load = () => api('/people').then(setList, () => setList([]))
  useEffect(() => { load(); api('/bx/users').then(setBx, () => setBx([])) }, [])
  if (!list) return <div className="card muted">Загрузка…</div>
  const save = (id, body) => api(`/people/${id}`, { method: 'POST', body }).then(load, e => setErr(e.message))
  // Роль без зоны не пускает в «Смену»: при первой роли сразу ставим её зону, HEAD может поменять кнопками ниже.
  const setRole = (p, role) => save(p.id, { role_code: role, ...(p.zones.length || !ROLE_ZONE[role] ? {} : { zones: [ROLE_ZONE[role]] }) })
  const pendingFirst = [...list].sort((a, b) => (a.status === 'pending' ? -1 : 0) - (b.status === 'pending' ? -1 : 0))
  return <div className="card"><h2>Команда</h2>{err && <p className="muted">{err}</p>}
    {openViewAs && <p className="small"><a className="seeas" onClick={openViewAs}>Посмотреть приложение глазами роли →</a></p>}
    {pendingFirst.map(p => <div key={p.id} className="person">
      <div><b>{p.full_name}</b> {p.tg_username && <span className="muted small">@{p.tg_username}</span>}
        {p.status === 'pending' && <span className="tag st-rejected">ждёт роли</span>}
        {p.status === 'blocked' && <span className="tag">вход закрыт</span>}
        {p.profile_at ? <div className="small muted">{[[p.last_name, p.first_name, p.middle_name].filter(Boolean).join(' '),
          p.birth_date && new Date(p.birth_date).toLocaleDateString('ru-RU'), p.phone, p.city, p.clothes_size && `размер ${p.clothes_size}`,
          p.emergency_phone && `экстренно: ${[p.emergency_name, p.emergency_phone].filter(Boolean).join(' ')}`].filter(Boolean).join(' · ')}</div>
          : <div className="small why">анкета не заполнена — заполнит при следующем входе</div>}</div>
      <select disabled={p.role_code === 'head'} value={p.role_code || ''} onChange={e => setRole(p, e.target.value)}>
        <option value="" disabled>— роль —</option>
        {Object.entries(ROLE).map(([k, t]) => <option key={k} value={k}>{t}</option>)}
      </select>
      {p.role_code && p.role_code !== 'head' && <label className="small muted">Вторая роль <span>· напр. оператор печати + саппорт: сам переключает «Я сейчас», смена — по ставке своей роли</span>
        <select value={(p.extra_roles || [])[0] || ''} onChange={e => { const r = e.target.value
          save(p.id, { extra_roles: r ? [r] : [], ...(r && ROLE_ZONE[r] && !p.zones.includes(ROLE_ZONE[r]) ? { zones: [...p.zones, ROLE_ZONE[r]] } : {}) }) }}>
          <option value="">— нет —</option>
          {Object.entries(ROLE).filter(([k]) => k !== 'head' && k !== p.role_code).map(([k, t]) => <option key={k} value={k}>{t}</option>)}
        </select></label>}
      {p.role_code && p.role_code !== 'head' && <label className="small muted check"><input type="checkbox" checked={!!p.reels} onChange={e => save(p.id, { reels: e.target.checked })} /> Оплачиваемые рилс <span>· «Продакшн», рилс после вашего утверждения — в оплату по «Значениям»</span></label>}
      {p.role_code && p.role_code !== 'head' && <label className="small muted check"><input type="checkbox" checked={!!p.pays} onChange={e => save(p.id, { pays: e.target.checked })} /> Вносит оплаты клиентов <span>· вкладка «Оплаты»: любая сделка по номеру или названию, с фото чека; вы сверяете в «Проверке»</span></label>}
      {p.role_code && p.role_code !== 'head' && <label className="small muted">Исполняет обязанности (и.о.) <span>· права и меню этой роли, ставка — прежняя до дня повышения</span>
        <select value={p.acting_role || ''} onChange={e => save(p.id, { acting_role: e.target.value })}>
          <option value="">— нет —</option>
          {Object.entries(ROLE).filter(([k]) => k !== 'head' && k !== p.role_code).map(([k, t]) => <option key={k} value={k}>{t}</option>)}
        </select></label>}
      {p.acting_role && <div className="acting-edit">
        <label className="small muted">День повышения <input type="date" defaultValue={p.acting_promo || ''} onBlur={e => e.target.value && e.target.value !== p.acting_promo && save(p.id, { acting_promo: e.target.value })} /></label>
        <label className="small muted">Что сказать человеку <input defaultValue={p.acting_note || ''} placeholder="15 декабря — день рождения команды" onBlur={e => e.target.value !== (p.acting_note || '') && save(p.id, { acting_note: e.target.value })} /></label>
        <p className="small muted">В день повышения поставь роль выше — «и.о.» снимется само, ставка станет новой.</p></div>}
      <div className="zones">{Object.entries(ZONE).map(([z, t]) => {
        const on = p.zones.includes(z)
        return <button key={z} className={on ? '' : 'ghost'} onClick={() => save(p.id, { zones: on ? p.zones.filter(x => x !== z) : [...p.zones, z] })}>{t}</button>
      })}</div>
      {BX_ROLES.has(p.role_code) && <label className="small muted">В Битриксе ({DZ_ROLES.has(p.role_code) ? 'по нему видит свои задачи в «Дизайне» и единицы' : 'его сделки увидит в «Сделках»'})
        <select value={p.bitrix_user_id || 0} onChange={e => save(p.id, { bitrix_user_id: +e.target.value })}>
          <option value={0}>— не связан —</option>
          {(bx || []).map(u => <option key={u.id} value={u.id}>{u.name}{u.position ? ` · ${u.position}` : ''}</option>)}
        </select></label>}
      <label className="small muted">Город сотрудника <span>· объект в другом городе — командировка: дорога как смена и суточные</span>
        <input defaultValue={p.city || ''} placeholder="Астана" onBlur={e => e.target.value.trim() !== (p.city || '') && save(p.id, { city: e.target.value })} /></label>
      <IssuedEdit person={p} />
      {p.role_code !== 'head' && p.status !== 'blocked' && <a className="seeas" onClick={() => startViewAs(p.id)}>смотреть как {p.full_name.split(' ')[0]}</a>}
      {p.role_code !== 'head' && (p.status === 'blocked'
        ? <a onClick={() => save(p.id, { status: 'active' })}>открыть вход</a>
        : p.status === 'active' && <a onClick={() => confirm(`Закрыть вход: ${p.full_name}?`) && save(p.id, { status: 'blocked' })}>закрыть вход</a>)}
    </div>)}
  </div>
}

// «Выдано и допуски» (HEAD 08.11): что у человека на руках. HEAD выдаёт, человек в «Кабинете» жмёт «Получил».
export const ITEM_KINDS = [['key', 'Ключи'], ['clothes', 'Одежда'], ['tool', 'Инструмент'], ['access', 'Доступы'], ['permit', 'Допуски'], ['other', 'Другое']]
const IST = { issued: 'на руках', returned: 'вернул', lost: 'утеряно' }
export function IssuedEdit({ person, onlyPermit }) {
  const [open, setOpen] = useState(false)
  const [l, setL] = useState(null)
  const [v, set] = useState({ kind: onlyPermit ? 'permit' : 'key', title: '', qty: 1, note: '' })
  const [err, setErr] = useState('')
  const load = () => api(`/people/${person.id}/items`).then(r => setL(r.items), e => setErr(e.message))
  useEffect(() => { if (open) load() }, [open])
  const add = () => api(`/people/${person.id}/items`, { method: 'POST', body: { ...v, qty: +v.qty || 1, note: v.note || null } })
    .then(() => { set({ ...v, title: '', note: '' }); load() }, e => setErr(e.message))
  const close = (it, status) => confirm(status === 'lost' ? `Отметить «${it.title}» утерянным?` : `«${it.title}» вернули?`) &&
    api(`/items/${it.id}/close`, { method: 'POST', body: { status } }).then(load, e => setErr(e.message))
  const kinds = onlyPermit ? ITEM_KINDS.filter(k => k[0] === 'permit') : ITEM_KINDS
  return <div className="issued">
    <a onClick={() => setOpen(!open)}>{open ? '▴' : '▾'} Выдано и допуски</a>
    {open && <div className="issued-box">
      {err && <p className="small why">{err}</p>}
      {!l ? <p className="small muted">Загрузка…</p> : !l.length ? <p className="small muted">Пока ничего не выдано.</p> :
        l.map(it => <div key={it.id} className={'row it-' + it.status}><div><b>{it.title}</b>{it.qty > 1 ? ` × ${it.qty}` : ''}
          <div className="small muted">{(ITEM_KINDS.find(k => k[0] === it.kind) || [, ''])[1]} · {IST[it.status]}{it.ack_at ? ' · получил ✓' : it.status === 'issued' ? ' · ещё не подтвердил' : ''}{it.note ? ` · ${it.note}` : ''}</div></div>
          {it.status === 'issued' && <span className="acts"><a onClick={() => close(it, 'returned')}>вернул</a> <a onClick={() => close(it, 'lost')}>утеряно</a></span>}</div>)}
      <div className="chips">{kinds.map(([k, t]) => <button key={k} className={v.kind === k ? 'on' : ''} onClick={() => set({ ...v, kind: k })}>{t}</button>)}</div>
      <input placeholder={v.kind === 'permit' ? 'К чему допуск: вышка, аэрограф, принтер…' : v.kind === 'access' ? 'Доступ к чему (без паролей)' : 'Что выдали'} value={v.title} onChange={e => set({ ...v, title: e.target.value })} />
      <div className="seg"><input type="number" min="1" value={v.qty} onChange={e => set({ ...v, qty: e.target.value })} style={{ maxWidth: 90 }} />
        <input placeholder="Примечание" value={v.note} onChange={e => set({ ...v, note: e.target.value })} /></div>
      <button className="mini" disabled={v.title.trim().length < 2} onClick={add}>Выдать</button>
    </div>}
  </div>
}

// В «Кабинете» человека: что у него на руках и допуски; «Получил» — подтверждение.
export function MyIssued() {
  const [l, setL] = useState(null)
  const load = () => api('/items/my').then(r => setL(r.items), () => setL([]))
  useEffect(() => { load() }, [])
  if (!l) return null
  const on = l.filter(x => x.status === 'issued')
  const permits = on.filter(x => x.kind === 'permit'), things = on.filter(x => x.kind !== 'permit')
  const ack = it => api(`/items/${it.id}/ack`, { method: 'POST' }).then(load)
  const Row = it => <div key={it.id} className="row"><div><b>{it.title}</b>{it.qty > 1 ? ` × ${it.qty}` : ''}
    <div className="small muted">{(ITEM_KINDS.find(k => k[0] === it.kind) || [, ''])[1]} · выдал {it.issued_by_name} {new Date(it.issued_at).toLocaleDateString('ru-RU')}{it.note ? ` · ${it.note}` : ''}</div></div>
    {it.ack_at ? <span className="tag st-approved">✓</span> : <button className="mini" onClick={() => ack(it)}>Получил</button>}</div>
  return <div className="card issued-my">
    <h2>Выдано мне</h2>
    {things.length ? things.map(Row) : <p className="small muted">Ключи, одежда, инструмент, доступы — когда выдадут, появятся здесь.</p>}
    <h3 style={{ marginTop: 14 }}>Допуски</h3>
    {permits.length ? permits.map(Row) : <p className="small muted">Допуск к оборудованию даёт Главный художник, Художник-Про или Мастер печати после ТБ.</p>}
    <p className="small muted">За выданное отвечаешь ты: вернуть при уходе, потерю — сразу сообщить.</p>
  </div>
}
