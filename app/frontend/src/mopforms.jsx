import React, { useEffect, useRef, useState } from 'react'
import { api } from './api.js'
import { CityPicker, Sheet } from './ui.jsx'
import { shrink } from './work.jsx'

// HEAD 25.11 «давай делаем»: МОП вводит всё в приложении, в Битриксе у него остаётся только переписка с клиентом.
// Здесь: заявка по звонку, клиент и реквизиты сделки, подписанный договор.

// ---------- заявка по звонку ----------
export function NewLeadSheet({ onClose, onDone }) {
  const [dict, setDict] = useState(null)
  const [f, setF] = useState({ name: '', phone: '', city: '', service: '', source: 'CALL', note: '' })
  const [dups, setDups] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  useEffect(() => { api('/bx/leads-new/dict').then(setDict, e => setErr(e.message)) }, [])
  const digits = f.phone.replace(/\D/g, '').length
  const ok = f.name.trim() && digits >= 10
  const send = force => {
    setBusy(true); setErr('')
    api('/bx/leads-new', { method: 'POST', body: { ...f, city: f.city || null, service: f.service || null, force } })
      .then(r => onDone(r.lead), e => { if (e.status === 409 && e.detail?.dups) setDups(e.detail.dups); else setErr(e.message) })
      .finally(() => setBusy(false))
  }
  return <Sheet title="Заявка по звонку" onClose={onClose}>
    {!dict ? <p className="muted small">{err || 'Загрузка…'}</p> : dups ? <div className="dealedit">
      <p className="small why">Этот номер уже есть в Битриксе:</p>
      {dups.map(x => <div key={x.kind + x.id} className="row"><span>{x.kind === 'lead' ? 'Лид' : 'Контакт'} № {x.id} · {x.name || 'без имени'}</span>
        <span className="small muted">{x.manager}</span></div>)}
      <p className="small muted">Если это тот же клиент — откройте его лид в «Лидах». Новый лид — только если это другой запрос.</p>
      <div className="dealbtns"><button className="mini" disabled={busy} onClick={() => send(true)}>{busy ? 'Завожу…' : 'Всё равно завести'}</button>
        <button className="ghost mini" onClick={() => setDups(null)}>Назад</button></div>
    </div> : <div className="dealedit newlead">
      <label><span>Имя клиента</span><input value={f.name} onChange={e => setF({ ...f, name: e.target.value })} placeholder="Как обращаться" /></label>
      <label><span>Телефон</span><input value={f.phone} type="tel" inputMode="tel" onChange={e => setF({ ...f, phone: e.target.value })} placeholder="+7 7__ ___ __ __" /></label>
      <span className="cplabel">Откуда клиент</span>
      <div className="chips">{dict.sources.map(s => <button key={s.id} className={f.source === s.id ? 'on' : ''} onClick={() => setF({ ...f, source: s.id })}>{s.name}</button>)}</div>
      <CityPicker cities={dict.cities} value={f.city} onPick={id => setF({ ...f, city: id })} label="Город (если знаете)" />
      {!!dict.services.length && <label><span>Услуга</span><select value={f.service} onChange={e => setF({ ...f, service: e.target.value })}>
        <option value="">— пока не знаю —</option>{dict.services.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>}
      <label><span>Что хочет клиент</span><textarea rows={3} value={f.note} onChange={e => setF({ ...f, note: e.target.value })} placeholder="Помещение, площадь, сроки — что сказал по телефону" /></label>
      {err && <p className="small why">{err}</p>}
      <button disabled={busy || !ok} onClick={() => send(false)}>{busy ? 'Завожу…' : 'Завести заявку'}</button>
      <p className="small muted">Лид появится в Битриксе на вас, со звонком в источнике. Дальше — как обычно: квалификация и «В сделку».</p>
    </div>}
  </Sheet>
}

// ---------- клиент и реквизиты ----------
const TYPES = ['Физлицо', 'ТОО', 'ИП']
export function ClientSheet({ dealId, onClose, onDone }) {
  const [f, setF] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  useEffect(() => { api(`/bx/deals/${dealId}/client`).then(c => setF({ ...c, company: c.company || '' }), e => setErr(e.message)) }, [dealId])
  const set = (k, v) => setF({ ...f, [k]: v })
  const save = () => {
    setBusy(true); setErr('')
    const { type, name, phone, email, company, bin, signer, signer_pos, bank, bik, iik } = f
    api(`/bx/deals/${dealId}/client`, { method: 'POST', body: { type, name, phone, email, company, bin, signer, signer_pos, bank, bik, iik } })
      .then(r => onDone(r.done.length ? 'Записано в Битрикс: ' + r.done.join(', ') + '.' : 'Ничего не поменялось.'), e => setErr(e.message))
      .finally(() => setBusy(false))
  }
  const firm = f && f.type !== 'Физлицо'
  return <Sheet title="Клиент и реквизиты" onClose={onClose}>
    {!f ? <p className="muted small">{err || 'Загрузка…'}</p> : <div className="dealedit client">
      <div className="seg">{TYPES.map(t => <button key={t} className={f.type === t ? '' : 'ghost'} onClick={() => set('type', t)}>{t}</button>)}</div>
      {firm && <label><span>{f.type === 'ИП' ? 'ИП (как в документах)' : 'Название ТОО'}</span>
        <input value={f.company} onChange={e => set('company', e.target.value)} placeholder={f.type === 'ИП' ? 'ИП Иванов' : 'ТОО «Ромашка»'} /></label>}
      <label><span>{firm ? 'Контактное лицо' : 'ФИО клиента'}</span><input value={f.name} onChange={e => set('name', e.target.value)} placeholder="Фамилия Имя" /></label>
      <label><span>Телефон</span><input value={f.phone} type="tel" inputMode="tel" onChange={e => set('phone', e.target.value)} placeholder="+7 7__ ___ __ __" /></label>
      <label><span>Почта</span><input value={f.email} type="email" inputMode="email" onChange={e => set('email', e.target.value)} placeholder="для договора и счёта" /></label>
      <h4>Реквизиты для договора</h4>
      <label><span>{f.type === 'ТОО' ? 'БИН' : 'ИИН'}</span><input value={f.bin} inputMode="numeric" onChange={e => set('bin', e.target.value.replace(/\D/g, '').slice(0, 12))} placeholder="12 цифр" /></label>
      {f.type === 'ТОО' && <div className="row2">
        <label><span>Кто подписывает</span><input value={f.signer} onChange={e => set('signer', e.target.value)} placeholder="ФИО директора" /></label>
        <label><span>Должность</span><input value={f.signer_pos} onChange={e => set('signer_pos', e.target.value)} placeholder="Директор" /></label></div>}
      {firm && <>
        <label><span>Банк</span><input value={f.bank} onChange={e => set('bank', e.target.value)} placeholder="АО «Kaspi Bank»" /></label>
        <div className="row2">
          <label><span>БИК</span><input value={f.bik} onChange={e => set('bik', e.target.value.toUpperCase().slice(0, 8))} placeholder="CASPKZKA" /></label>
          <label><span>ИИК</span><input value={f.iik} onChange={e => set('iik', e.target.value.toUpperCase().replace(/\s/g, '').slice(0, 20))} placeholder="KZ…" /></label></div></>}
      {err && <p className="small why">{err}</p>}
      <button disabled={busy} onClick={save}>{busy ? 'Записываю…' : 'Сохранить'}</button>
      <p className="small muted">Записывается в Битрикс: в контакт{firm ? ', компанию и её реквизиты' : ''}. Договор и счёт возьмут их сами.</p>
    </div>}
  </Sheet>
}

// ---------- подписанный договор ----------
const readFile = file => new Promise((ok, fail) => { const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = fail; r.readAsDataURL(file) })
export function SignedUpload({ d, onDone }) {
  const inp = useRef(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const have = (d.files || []).filter(x => (x.title || '').startsWith('Договор подписанный'))
  const pick = async file => {
    if (!file) return
    setBusy(true); setErr('')
    try {
      if (file.size > 12 * 1024 * 1024 && file.type === 'application/pdf') throw new Error('PDF больше 12 МБ — сожмите его или снимите фото')
      const data = file.type.startsWith('image/') ? await shrink(file) : await readFile(file)
      const r = await api(`/bx/deals/${d.id}/signed`, { method: 'POST', body: { name: file.name, data } })
      onDone(r, 'Подписанный договор в сделке' + (r.drive ? ' и в папке «ДОКУМЕНТЫ».' : '.') + (r.held?.length ? ' Стадия не сменилась — не хватает: ' + r.held.join(', ') : ''))
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  return <div className="card signed">
    <h3>Подписанный договор</h3>
    {have.length ? <p className="small">В сделке: {have.length} {have.length === 1 ? 'файл' : 'файла'}. Можно добавить ещё страницу.</p>
      : <p className="small muted">Скан или фото подписанного договора. Ляжет в сделку и в папку «ДОКУМЕНТЫ»; когда аванс уже внесён — сделка сама перейдёт в работу.</p>}
    <input ref={inp} type="file" hidden accept="application/pdf,image/jpeg,image/png" onChange={e => { pick(e.target.files[0]); e.target.value = '' }} />
    <button className={have.length ? 'ghost' : ''} disabled={busy} onClick={() => inp.current?.click()}>{busy ? 'Загружаю…' : have.length ? '+ Ещё файл' : 'Загрузить подписанный договор'}</button>
    {err && <p className="small why">{err}</p>}
  </div>
}
