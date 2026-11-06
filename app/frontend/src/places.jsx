import React, { useEffect, useRef, useState } from 'react'
import { api } from './api.js'

// Рабочие места ролей (бывшие артефакты) во фрейме по подписанной ссылке.
// mode='study' (HEAD 06.11): место МОП как «Учёба» — только учебник, тест, правила игры; рабочие разделы живут в карточке сделки.
export function Places({ list, mode }) {
  const [code, setCode] = useState(() => { try { return localStorage.getItem('artgame.place') || '' } catch { return '' } })
  const [hash, setHash] = useState('')
  const cur = list.find(p => p.code === code) || list[0]
  const frame = useRef(null)
  useEffect(() => {
    const on = e => {
      if (e.origin !== location.origin || e.data?.type !== 'artgame:place') return
      if (list.some(p => p.code === e.data.code)) { setCode(e.data.code); setHash(e.data.hash || '') }
    }
    window.addEventListener('message', on)
    return () => window.removeEventListener('message', on)
  }, [list])
  useEffect(() => { try { cur && !mode && localStorage.setItem('artgame.place', cur.code) } catch { /* без памяти */ } }, [cur])
  if (!cur) return <div className="card muted">Для твоей роли рабочего места пока нет.</div>
  const src = cur.url + (mode ? `?mode=${mode}` : '') + (hash || (mode === 'study' ? '#ucheb' : ''))
  return <div className="place">
    {list.length > 1 && <div className="chips">{list.map(p =>
      <button key={p.code} className={p.code === cur.code ? 'on' : ''} onClick={() => { setCode(p.code); setHash('') }}>{p.title}</button>)}</div>}
    <iframe ref={frame} key={cur.code + hash + (mode || '')} title={cur.title} src={src} className="placeframe" />
  </div>
}

// Панель рабочего места внутри карточки сделки: один раздел (#kp или #docs), без шапки; сделка и расчёт подставлены (place_bx.js).
export function Embed({ place, view, dealId, kp, ds, onDoc }) {
  const [n, setN] = useState(0)
  useEffect(() => {
    const on = e => { if (e.origin === location.origin && e.data?.type === 'artgame:doc' && onDoc) onDoc(e.data) }
    window.addEventListener('message', on)
    return () => window.removeEventListener('message', on)
  }, [onDoc])
  if (!place) return <p className="small muted">Рабочее место МОП недоступно для вашей роли.</p>
  try { localStorage.setItem('artgame.bx.open', JSON.stringify({ id: dealId, view, kp, ds, t: Date.now() })) } catch { /* без памяти */ }
  return <div className="embed">
    <iframe key={view + dealId + n} title={view} src={`${place.url}?mode=embed#${view}`} />
    <button className="ghost mini" style={{ position: 'absolute', top: 8, right: 8 }} onClick={() => setN(n + 1)}>Заново</button>
  </div>
}

export function usePlaces() {
  const [list, setList] = useState([])
  useEffect(() => { api('/places').then(setList, () => setList([])) }, [])
  return list
}
