import React, { useEffect, useRef, useState } from 'react'
import { api } from './api.js'

// Рабочие места ролей (бывшие артефакты) во фрейме по подписанной ссылке.
// mode='study' (HEAD 06.11): место МОП как «Учёба» — только учебник, тест, правила игры; рабочие разделы живут в карточке сделки.
// opts[code] = { hide: [...], home } — скрыть разделы места (place_shim.js), extra — своя вкладка-чип (должностная).
export function Places({ list, mode, opts = {}, extra: ex }) {
  const extras = (Array.isArray(ex) ? ex : ex ? [ex] : []).filter(Boolean)
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
  const extra = extras.find(x => x.code === code)
  const onExtra = !!extra
  if (!cur && !extras.length) return <div className="card muted">Для твоей роли рабочего места пока нет.</div>
  const o = (cur && opts[cur.code]) || {}
  // sections (HEAD 08.11): разделы места — такими же чипами, как «ТБ» и «Правила игры», в одном ряду; свои вкладки места скрыты
  const secs = o.sections || null
  const q = new URLSearchParams({ ...(mode ? { mode } : {}), ...(o.hide?.length ? { hide: o.hide.join(','), home: o.home || '' } : {}), ...(o.nocalc ? { nocalc: '1' } : {}),
    ...(secs ? { notabs: '1' } : {}), dark: '1' }).toString()
  const src = cur ? cur.url + (q ? '?' + q : '') + (hash || (o.home ? '#' + o.home : mode === 'study' ? '#ucheb' : '')) : ''
  const curSec = (hash || '#' + (o.home || 'ucheb')).slice(1).split('-')[0]
  return <div className="place">
    {(list.length > 1 || extras.length > 0 || secs) && <div className="chips placechips">{secs ? secs.map(([h, t, c]) =>   // c — раздел другого места (HEAD 11.11: Главным и Про — учебник печати рядом со своим)
      <button key={(c || '') + h} className={!onExtra && curSec === h && (c || cur.code) === cur.code ? 'on' : ''} onClick={() => { setCode(c || cur.code); setHash('#' + h) }}>{t}</button>) : list.map(p =>
      <button key={p.code} className={!onExtra && p.code === cur.code ? 'on' : ''} onClick={() => { setCode(p.code); setHash('') }}>{p.title}</button>)}
      {extras.map(x => <button key={x.code} className={code === x.code ? 'on' : ''} onClick={() => setCode(x.code)}>{x.title}</button>)}</div>}
    {onExtra || !cur ? <div className="placeextra">{(extra || extras[0]).render()}</div> : <iframe ref={frame} key={cur.code + hash + (mode || '')} title={cur.title} src={src} className="placeframe" allow="fullscreen" allowFullScreen />}
  </div>
}

// Панель рабочего места внутри карточки сделки: один раздел (#kp или #docs), без шапки; сделка и расчёт подставлены (place_bx.js).
// view="calc" (HEAD 26.11): полный калькулятор блока; calc — что подставить из сделки, onCalc(msg, reply) — «Записать в сделку».
export function Embed({ place, view, dealId, kp, ds, calc, onDoc, onCalc }) {
  const [n, setN] = useState(0)
  useEffect(() => {
    const on = e => {
      if (e.origin !== location.origin) return
      if (e.data?.type === 'artgame:doc' && onDoc) onDoc(e.data)
      if (e.data?.type === 'artgame:calc' && onCalc && e.data.deal === dealId)
        onCalc(e.data, (ok, text) => e.source?.postMessage({ type: 'artgame:calc-done', ok, text }, location.origin))
    }
    window.addEventListener('message', on)
    return () => window.removeEventListener('message', on)
  }, [onDoc, onCalc, dealId])
  // высота фрейма — по содержимому (HEAD 26.11 «чтобы ничего не застревало»): одна прокрутка страницы, без второй внутри
  const fr = useRef(null)
  useEffect(() => {
    const t = setInterval(() => {
      try {
        const doc = fr.current?.contentDocument, app = doc?.getElementById('app') || doc?.body
        if (!app) return
        const h = Math.min(8000, Math.max(480, Math.ceil(app.getBoundingClientRect().bottom + (doc.defaultView.scrollY || 0)) + 24))
        if (Math.abs(fr.current.offsetHeight - h) > 8) fr.current.style.height = h + 'px'
      } catch { /* другой адрес — оставляем как есть */ }
    }, 400)
    return () => clearInterval(t)
  }, [view, dealId, n])
  if (!place) return <p className="small muted">Рабочее место МОП недоступно для вашей роли.</p>
  try { localStorage.setItem('artgame.bx.open', JSON.stringify({ id: dealId, view, kp, ds, calc, t: Date.now() })) } catch { /* без памяти */ }
  return <div className="embed">
    <iframe ref={fr} key={view + dealId + n} title={view} src={`${place.url}?mode=embed&dark=1#${view}`} />
    <button className="ghost mini" style={{ position: 'absolute', top: 8, right: 8 }} onClick={() => setN(n + 1)}>Заново</button>
  </div>
}

export function usePlaces() {
  const [list, setList] = useState([])
  useEffect(() => { api('/places').then(setList, () => setList([])) }, [])
  return list
}

// Блок «Расчёт · КП · Документы · Скрипты» целиком (HEAD 26.11: «все калькуляторы, генераторы КП — в одном месте,
// а фокус — на сделке»). Из сделки — окном поверх карточки, данные сделки подставлены в каждый раздел; закрыли — снова сделка.
// view — раздел, с которого открыть; onCalc / onDoc — «Записать в сделку» и скачанный документ (как у Embed).
export function Tools({ place, dealId, title, view, kp, ds, calc, onDoc, onCalc, close, bar }) {
  useEffect(() => {
    const on = e => {
      if (e.origin !== location.origin) return
      if (e.data?.type === 'artgame:doc' && onDoc) onDoc(e.data)
      if (e.data?.type === 'artgame:calc' && onCalc && e.data.deal === dealId)
        onCalc(e.data, (ok, text) => e.source?.postMessage({ type: 'artgame:calc-done', ok, text }, location.origin))
    }
    const esc = e => { if (e.key === 'Escape') close() }
    window.addEventListener('message', on); window.addEventListener('keydown', esc)
    const ov = document.body.style.overflow; document.body.style.overflow = 'hidden'
    return () => { window.removeEventListener('message', on); window.removeEventListener('keydown', esc); document.body.style.overflow = ov }
  }, [onDoc, onCalc, dealId, close])
  const [src] = useState(() => {
    try { localStorage.setItem('artgame.bx.open', JSON.stringify({ id: dealId, view: 'deal', kp, ds, calc, t: Date.now() })) } catch { /* без памяти */ }
    return place ? `${place.url}?mode=tools&dark=1#${view || 'calc'}` : ''
  })
  const fr = useRef(null)
  useEffect(() => { fr.current?.contentWindow?.postMessage({ type: 'artgame:deal-data', id: dealId, kp, ds }, location.origin) }, [kp, ds, dealId])
  return <div className="toolsov" role="dialog" aria-label="Расчёт и КП">
    <div className="toolsbar">
      <button className="ghost mini" onClick={close}>← В сделку</button>
      <b>{title}</b>
      {bar}
    </div>
    {place ? <iframe ref={fr} title="Расчёт и КП" src={src} /> : <p className="muted">Рабочее место МОП недоступно для вашей роли.</p>}
  </div>
}

