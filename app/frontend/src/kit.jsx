import React, { useEffect, useMemo, useRef, useState } from 'react'
import { download } from './objects.jsx'
import { Sheet } from './ui.jsx'

// «Пак элементов» (HEAD 14.11): рабочий набор бренда прямо в приложении. Каждый элемент — скачать отдельно
// (в CapCut, монтаж, макет) или сразу поставить в редактор сторис. Файлы лежат в /kit (public/kit, список — kit.json).
// Цен в паке нет: плашки цен из артефакта не перенесены, цены — только из «Значений».
const KIT = '/kit/'
let cache = null
export const loadKit = () => cache || (cache = fetch(KIT + 'kit.json').then(r => { if (!r.ok) throw new Error('пак не загрузился'); return r.json() }).catch(e => { cache = null; throw e }))
const fsize = b => b > 1e6 ? (b / 1e6).toFixed(1) + ' МБ' : Math.ceil(b / 1e3) + ' КБ'
const thumb = x => `${KIT}t/${x.g}/${x.id}.webp`
const ext = x => x.f.split('.').pop()
const save = x => download({ url: KIT + x.f, name: `artgame_${x.id}.${ext(x)}` })
const IN_STORY = ['t_logo', 't_stickers', 't_tags', 't_story', 't_cards', 't_bands', 't_video']   // что можно поставить на сторис

export function Kit({ onBack, canPost, onPublish }) {
  const [kit, setKit] = useState(null)
  const [g, setG] = useState('t_stickers')
  const [one, setOne] = useState(null)
  const [story, setStory] = useState(null)   // null | {} | {add: элемент} | {frame: рамка}
  useEffect(() => { loadKit().then(setKit, e => setKit({ err: e.message, groups: [], items: [] })) }, [])
  const items = useMemo(() => (kit?.items || []).filter(x => x.g === g), [kit, g])
  const subs = useMemo(() => [...new Set(items.map(x => x.sub))], [items])
  if (story) return <StoryEditor kit={kit} start={story} canPost={canPost} onPublish={onPublish} onClose={() => setStory(null)} />
  return <div className="card">
    <div className="mktcrumbs"><button className="ghost mini" onClick={onBack}>‹ Бренд</button><span>Пак элементов</span></div>
    <button disabled={!kit || !!kit.err} onClick={() => setStory({})}>Собрать сторис</button>
    <p className="small muted">Фото, рамка дизайнера, стикеры и текст. Готовую сторис можно скачать или сразу отправить на утверждение.</p>
    {!kit ? <p className="muted">Загрузка…</p> : kit.err ? <p className="small why">{kit.err}</p> : <>
      <div className="kitnav">{kit.groups.map(x => <button key={x.key} className={'ghost mini' + (g === x.key ? ' on' : '')} onClick={() => setG(x.key)}>{x.title}<i>{x.n}</i></button>)}</div>
      {subs.map(s => <React.Fragment key={s}>
        {s && <h4 className="kitsub">{s}</h4>}
        <div className="kitgrid">{items.filter(x => x.sub === s).map(x => <button key={x.id} className={'kittile ' + x.bg} onClick={() => setOne(x)}>
          <img src={thumb(x)} alt="" loading="lazy" /><span>{x.title}</span></button>)}</div>
      </React.Fragment>)}
    </>}
    {one && <Sheet title={one.title} onClose={() => setOne(null)}>
      <div className={'kitbig ' + one.bg}><img src={KIT + one.f} alt="" /></div>
      <p className="small">{one.use}</p>
      <p className="small muted">{one.w}×{one.h} · {ext(one).toUpperCase()}{one.alpha ? ', прозрачный фон' : ''} · {fsize(one.size)}</p>
      <button onClick={() => save(one)}>⬇ Скачать</button>
      {IN_STORY.includes(one.g) && <button className="ghost" onClick={() => { setStory({ add: one }); setOne(null) }}>Поставить на сторис</button>}
      {one.g === 's_stories' && <button className="ghost" onClick={() => { setStory({ frame: one }); setOne(null) }}>Собрать сторис в этой рамке</button>}
    </Sheet>}
  </div>
}

// ---------- Редактор сторис: 1080×1920, слои снизу вверх — фон или фото, рамка, элементы и текст ----------
const W = 1080, H = 1920
const FONTS = { compacta: ['Заголовок', '"AG Compacta", Impact, sans-serif'], onest: ['Текст', 'Onest, system-ui, sans-serif'], script: ['Рукопись', '"AG Studio Script", cursive'] }
const COLORS = ['#FFFFFF', '#0D0B0C', '#E60041']
const loadImg = src => new Promise((ok, fail) => { const i = new Image(); i.onload = () => ok(i); i.onerror = () => fail(new Error('картинка не загрузилась')); i.src = src })
let seq = 1

