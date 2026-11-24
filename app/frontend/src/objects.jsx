import React, { useEffect, useRef, useState } from 'react'
import { api, uuid } from './api.js'
import { enqueue } from './queue.js'
import { shrink } from './work.jsx'
import { CamLabel } from './camera.jsx'

// Разделы проекта (HEAD 09.11: «что за что отвечает», плашка «Видео»)
export const KIND = { design: 'Эскизы', photo: 'Фото', video: 'Видео', media: 'Продакшн', doc: 'Документы' }
const ABOUT = {
  design: 'Эскизы от дизайнера — из папки сделки «ДИЗАЙН». Утверждённый — первым.',
  photo: 'Всё, что сняли на объекте: фото до и после из смен и добавленные вручную.',
  video: 'Видео с объекта: снятое на смене и загруженное в «Продакшн». Видят все на проекте.',
  media: 'Продакшн — лучшее, что HEAD утвердил для соцсетей и портфолио: фото, видео, рилс.',
  doc: 'Договор, счета, акты. Видят HEAD, МОП, Про и главные.' }
const PROD = new Set(['head', 'lead_artist', 'artist_pro', 'print_master'])
const DOC_ROLES = new Set(['head', 'mop', 'mop_vip', 'artist_pro', 'lead_artist', 'print_master', 'lead_designer'])
const size = b => b > 1e6 ? (b / 1e6).toFixed(1) + ' МБ' : Math.ceil(b / 1e3) + ' КБ'

// Большой файл грузится с телефона прямо в Google; сервер только выдаёт ссылку и проверяет результат.
// Большой файл — прямо в Google, частями (HEAD 24.11: «видео не загружаются»). Раньше файл шёл одним куском: на телефоне
// любой обрыв связи на видео в сотни мегабайт рвал загрузку целиком. Теперь части по 8 МБ: обрыв — ждём, спрашиваем у Google,
// сколько уже принято, и продолжаем с этого места (до 8 попыток подряд). Экран на время загрузки не гаснет, где это возможно.
const CHUNK = 8 * 1024 * 1024   // кратно 256 КБ — требование Google
const wait = ms => new Promise(r => setTimeout(r, ms))
const put = (url, body, headers = {}, onLoaded = null) => new Promise((ok, fail) => {
  const x = new XMLHttpRequest()
  x.open('PUT', url)
  for (const [k, v] of Object.entries(headers)) x.setRequestHeader(k, v)
  if (onLoaded) x.upload.onprogress = e => onLoaded(e.loaded)
  x.onload = () => ok(x)
  x.onerror = x.onabort = x.ontimeout = () => fail(new Error('нет сети'))
  x.send(body)
})
const accepted = (x, fallback) => { let r = null; try { r = x.getResponseHeader('Range') } catch { /* заголовок не отдан */ } const m = /-(\d+)$/.exec(r || ''); return m ? +m[1] + 1 : fallback }
export async function sendToGoogle(url, file, onProgress) {
  if (file.size <= CHUNK) {   // маленький файл — одним запросом, как раньше
    for (let t = 0; ; t++) {
      try {
        const x = await put(url, file, {}, n => onProgress(n / file.size))
        if (x.status < 300) return JSON.parse(x.responseText)
        if (x.status < 500 && x.status !== 429) throw Object.assign(new Error('Google ' + x.status), { fatal: true })
      } catch (e) { if (e.fatal || t >= 4) throw e }
      await wait(1500 * (t + 1))
    }
  }
  let off = 0, tries = 0
  for (;;) {
    const end = Math.min(file.size, off + CHUNK)
    let x = null
    try { x = await put(url, file.slice(off, end), { 'Content-Range': `bytes ${off}-${end - 1}/${file.size}` }, n => onProgress(Math.min(1, (off + n) / file.size))) } catch { /* обрыв — ниже */ }
    if (x && x.status < 300) return JSON.parse(x.responseText)
    if (x && x.status === 308) { off = accepted(x, end); tries = 0; continue }
    if (x && [400, 401, 403, 404, 410].includes(x.status)) throw new Error(x.status === 404 || x.status === 410 ? 'загрузка устарела — выбери файл ещё раз' : 'Google ' + x.status)
    if (++tries > 8) throw new Error('нет сети')
    await wait(Math.min(30000, 1000 * 2 ** tries))
    try {   // сколько Google уже принял
      const q = await put(url, null, { 'Content-Range': `bytes */${file.size}` })
      if (q.status < 300) return JSON.parse(q.responseText)
      if (q.status === 308) off = accepted(q, 0)
    } catch { /* сети всё ещё нет — следующая попытка */ }
  }
}
export function uploadBig(objectId, kind, file, onProgress, extra = {}) {
  let lock = null
  try { navigator.wakeLock?.request('screen').then(l => { lock = l }, () => {}) } catch { /* не поддерживается */ }
  return api(`/objects/${objectId}/uploads`, { method: 'POST',
    body: { client_uid: uuid(), kind, name: file.name, mime: file.type || 'application/octet-stream', size: file.size, ...extra } })
    .then(r => r.done ? r : sendToGoogle(r.upload_url, file, onProgress)
      .then(g => api(`/files/${r.file_id}/done`, { method: 'POST', body: { drive_id: g.id } })))
    .finally(() => { try { lock?.release() } catch { /* уже отпущен */ } })
}

