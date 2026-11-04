import React, { useEffect, useState } from 'react'
import { api } from './api.js'
import { enqueue } from './queue.js'
import { shrink } from './work.jsx'

const KIND = { photo: 'Фото', design: 'Дизайн', doc: 'Документы' }
const DOC_ROLES = new Set(['head', 'mop', 'mop_vip', 'lead_artist', 'print_master', 'lead_designer'])
const size = b => b > 1e6 ? (b / 1e6).toFixed(1) + ' МБ' : Math.ceil(b / 1e3) + ' КБ'

// Большой файл грузится с телефона прямо в Google; сервер только выдаёт ссылку и проверяет результат.
function uploadBig(objectId, kind, file, onProgress) {
  return api(`/objects/${objectId}/uploads`, { method: 'POST',
    body: { client_uid: crypto.randomUUID(), kind, name: file.name, mime: file.type || 'application/octet-stream', size: file.size } })
    .then(r => r.done ? r : new Promise((ok, fail) => {
      const x = new XMLHttpRequest()
      x.open('PUT', r.upload_url)
      x.upload.onprogress = e => onProgress(e.loaded / e.total)
      x.onload = () => x.status < 300 ? ok(JSON.parse(x.responseText)) : fail(new Error('Google ' + x.status))
      x.onerror = () => fail(new Error('нет сети'))
      x.send(file)
    }).then(g => api(`/files/${r.file_id}/done`, { method: 'POST', body: { drive_id: g.id } })))
}

function Files({ obj, me, back }) {
  const [kind, setKind] = useState('photo')
  const [list, setList] = useState(null)
  const [busy, setBusy] = useState('')
  const load = () => api(`/objects/${obj.id}/files?kind=${kind}`).then(setList, () => setList([]))
  useEffect(() => { setList(null); load() }, [kind])
  useEffect(() => { window.addEventListener('artgame:queue', load); return () => window.removeEventListener('artgame:queue', load) }, [kind])
  const kinds = Object.keys(KIND).filter(k => k !== 'doc' || DOC_ROLES.has(me.role_code))
  const canBig = kind === 'photo' || (kind === 'design' && (me.role_code === 'head' || me.zones.includes('design'))) || (kind === 'doc' && DOC_ROLES.has(me.role_code))

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

  return <>
    <div className="card">
      <a onClick={back}>← объекты</a>
      <h2>{obj.id ? `№${obj.id} · ` : ''}{obj.title}</h2>
      <div className="seg">{kinds.map(k => <button key={k} className={k === kind ? '' : 'ghost'} onClick={() => setKind(k)}>{KIND[k]}</button>)}</div>
      {kind === 'photo' && <label className="photo"><span>📷 Добавить фото</span>
        <input type="file" accept="image/*" multiple hidden onChange={e => e.target.files.length && addPhotos(e.target.files)} /></label>}
      {kind !== 'photo' && canBig && <label className="photo"><span>⬆ Загрузить файл</span>
        <input type="file" hidden onChange={e => e.target.files[0] && addBig(e.target.files[0])} /></label>}
      {busy && <p className="muted small">{busy}</p>}
    </div>
    <div className="card">
      {!list ? <p className="muted">Загрузка…</p> : !list.length ? <p className="muted">Пока пусто</p> :
        kind === 'photo'
          ? <div className="grid">{list.map(f => <a key={f.id} href={f.url} target="_blank" rel="noreferrer"><img src={f.thumb} alt={f.name} loading="lazy" /></a>)}</div>
          : list.map(f => <div key={f.id} className="row">
              <div><a href={f.url} target="_blank" rel="noreferrer"><b>{f.name}</b></a><br />
                <span className="muted small">{size(f.size)} · {f.by} · {new Date(f.created_at).toLocaleDateString('ru-RU')}</span></div>
            </div>)}
    </div>
  </>
}

export function Objects({ me }) {
  const [list, setList] = useState(null)
  const [open, setOpen] = useState(null)
  useEffect(() => { api('/objects').then(setList, () => setList([])) }, [])
  if (open) return <Files obj={open} me={me} back={() => setOpen(null)} />
  return <div className="card"><h2>Объекты</h2>
    {!list ? <p className="muted">Загрузка…</p> : list.map(o => <div key={o.id} className="row" onClick={() => setOpen(o)} style={{ cursor: 'pointer' }}>
      <div><b>{o.id ? `№${o.id} · ` : ''}{o.title}</b>{o.city && <span className="muted"> — {o.city}</span>}<br />
        <span className="muted small">фото {o.photos} · дизайн {o.designs}</span></div>
      <span className="muted">›</span>
    </div>)}
  </div>
}
