import React, { useEffect, useState } from 'react'

// Всплывающее окно (HEAD 06.11): лист снизу на телефоне, окно по центру на компьютере. Закрывается тапом по фону, ✕ и Esc.
export function Sheet({ title, onClose, children, wide }) {
  useEffect(() => {
    const k = e => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', k)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { window.removeEventListener('keydown', k); document.body.style.overflow = prev }
  }, [])
  return <div className="sheet" onClick={onClose}>
    <div className={'sheetbox modal' + (wide ? ' wide' : '')} onClick={e => e.stopPropagation()} role="dialog" aria-modal="true">
      <div className="mhead"><h2>{title}</h2><button className="x" aria-label="Закрыть" onClick={onClose}>✕</button></div>
      <div className="mbody">{children}</div>
    </div>
  </div>
}

// Кнопка «Скопировать»: копирует текст и на полторы секунды пишет «Скопировано».
export function Copy({ text, label = 'Скопировать', className = 'ghost mini' }) {
  const [ok, setOk] = useState('')
  const go = () => navigator.clipboard?.writeText(text).then(() => setOk('Скопировано'), () => setOk('Не удалось')).finally(() => setTimeout(() => setOk(''), 1500))
  return <button className={className} onClick={go}>{ok || label}</button>
}
