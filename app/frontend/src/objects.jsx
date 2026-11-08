import React, { useEffect, useState } from 'react'
import { api } from './api.js'
import { enqueue } from './queue.js'
import { shrink } from './work.jsx'

export const KIND = { design: 'Эскизы', photo: 'Фото', media: 'Продакшн', doc: 'Документы' }
const DOC_ROLES = new Set(['head', 'mop', 'mop_vip', 'lead_artist', 'print_master', 'lead_designer'])
const size = b => b > 1e6 ? (b / 1e6).toFixed(1) + ' МБ' : Math.ceil(b / 1e3) + ' КБ'

// Большой файл грузится с телефона прямо в Google; сервер только выдаёт ссылку и проверяет результат.
export function uploadBig(objectId, kind, file, onProgress, extra = {}) {
  return api(`/objects/${objectId}/uploads`, { method: 'POST',
    body: { client_uid: crypto.randomUUID(), kind, name: file.name, mime: file.type || 'application/octet-stream', size: file.size, ...extra } })
    .then(r => r.done ? r : new Promise((ok, fail) => {
      const x = new XMLHttpRequest()
      x.open('PUT', r.upload_url)
      x.upload.onprogress = e => onProgress(e.loaded / e.total)
      x.onload = () => x.status < 300 ? ok(JSON.parse(x.responseText)) : fail(new Error('Google ' + x.status))
      x.onerror = () => fail(new Error('нет сети'))
      x.send(file)
    }).then(g => api(`/files/${r.file_id}/done`, { method: 'POST', body: { drive_id: g.id } })))
}

// Галерея проекта (HEAD 08.11, «Проекты» и «Объекты» — один раздел): эскизы, фото с объекта, продакшн, документы.
export function Gallery({ obj, me, start = 'design' }) {
  const [kind, setKind] = useState(start)
  const [list, setList] = useState(null)
  const [busy, setBusy] = useState('')
  const load = () => (kind === 'media' ? api(`/media?scope=object&object_id=${obj.id}`).then(r => r.items) : api(`/objects/${obj.id}/files?kind=${kind}`))
    .then(setList, () => setList([]))
  useEffect(() => { setList(null); load() }, [kind])
  useEffect(() => { window.addEventListener('artgame:queue', load); return () => window.removeEventListener('artgame:queue', load) }, [kind])
  const kinds = Object.keys(KIND).filter(k => k !== 'doc' || DOC_ROLES.has(me.role_code))
  const canBig = (kind === 'design' && (me.role_code === 'head' || me.zones.includes('design'))) || (kind === 'doc' && DOC_ROLES.has(me.role_code))

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
  const addBig = async file => {
    try {
      await uploadBig(obj.id, kind, file, p => setBusy(`${file.name}: ${Math.round(p * 100)}%`))
      setBusy(''); load()
    } catch (e) { setBusy(`Не загрузилось: ${e.message}. Нужна сеть, попробуй ещё раз.`) }
  }
  const grid = kind === 'photo'   // фото — сеткой; эскизы, продакшн, документы — списком с названием
  const pics = list && (grid ? list.filter(f => f.thumb) : [])
  return <div className="card">
    <div className="segf">{kinds.map(k => <button key={k} className={k === kind ? 'on' : ''} onClick={() => setKind(k)}>{KIND[k]}</button>)}</div>
    {kind === 'photo' && <label className="photo"><span>📷 Добавить фото с объекта</span>
      <input type="file" accept="image/*" multiple hidden onChange={e => e.target.files.length && addPhotos(e.target.files)} /></label>}
    {canBig && <label className="photo"><span>⬆ Загрузить {kind === 'design' ? 'эскиз' : 'файл'}</span>
      <input type="file" hidden onChange={e => e.target.files[0] && addBig(e.target.files[0])} /></label>}
    {busy && <p className="muted small">{busy}</p>}
    {!list ? <p className="muted">Загрузка…</p> : !list.length ? <p className="muted small">{kind === 'design' ? 'Эскизов пока нет — их загружает дизайнер.' :
      kind === 'media' ? 'Утверждённого материала пока нет.' : 'Пока пусто.'}</p> : <>
      {pics.length > 0 && <div className="grid">{pics.map(f => <a key={f.id} href={f.url} target="_blank" rel="noreferrer"><img src={f.thumb} alt={f.name} loading="lazy" /></a>)}</div>}
      {list.filter(f => !grid || !f.thumb).map(f => <div key={f.id} className="mitem">
        <a className="mthumb" href={f.url} target="_blank" rel="noreferrer">{f.thumb ? <img src={f.thumb} alt="" loading="lazy" /> : <span>{f.media_type && f.media_type !== 'photo' ? '▶' : '📄'}</span>}</a>
        <div className="mbody"><a href={f.url} target="_blank" rel="noreferrer"><b>{f.media_type === 'reels' ? '🎬 ' : f.media_type === 'video' ? '▶ ' : ''}{f.name}</b></a><br />
          <span className="muted small">{size(f.size)} · {f.by} · {new Date(f.created_at).toLocaleDateString('ru-RU')}</span></div>
      </div>)}</>}
  </div>
}
