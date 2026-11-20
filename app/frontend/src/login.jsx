import React, { useState } from 'react'
import { api, setWebToken } from './api.js'

// Вход с компьютера (HEAD 06.11): телефон или @ник из Telegram → бот присылает код → браузер помнит вход 30 дней.
export function Login({ onDone }) {
  const [who, setWho] = useState('')
  const [code, setCode] = useState('')
  const [sent, setSent] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const run = f => { setBusy(true); setErr(''); return f().catch(e => setErr(e.message)).finally(() => setBusy(false)) }
  const ask = () => run(() => api('/login/code', { method: 'POST', body: { who } }).then(r => setSent(r.text)))
  const go = () => run(() => api('/login/verify', { method: 'POST', body: { who, code } }).then(r => { setWebToken(r.token); onDone() }))
  return <div className="card login">
    <h1>ARTGAME</h1>
    <p className="muted">Вход с компьютера. Укажите телефон или ник Telegram, бот @artgame_team_bot пришлёт код.</p>
    <input value={who} onChange={e => { setWho(e.target.value); setSent('') }} placeholder="+7 700 000 00 00 или @ник" autoFocus disabled={busy}
      onKeyDown={e => e.key === 'Enter' && who.trim() && !sent && ask()} />
    {!sent && <button disabled={!who.trim() || busy} onClick={ask}>Получить код</button>}
    {sent && <>
      <p className="small muted">{sent}</p>
      <input value={code} onChange={e => setCode(e.target.value)} placeholder="Код из Telegram" inputMode="numeric" autoFocus maxLength={6}
        onKeyDown={e => e.key === 'Enter' && code.length === 6 && go()} />
      <button disabled={code.replace(/\D/g, '').length !== 6 || busy} onClick={go}>Войти</button>
      <button className="ghost" disabled={busy} onClick={ask}>Прислать код ещё раз</button>
    </>}
    {err && <p className="small" style={{ color: 'var(--hot)' }}>{err}</p>}
    <p className="small muted">Первый раз — откройте приложение в Telegram через бота на телефоне и дождитесь роли от HEAD. Иконку на рабочий стол: меню браузера → «Установить приложение».</p>
  </div>
}