const isVideo = f => (f.mime || '').startsWith('video/') || f.media_type === 'video' || f.media_type === 'reels'
const isImage = f => (f.mime || '').startsWith('image/')

// Скачать сразу (HEAD 09.11): в Telegram — его загрузкой, в браузере — файлом, без перехода на страницу
export function download(f) {
  const url = new URL(f.url + (f.url.includes('?') ? '&' : '?') + 'dl=1', location.href).href
  const tg = window.Telegram?.WebApp
  if (tg?.downloadFile && tg.isVersionAtLeast?.('8.0')) { try { tg.downloadFile({ url, file_name: f.name || 'file' }); return } catch { /* ниже — обычной ссылкой */ } }
  const a = document.createElement('a'); a.href = url; a.download = f.name || ''; document.body.appendChild(a); a.click(); a.remove()
}

// Просмотр внутри приложения: фото — крупно, видео — плеером, остальное — «Скачать»
// HEAD 18.11: «нормально сделать, чтобы можно было отчёты листать» — list + onNav: свайп влево/вправо, стрелки, счётчик «2 из 5»
export function Viewer({ f, onClose, extra = null, list = null, onNav = null }) {
  // тип не известен (ссылка из ленты, чек) — сначала картинкой, не вышло — видео, не вышло — карточка «Скачать»
  const [mode, setMode] = useState(null)
  const touch = useRef(null)
  useEffect(() => setMode(null), [f])
  const many = !!(f && onNav && list && list.length > 1)
  const i = many ? Math.max(0, list.findIndex(x => x === f || (x.url && x.url === f.url))) : 0
  const go = d => many && onNav(list[(i + d + list.length) % list.length])
  useEffect(() => {
    if (!f) return
    const k = e => { if (e.key === 'ArrowRight') go(1); else if (e.key === 'ArrowLeft') go(-1); else if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', k)
    if (many) [1, -1].forEach(d => { const x = list[(i + d + list.length) % list.length]; if (x && !isVideo(x)) new Image().src = x.url })   // соседние — заранее
    return () => document.removeEventListener('keydown', k)
  }, [f, list])
  if (!f) return null
  const m = mode || (isVideo(f) ? 'video' : isImage(f) || !f.mime ? 'img' : 'file')
  const ts = e => { touch.current = { x: e.touches[0].clientX, y: e.touches[0].clientY } }
  const te = e => {
    const t = touch.current; touch.current = null
    if (!t || !many) return
    const dx = e.changedTouches[0].clientX - t.x, dy = e.changedTouches[0].clientY - t.y
    if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy) * 1.3) go(dx < 0 ? 1 : -1)
  }
  return <div className="lightbox viewer" onClick={onClose} onTouchStart={ts} onTouchEnd={te}>
    {many && <div className="vcount" onClick={e => e.stopPropagation()}>{i + 1} из {list.length}</div>}
    {many && <button className="vnav prev" aria-label="Назад" onClick={e => { e.stopPropagation(); go(-1) }}>‹</button>}
    {many && <button className="vnav next" aria-label="Дальше" onClick={e => { e.stopPropagation(); go(1) }}>›</button>}
    <div className="vbox" onClick={e => e.stopPropagation()}>
      {m === 'video' ? <video src={f.url} controls playsInline autoPlay preload="metadata" onError={() => setMode('file')} /> :
        m === 'img' ? <img src={f.url} alt={f.name || ''} onError={() => setMode(f.mime ? 'file' : 'video')} /> : <div className="vfile">📄<b>{f.name || 'Файл'}</b></div>}
    </div>
    {f.name && <p>{f.name}{f.size ? ` · ${size(f.size)}` : ''}</p>}
    <div className="vbtns" onClick={e => e.stopPropagation()}>
      <button className="mini" onClick={() => download(f)}>⬇ Скачать</button>
      <button className="ghost mini" onClick={onClose}>Закрыть</button></div>
    {extra && <div className="vextra" onClick={e => e.stopPropagation()}>{extra}</div>}
  </div>
}

