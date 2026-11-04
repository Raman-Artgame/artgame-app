import React, { useEffect, useRef, useState } from 'react'
import { api } from './api.js'

// Рабочие места ролей (бывшие артефакты). Страница места — во фрейме по подписанной ссылке.
export function Places({ list }) {
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
  useEffect(() => { try { cur && localStorage.setItem('artgame.place', cur.code) } catch { /* без памяти */ } }, [cur])
  if (!cur) return <div className="card muted">Для твоей роли рабочего места пока нет.</div>
  return <div className="place">
    {list.length > 1 && <div className="chips">{list.map(p =>
      <button key={p.code} className={p.code === cur.code ? 'on' : ''} onClick={() => { setCode(p.code); setHash('') }}>{p.title}</button>)}</div>}
    <iframe ref={frame} key={cur.code + hash} title={cur.title} src={cur.url + hash} className="placeframe" />
  </div>
}

export function usePlaces() {
  const [list, setList] = useState([])
  useEffect(() => { api('/places').then(setList, () => setList([])) }, [])
  return list
}
