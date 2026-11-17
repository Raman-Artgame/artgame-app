import React, { useEffect, useRef, useState } from 'react'

// HEAD 17.11: «У Лизы Самсунг, она не может сфоткать, может только фото добавить». На Android (Telegram и часть браузеров)
// атрибут capture игнорируется — открывается только галерея. Поэтому на Android «Камера» — своя камера в приложении
// (getUserMedia: видео с задней камеры → кадр в jpeg). Не дали доступ или камеры нет — кнопка «Открыть камеру телефона» (capture).
// На iPhone capture работает — там как было.
const ANDROID = typeof navigator !== 'undefined' && /Android/i.test(navigator.userAgent)
export const ownCamera = () => ANDROID && !!navigator.mediaDevices?.getUserMedia

const capIn = onFiles => <input type="file" accept="image/*" capture="environment" hidden
  onChange={e => { const f = [...e.target.files]; e.target.value = ''; f.length && onFiles(f) }} />

export function CamLabel({ multi, onFiles, className, children }) {
  const [open, setOpen] = useState(false)
  if (!ownCamera()) return <label className={className}>{children}{capIn(onFiles)}</label>
  return <>
    <button type="button" className={className} onClick={() => setOpen(true)}>{children}</button>
    {open && <Shooter multi={multi} onFiles={onFiles} close={() => setOpen(false)} />}
  </>
}

function Shooter({ multi, onFiles, close }) {
  const video = useRef(null)
  const [err, setErr] = useState('')
  const [shots, setShots] = useState([])   // [{file, url}]
  const [ready, setReady] = useState(false)
  useEffect(() => {
    let stream, gone = false
    navigator.mediaDevices.getUserMedia({ audio: false, video: { facingMode: { ideal: 'environment' }, width: { ideal: 2560 }, height: { ideal: 1440 } } })
      .then(s => {
        stream = s
        if (gone) return s.getTracks().forEach(t => t.stop())
        video.current.srcObject = s
        video.current.play().catch(() => {})
      })
      .catch(() => setErr('Нет доступа к камере.'))
    return () => { gone = true; stream && stream.getTracks().forEach(t => t.stop()) }
  }, [])
  const snap = () => {
    const v = video.current
    if (!v?.videoWidth) return
    const c = document.createElement('canvas')
    c.width = v.videoWidth; c.height = v.videoHeight
    c.getContext('2d').drawImage(v, 0, 0)
    c.toBlob(b => {
      if (!b) return
      const file = new File([b], `photo-${Date.now()}.jpg`, { type: 'image/jpeg' })
      if (!multi) { onFiles([file]); close(); return }
      setShots(a => [...a, { file, url: URL.createObjectURL(b) }])
    }, 'image/jpeg', 0.92)
  }
  const finish = () => { shots.length && onFiles(shots.map(x => x.file)); shots.forEach(x => URL.revokeObjectURL(x.url)); close() }
  return <div className="shooter" role="dialog">
    {err ? <div className="shooter-err">
      <p>{err} Разреши камеру для приложения или открой камеру телефона:</p>
      <label className="btnlike">📷 Открыть камеру телефона{capIn(f => { onFiles(f); close() })}</label>
      <button className="ghost" onClick={close}>Закрыть</button></div>
      : <video ref={video} playsInline muted autoPlay onLoadedMetadata={() => setReady(true)} onPlaying={() => setReady(true)} />}
    {!err && <>
      {shots.length > 0 && <div className="shooter-pics">{shots.map((x, i) => <img key={i} src={x.url} alt="" />)}</div>}
      <div className="shooter-bar">
        <button className="ghost" onClick={() => { shots.forEach(x => URL.revokeObjectURL(x.url)); close() }}>✕</button>
        <button className="shutter" aria-label="Снять" disabled={!ready} onClick={snap} style={{ background: "#fff" }} />
        {multi ? <button disabled={!shots.length} onClick={finish}>Готово{shots.length ? ` · ${shots.length}` : ''}</button> : <span className="shooter-gap" />}
      </div></>}
  </div>
}