// Фото не с этого объекта (HEAD 14.11, 1611): HEAD переносит фото — одно или все фото этого человека за тот день — в нужный проект
function MoveFile({ f, from, onMoved }) {
  const [list, setList] = useState(null)
  const [to, setTo] = useState('')
  const [all, setAll] = useState(true)
  const [msg, setMsg] = useState('')
  if (!list) return <button className="ghost mini" onClick={() => api('/head/move-targets').then(r => setList(r.filter(o => o.id !== from)), e => setMsg(e.message))}>
    Не с этого объекта? Перенести{msg ? ' · ' + msg : ''}</button>
  const go = () => api(`/files/${f.id}/move`, { method: 'POST', body: { object_id: +to, same_day: all } })
    .then(r => { setMsg(`Перенесено в №${r.object_id} ${r.object_title}: ${r.files} фото.`); setTimeout(onMoved, 1200) }, e => setMsg(e.message))
  return <div className="moveshift">
    <select value={to} onChange={e => setTo(e.target.value)}><option value="">— в какой проект —</option>
      {list.map(o => <option key={o.id} value={o.id}>№{o.id} · {o.title}{o.city ? ` — ${o.city}` : ''}</option>)}</select>
    <label className="check"><input type="checkbox" checked={all} onChange={e => setAll(e.target.checked)} /> и все фото {f.by || 'этого человека'} за этот день</label>
    <button className="mini" disabled={!to} onClick={go}>Перенести</button>
    {msg && <p className="small">{msg}</p>}
  </div>
}

// Галерея проекта (HEAD 08.11, «Проекты» и «Объекты» — один раздел): эскизы, фото с объекта, видео, продакшн, документы.
// Миниатюра файла; не загрузилась (HEAD 22.11: у PNG эскизов был значок «?») — аккуратный значок с типом файла
function Thumb({ f }) {
  const [st, setSt] = useState('')   // '' — грузится, 'ok', 'bad'
  const ext = (f.name || '').split('.').pop()
  const badge = <span className={f.thumb ? 'mext' : ''}>{isVideo(f) ? '▶' : f.thumb && ext.length <= 4 ? ext.toUpperCase() : '📄'}</span>
  if (!f.thumb || st === 'bad') return badge
  // пока превью грузится (большой файл сервер готовит несколько секунд) — значок типа, а не пустой квадрат
  return <>{st !== 'ok' && badge}<img src={f.thumb} alt="" style={st === 'ok' ? null : { position: 'absolute', opacity: 0 }} onLoad={() => setSt('ok')} onError={() => setSt('bad')} /></>
}

