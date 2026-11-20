import React, { useState } from 'react'
import { api } from './api.js'

// Анкета «Мои данные» (HEAD 09.11): имя в приложении — из анкеты, а не из Telegram. Заполняет сам человек:
// при первом входе — до всего остального, потом правит в «Кабинете». HEAD видит анкету в «Команде».
const SIZES = ['XS', 'S', 'M', 'L', 'XL', 'XXL']
const CITIES = ['Астана', 'Шымкент', 'Алматы', 'Караганда']
const YMD = d => d ? String(d).slice(0, 10) : ''

export function ProfileForm({ me, onDone, first, onCancel }) {
  const tg = window.Telegram?.WebApp?.initDataUnsafe?.user
  const [v, set] = useState({
    last_name: me?.last_name || (first ? tg?.last_name || '' : ''), first_name: me?.first_name || (first ? tg?.first_name || '' : ''),
    middle_name: me?.middle_name || '', birth_date: YMD(me?.birth_date), phone: me?.phone || '', city: me?.city || '',
    emergency_name: me?.emergency_name || '', emergency_phone: me?.emergency_phone || '', clothes_size: me?.clothes_size || '' })
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const f = k => ({ value: v[k], onChange: e => set({ ...v, [k]: e.target.value }) })
  const ok = v.last_name.trim().length >= 2 && v.first_name.trim().length >= 2 && v.birth_date && v.phone.replace(/\D/g, '').length >= 10 && v.city.trim().length >= 2
  const send = async () => {
    setBusy(true); setErr('')
    try {
      if (!me) await api('/register', { method: 'POST', body: { full_name: `${v.first_name.trim()} ${v.last_name.trim()}`, phone: v.phone } })
      await api('/profile', { method: 'POST', body: { ...v, middle_name: v.middle_name || null, emergency_name: v.emergency_name || null,
        emergency_phone: v.emergency_phone || null, clothes_size: v.clothes_size || null } })
      onDone(await api('/me'))
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  return <div className="card profile">
    {first ? <><h1>{me ? 'Мои данные' : 'Добро пожаловать'}</h1>
      <p className="muted">Заполни анкету — так тебя увидят в приложении, в сменах и в оплате. {me ? '' : 'Потом HEAD назначит тебе роль.'}</p></> :
      <h2>Мои данные</h2>}
    <label className="muted">Фамилия *</label><input {...f('last_name')} autoComplete="family-name" placeholder="как в удостоверении" />
    <label className="muted">Имя *</label><input {...f('first_name')} autoComplete="given-name" />
    <label className="muted">Отчество</label><input {...f('middle_name')} autoComplete="additional-name" placeholder="если есть" />
    <label className="muted">Дата рождения *</label><input type="date" {...f('birth_date')} max={new Date(Date.now() - 14 * 365.25 * 864e5).toISOString().slice(0, 10)} />
    <label className="muted">Телефон *</label><input {...f('phone')} inputMode="tel" autoComplete="tel" placeholder="+7 7__ ___ __ __" />
    <label className="muted">Город *</label>
    <div className="chips">{CITIES.map(c => <button key={c} type="button" className={v.city === c ? 'on' : ''} onClick={() => set({ ...v, city: c })}>{c}</button>)}</div>
    <input {...f('city')} placeholder="или другой город" />
    <label className="muted">Кому звонить в экстренном случае</label>
    <div className="pair"><input {...f('emergency_name')} placeholder="Кто (мама, брат…)" /><input {...f('emergency_phone')} inputMode="tel" placeholder="Телефон" /></div>
    <label className="muted">Размер одежды (форма ARTGAME)</label>
    <div className="chips">{SIZES.map(s => <button key={s} type="button" className={v.clothes_size === s ? 'on' : ''} onClick={() => set({ ...v, clothes_size: v.clothes_size === s ? '' : s })}>{s}</button>)}</div>
    {err && <p className="small why">{err}</p>}
    <button disabled={!ok || busy} onClick={send}>{busy ? 'Сохраняю…' : 'Сохранить'}</button>
    {onCancel && <button className="ghost" onClick={onCancel}>Отмена</button>}
    <p className="small muted">* — обязательно. Данные видят только HEAD и ты.</p>
  </div>
}

// В «Кабинете»: свёрнуто одной строкой, «Изменить» открывает анкету
export function MyData({ me, onMe }) {
  const [edit, setEdit] = useState(false)
  if (me._view_as) return null
  if (edit) return <ProfileForm me={me} onDone={m => { setEdit(false); onMe?.(m) }} onCancel={() => setEdit(false)} />
  const age = me.birth_date ? Math.floor((Date.now() - new Date(me.birth_date)) / (365.25 * 864e5)) : null
  return <div className="card mydata">
    <div className="head"><h3>Мои данные</h3><button className="ghost mini" onClick={() => setEdit(true)}>Изменить</button></div>
    <p className="small">{[me.last_name, me.first_name, me.middle_name].filter(Boolean).join(' ') || me.full_name}</p>
    <p className="small muted">{[me.birth_date && new Date(me.birth_date).toLocaleDateString('ru-RU') + (age ? ` (${age})` : ''), me.phone, me.city, me.clothes_size && `размер ${me.clothes_size}`].filter(Boolean).join(' · ')}</p>
    {me.emergency_phone && <p className="small muted">Экстренно: {[me.emergency_name, me.emergency_phone].filter(Boolean).join(', ')}</p>}
  </div>
}