export function StoryEditor({ kit, start, canPost, onPublish, onClose }) {
  const [photo, setPhoto] = useState(null)        // {src, w, h, x, y, s}
  const [frame, setFrame] = useState(start.frame || null)
  const [bg, setBg] = useState(null)
  const [first] = useState(() => start.add ? mk(start.add) : null)
  const [layers, setLayers] = useState(first ? [first] : [])
  const [sel, setSel] = useState(first ? first.id : null)   // id слоя | 'photo'
  const [pick, setPick] = useState(null)          // 'frame' | 'el' | 'bg'
  const [grid, setGrid] = useState(false)
  const [out, setOut] = useState(null)            // {url, file}
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const [k, setK] = useState(0.3)
  const drag = useRef(null)
  const fileIn = useRef(null)
  const cur = layers.find(l => l.id === sel)
  const tools = cur?.type === 'text' ? 420 : cur || sel === 'photo' ? 300 : 230   // место под панель внизу: холст сжимается, кнопки не уезжают
  useEffect(() => {
    const fit = () => setK(Math.min((innerWidth - 24) / W, (innerHeight - tools) / H))
    fit(); addEventListener('resize', fit)
    return () => removeEventListener('resize', fit)
  }, [tools])
  useEffect(() => { const prev = document.body.style.overflow; document.body.style.overflow = 'hidden'; return () => { document.body.style.overflow = prev } }, [])
  const upd = (id, p) => setLayers(ls => ls.map(l => l.id === id ? { ...l, ...p } : l))
  const stickers = layers.filter(l => l.item?.g === 't_stickers').length

  function mk(item) { const w = Math.min(item.w, item.g === 't_stickers' ? 360 : 760); return { id: seq++, type: 'img', item, x: W / 2, y: H / 2, w, r: 0 } }
  const addEl = item => { const l = mk(item); setLayers(ls => [...ls, l]); setSel(l.id); setPick(null) }
  const addText = () => { const l = { id: seq++, type: 'text', text: 'ТЕКСТ', font: 'compacta', color: '#FFFFFF', size: 170, x: W / 2, y: 620, r: 0 }; setLayers(ls => [...ls, l]); setSel(l.id) }
  const onFile = async e => {
    const f = e.target.files?.[0]; e.target.value = ''
    if (!f) return
    if (!f.type.startsWith('image/')) return setMsg('Нужно фото. Видео в рамку ставится в монтаже: скачай рамку отдельно.')
    const src = URL.createObjectURL(f)
    try { const i = await loadImg(src); setPhoto({ src, w: i.naturalWidth, h: i.naturalHeight, x: 0, y: 0, s: 1 }); setBg(null); setSel('photo'); setMsg('') } catch (ex) { setMsg(ex.message) }
  }
  const cover = p => { const c = Math.max(W / p.w, H / p.h) * p.s; return { w: p.w * c, h: p.h * c } }

  const down = (e, id) => {
    e.stopPropagation(); setSel(id)
    const t = id === 'photo' ? photo : layers.find(l => l.id === id)
    drag.current = { id, px: e.clientX, py: e.clientY, x: t.x, y: t.y }
    e.currentTarget.setPointerCapture?.(e.pointerId)
  }
  const move = e => {
    const d = drag.current; if (!d) return
    const x = d.x + (e.clientX - d.px) / k, y = d.y + (e.clientY - d.py) / k
    d.id === 'photo' ? setPhoto(p => ({ ...p, x, y })) : upd(d.id, { x, y })
  }
  const up = () => { drag.current = null }
  const order = dir => setLayers(ls => { const i = ls.findIndex(l => l.id === sel), j = i + dir; if (i < 0 || j < 0 || j >= ls.length) return ls; const n = [...ls];[n[i], n[j]] = [n[j], n[i]]; return n })

  const render = async () => {
    setBusy(true); setMsg('')
    try {
      await Promise.all(Object.values(FONTS).map(f => document.fonts?.load(`100px ${f[1]}`)))
      const c = document.createElement('canvas'); c.width = W; c.height = H
      const x = c.getContext('2d')
      x.fillStyle = '#0D0B0C'; x.fillRect(0, 0, W, H)
      if (bg) x.drawImage(await loadImg(KIT + bg.f), 0, 0, W, H)
      if (photo) { const s = cover(photo); x.drawImage(await loadImg(photo.src), (W - s.w) / 2 + photo.x, (H - s.h) / 2 + photo.y, s.w, s.h) }
      if (frame) x.drawImage(await loadImg(KIT + frame.f), 0, 0, W, H)
      for (const l of layers) {
        x.save(); x.translate(l.x, l.y); x.rotate(l.r * Math.PI / 180)
        if (l.type === 'img') { const h = l.w * l.item.h / l.item.w; x.drawImage(await loadImg(KIT + l.item.f), -l.w / 2, -h / 2, l.w, h) } else {
          x.font = `${l.font === 'onest' ? '700 ' : ''}${l.size}px ${FONTS[l.font][1]}`; x.textAlign = 'center'; x.textBaseline = 'middle'; x.fillStyle = l.color
          const lines = l.text.split('\n'), lh = l.size * 1.05
          lines.forEach((t, i) => { const y = (i - (lines.length - 1) / 2) * lh
            if (l.font === 'script') { x.lineWidth = l.size / 9; x.lineJoin = 'round'; x.strokeStyle = l.color === '#0D0B0C' ? '#FFFFFF' : '#0D0B0C'; x.strokeText(t, 0, y) }
            x.fillText(t, 0, y) })
        }
        x.restore()
      }
      const blob = await new Promise(ok => c.toBlob(ok, 'image/png'))
      const d = new Date(), p = n => String(n).padStart(2, '0')
      const file = new File([blob], `artgame_story_${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}.png`, { type: 'image/png' })
      setOut({ url: URL.createObjectURL(blob), file }); setSel(null)
    } catch (ex) { setMsg(ex.message) }
    setBusy(false)
  }
  const send = async how => {
    setBusy(true); setMsg('')
    try { await onPublish(out.file, how); if (how === 'post') onClose() } catch (ex) {
      if (how === 'save') { const a = document.createElement('a'); a.href = out.url; a.download = out.file.name; document.body.appendChild(a); a.click(); a.remove() } else setMsg(ex.message)
    }
    setBusy(false)
  }

  const list = pick === 'frame' ? kit.items.filter(x => x.g === 's_stories') : pick === 'bg' ? kit.items.filter(x => x.g === 't_bg' && x.id.endsWith('9x16')) : []
  return <div className="storyed" onPointerMove={move} onPointerUp={up} onPointerCancel={up}>
    <div className="storytop"><button className="ghost mini" onClick={onClose}>‹ Закрыть</button><b>Сторис</b>
      <button className="mini" disabled={busy} onClick={render}>{busy ? '…' : 'Готово'}</button></div>
    <div className="storystage" style={{ width: W * k, height: H * k }} onPointerDown={() => setSel(null)}>
      <div className="storycanvas" style={{ width: W, height: H, transform: `scale(${k})` }}>
        {bg && <img className="full" src={KIT + bg.f} alt="" draggable={false} />}
        {photo && (() => { const s = cover(photo); return <img className={'ph' + (sel === 'photo' ? ' sel' : '')} src={photo.src} alt="" draggable={false} onPointerDown={e => down(e, 'photo')}
          style={{ width: s.w, height: s.h, left: (W - s.w) / 2 + photo.x, top: (H - s.h) / 2 + photo.y }} /> })()}
        {!bg && !photo && <div className="storyhint" onPointerDown={e => e.stopPropagation()} onClick={() => fileIn.current.click()}>Нажми, чтобы выбрать фото</div>}
        {frame && <img className="full pass" src={KIT + frame.f} alt="" draggable={false} />}
        {layers.map(l => l.type === 'img'
          ? <img key={l.id} className={'ly' + (sel === l.id ? ' sel' : '')} src={KIT + l.item.f} alt="" draggable={false} onPointerDown={e => down(e, l.id)}
            style={{ left: l.x, top: l.y, width: l.w, transform: `translate(-50%,-50%) rotate(${l.r}deg)` }} />
          : <div key={l.id} className={'ly tx ' + l.font + (sel === l.id ? ' sel' : '')} onPointerDown={e => down(e, l.id)}
            style={{ left: l.x, top: l.y, fontSize: l.size, color: l.color, fontFamily: FONTS[l.font][1], transform: `translate(-50%,-50%) rotate(${l.r}deg)`,
              WebkitTextStroke: l.font === 'script' ? `${l.size / 18}px ${l.color === '#0D0B0C' ? '#fff' : '#0D0B0C'}` : undefined }}>{l.text}</div>)}
        {grid && <img className="full pass" src={KIT + 'x_guides/safe_reels_9x16.png'} alt="" />}
      </div>
    </div>
    {msg && <p className="small why storymsg">{msg}</p>}
    {stickers > 3 && <p className="small why storymsg">По книге бренда: до трёх стикеров на кадр. Сейчас {stickers}.</p>}
    <div className="storytools">
      {cur ? <>
        {cur.type === 'text' && <><textarea rows={2} value={cur.text} onChange={e => upd(cur.id, { text: e.target.value })} />
          <div className="chips">{Object.entries(FONTS).map(([f, [t]]) => <button key={f} className={cur.font === f ? 'on' : ''} onClick={() => upd(cur.id, { font: f })}>{t}</button>)}
            {COLORS.map(c => <button key={c} aria-label={c} className={'stcol' + (cur.color === c ? ' on' : '')} style={{ background: c }} onClick={() => upd(cur.id, { color: c })} />)}</div></>}
        <label className="storyrng"><span>Размер</span>{cur.type === 'text'
          ? <input type="range" min="40" max="420" value={cur.size} onChange={e => upd(cur.id, { size: +e.target.value })} />
          : <input type="range" min="60" max="1600" value={cur.w} onChange={e => upd(cur.id, { w: +e.target.value })} />}</label>
        <label className="storyrng"><span>Поворот</span><input type="range" min="-180" max="180" value={cur.r} onChange={e => upd(cur.id, { r: +e.target.value })} /></label>
        <div className="seg"><button className="ghost mini" onClick={() => order(1)}>Выше</button><button className="ghost mini" onClick={() => order(-1)}>Ниже</button>
          <button className="ghost mini" onClick={() => { setLayers(ls => ls.filter(l => l.id !== sel)); setSel(null) }}>Убрать</button><button className="mini" onClick={() => setSel(null)}>Ок</button></div>
      </> : sel === 'photo' && photo ? <>
        <label className="storyrng"><span>Размер</span><input type="range" min="100" max="400" value={photo.s * 100} onChange={e => setPhoto(p => ({ ...p, s: +e.target.value / 100 }))} /></label>
        <p className="small muted">Двигай фото пальцем, чтобы работа попала в окно рамки.</p>
        <div className="seg"><button className="ghost mini" onClick={() => fileIn.current.click()}>Другое фото</button><button className="mini" onClick={() => setSel(null)}>Ок</button></div>
      </> : <div className="storybar">
        <button className="ghost" onClick={() => fileIn.current.click()}><i>▣</i>Фото</button>
        <button className="ghost" onClick={() => setPick('frame')}><i>▢</i>Рамка</button>
        <button className="ghost" onClick={() => setPick('el')}><i>★</i>Элемент</button>
        <button className="ghost" onClick={addText}><i>Аа</i>Текст</button>
        <button className="ghost" onClick={() => setPick('bg')}><i>▦</i>Фон</button>
        <button className={'ghost' + (grid ? ' on' : '')} onClick={() => setGrid(!grid)}><i>⌗</i>Зоны</button>
      </div>}
    </div>
    <input ref={fileIn} type="file" accept="image/*" hidden onChange={onFile} />
    {(pick === 'frame' || pick === 'bg') && <Sheet title={pick === 'frame' ? 'Рамка сторис' : 'Фон из пака'} onClose={() => setPick(null)}>
      <p className="small muted">{pick === 'frame' ? 'Рамки дизайнера. Фото встаёт под рамку, работа видна в окне.' : 'Фон вместо фото: под текст, анонс или акцию.'}</p>
      <div className="kitgrid three"><button className="kittile dark" onClick={() => { pick === 'frame' ? setFrame(null) : setBg(null); setPick(null) }}><span>{pick === 'frame' ? 'Без рамки' : 'Без фона'}</span></button>
        {list.map(x => <button key={x.id} className="kittile dark tall" onClick={() => { if (pick === 'frame') setFrame(x); else { setBg(x); setPhoto(null) } setPick(null) }}><img src={thumb(x)} alt="" loading="lazy" /><span>{x.title.replace('Сторис · ', '')}</span></button>)}</div>
    </Sheet>}
    {pick === 'el' && <ElPick kit={kit} onPick={addEl} onClose={() => setPick(null)} />}
    {out && <Sheet title="Сторис готова" onClose={() => setOut(null)}>
      <img className="storyout" src={out.url} alt="Готовая сторис" />
      {canPost && <button disabled={busy} onClick={() => send('post')}>В публикацию, на утверждение</button>}
      <button className="ghost" disabled={busy} onClick={() => send('save')}>⬇ Скачать картинку</button>
      <button className="ghost" onClick={() => setOut(null)}>Поправить ещё</button>
      {msg && <p className="small why">{msg}</p>}
    </Sheet>}
  </div>
}

function ElPick({ kit, onPick, onClose }) {
  const [g, setG] = useState('t_story')
  return <Sheet title="Элемент из пака" onClose={onClose}>
    <div className="kitnav">{kit.groups.filter(x => IN_STORY.includes(x.key)).map(x => <button key={x.key} className={'ghost mini' + (g === x.key ? ' on' : '')} onClick={() => setG(x.key)}>{x.title}</button>)}</div>
    <div className="kitgrid three">{kit.items.filter(x => x.g === g).map(x => <button key={x.id} className={'kittile ' + x.bg} onClick={() => onPick(x)}><img src={thumb(x)} alt="" loading="lazy" /><span>{x.title}</span></button>)}</div>
  </Sheet>
}