export function Gallery({ obj, me, start = 'design', only, skip = [], bare = false, top = null }) {
  const [kind, setKind] = useState(start)
  const [list, setList] = useState(null)
  const [busy, setBusy] = useState('')
  const [open, setOpen] = useState(null)
  const load = () => (kind === 'media' ? api(`/media?scope=object&object_id=${obj.id}`).then(r => r.items) :
    kind === 'video' ? api(`/media?scope=object&type=video&object_id=${obj.id}`).then(r => r.items) : api(`/objects/${obj.id}/files?kind=${kind}`))
    .then(setList, () => setList([]))
  useEffect(() => { setList(null); load() }, [kind])
  useEffect(() => { window.addEventListener('artgame:queue', load); return () => window.removeEventListener('artgame:queue', load) }, [kind])
  const kinds = Object.keys(KIND).filter(k => (k !== 'doc' || DOC_ROLES.has(me.role_code)) && (!only || only.includes(k)) && !skip.includes(k))
  const canBig = (kind === 'design' && (me.role_code === 'head' || me.zones.includes('design'))) || (kind === 'doc' && DOC_ROLES.has(me.role_code))
  const canVideo = kind === 'video' && (PROD.has(me.role_code) || me.reels) && !me._view_as

  const addPhotos = async files => {
    setBusy(`Фото: 0 из ${files.length}`)
    let left = 0
    for (const [i, f] of [...files].entries()) {
      left = await enqueue(`/objects/${obj.id}/photos`, { data: await shrink(f) })
      setBusy(`Фото: ${i + 1} из ${files.length}`)
    }
    setBusy(left ? 'Фото сохранены на телефоне, отправятся, когда будет сеть.' : '')
    load()
  }
  const addBig = async (file, k = kind, extra = {}) => {
    try {
      await uploadBig(obj.id, k, file, p => setBusy(`${file.name}: ${Math.round(p * 100)}%`), extra)
      setBusy(k === 'media' ? 'Видео загружено — HEAD посмотрит и лучшее отправит в «Продакшн».' : ''); load()
    } catch (e) { setBusy(`Не загрузилось: ${e.message}. Нужна сеть, попробуй ещё раз.`) }
  }
  const grid = kind === 'photo'   // фото — сеткой; эскизы, видео, продакшн, документы — списком с названием
  const pics = list && (grid ? list.filter(f => f.thumb) : [])
  const empty = { design: 'Эскизов и файлов в печать пока нет — их загружает дизайнер.', video: 'Видео пока нет.', media: 'Утверждённого материала пока нет.' }
  return <div className={bare ? 'gbare' : 'card'}>
    {kinds.length > 1 && <div className="segf">{kinds.map(k => <button key={k} className={k === kind ? 'on' : ''} onClick={() => setKind(k)}>{KIND[k]}</button>)}</div>}
    {top}
    {!bare && <p className="small muted gabout">{ABOUT[kind]}</p>}
    {/* HEAD 16.11: на iPhone без capture — меню, на Samsung в Telegram — только галерея; поэтому две кнопки */}
    {kind === 'photo' && <div className="seg snapbtns"><CamLabel multi className="btnlike" onFiles={addPhotos}>📷 Снять фото с объекта</CamLabel>
      <label className="btnlike ghost">🖼 Из галереи
      <input type="file" accept="image/*" multiple hidden onChange={e => { const f = [...e.target.files]; e.target.value = ''; f.length && addPhotos(f) }} /></label></div>}
    {canBig && <label className="photo"><span>⬆ Загрузить {kind === 'design' ? 'эскиз или файл в печать' : 'файл'}</span>
      <input type="file" hidden onChange={e => e.target.files[0] && addBig(e.target.files[0])} /></label>}
    {canVideo && <label className="photo"><span>🎥 Загрузить видео с объекта</span>
      <input type="file" accept="video/*" hidden onChange={e => e.target.files[0] && addBig(e.target.files[0], 'media', { media_type: 'video' })} /></label>}
    {busy && <p className="muted small">{busy}</p>}
    {!list ? <p className="muted">Загрузка…</p> : !list.length ? <p className="muted small">{empty[kind] || 'Пока пусто.'}</p> : <>
      {pics.length > 0 && <div className="grid">{pics.map(f => <button key={f.id} className="gpic" onClick={() => setOpen(f)}><img src={f.thumb} alt={f.name} loading="lazy" /></button>)}</div>}
      {list.filter(f => !grid || !f.thumb).map(f => <div key={f.id} className="mitem">
        <button className="mthumb" onClick={() => setOpen(f)}><Thumb f={f} /></button>
        <div className="mbody"><a onClick={() => setOpen(f)}><b>{f.media_type === 'reels' ? '🎬 ' : f.media_type === 'video' ? '▶ ' : ''}{f.name}</b></a>{kind === 'design' && /утвержд/i.test(f.note || '') && <i className="okmark small"> ✓ утверждён</i>}<br />
          <span className="muted small">{f.size ? size(f.size) + ' · ' : ''}{f.by} · {new Date(f.created_at).toLocaleDateString('ru-RU')}{kind === 'video' && f.review === 'approved' ? ' · в Продакшн' : ''}</span></div>
        <button className="ghost mini" aria-label="Скачать" onClick={() => download(f)}>⬇</button>
      </div>)}</>}
    <Viewer f={open} onClose={() => setOpen(null)} list={pics && pics.length > 1 && pics.includes(open) ? pics : null} onNav={setOpen} extra={open && me.role_code === 'head' && !me._view_as && ['photo', 'video', 'media'].includes(kind)
      ? <MoveFile key={open.id} f={open} from={obj.id} onMoved={() => { setOpen(null); load() }} /> : null} />
  </div>
}

// Любая ссылка на файл приложения (/api/files/…/content) открывается здесь же, а не в браузере (HEAD 09.11)
export function FileLinks() {
  const [f, setF] = useState(null)
  const [list, setList] = useState(null)
  useEffect(() => {
    const isFile = a => /\/content\b/.test(a.getAttribute('href') || '')
    const item = a => ({ url: a.getAttribute('href'), name: a.getAttribute('title') || a.textContent.trim() || '' })
    const on = e => {
      const a = e.target.closest?.('a[href*="/api/files/"]')
      if (!a || !isFile(a) || e.defaultPrevented) return
      e.preventDefault()
      // фото отчёта листаются (HEAD 18.11): все фото-ссылки той же строки смены/проекта — до, после и доп. фото
      const box = a.querySelector('img') && a.closest('.row, .card')
      const links = box ? [...box.querySelectorAll('a[href*="/api/files/"]')].filter(x => isFile(x) && x.querySelector('img')) : []
      const all = links.length > 1 ? links.map(item) : null
      setList(all)
      setF(all ? all[links.indexOf(a)] : item(a))
    }
    document.addEventListener('click', on)
    return () => document.removeEventListener('click', on)
  }, [])
  return <Viewer f={f} list={list} onNav={setF} onClose={() => { setF(null); setList(null) }} />
}
