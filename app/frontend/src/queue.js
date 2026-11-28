// Офлайн-очередь: запись сохраняется на телефоне и уходит, когда появится сеть.
// client_uid не даёт серверу создать дубль при повторной отправке.
import { api, readOnlyHit, testAs, uuid, viewAs } from './api.js'
const KEY = 'artgame.queue.v1'
// HEAD 16.11 (проверка под нагрузку): очередь жила только в localStorage — это ~5 МБ, то есть 5–8 фото. На объекте без сети
// следующее фото не помещалось, сохранение молча падало, и запись пропадала даже из отправки. Теперь очередь — в памяти
// приложения (отправляется в любом случае) + в IndexedDB телефона (сотни МБ, переживает закрытие); localStorage — запасной.
let mem = (() => { try { return JSON.parse(localStorage.getItem(KEY) || '[]') } catch { return [] } })()
let full = false   // телефон не смог сохранить очередь: не закрывать приложение, пока не уйдёт
const idb = () => new Promise((ok, no) => {
  try { const r = indexedDB.open('artgame', 1); r.onupgradeneeded = () => r.result.createObjectStore('kv'); r.onsuccess = () => ok(r.result); r.onerror = () => no(r.error) } catch (e) { no(e) }
})
const idbDo = (mode, fn) => idb().then(d => new Promise((ok, no) => {
  const t = d.transaction('kv', mode); const r = fn(t.objectStore('kv')); t.oncomplete = () => ok(r && r.result); t.onerror = () => no(t.error)
}))
const load = () => mem
function save(q) {
  mem = q
  let ls = false
  try { localStorage.setItem(KEY, JSON.stringify(q)); ls = true } catch { /* не поместилось — держит IndexedDB */ }
  if (ls) { full = false; idbDo('readwrite', s => s.delete(KEY)).catch(() => {}); return Promise.resolve() }
  try { localStorage.removeItem(KEY) } catch {}
  return idbDo('readwrite', s => s.put(q, KEY)).then(() => { full = false }, () => { full = true })
}
// при запуске — то, что лежит в IndexedDB (большая очередь с прошлого раза)
const ready = idbDo('readonly', s => s.get(KEY)).then(q => {
  if (Array.isArray(q) && q.length) {
    const seen = new Set(mem.map(x => x.path + x.body.client_uid))
    mem = [...mem, ...q.filter(x => !seen.has(x.path + x.body.client_uid))]
    window.dispatchEvent(new Event('artgame:queue'))
  }
}, () => {})

export const pending = () => load().length
export const unsaved = () => full   // «Не закрывай приложение: телефон не сохранил очередь»
const FKEY = 'artgame.queue.failed'
export const failed = () => { try { return JSON.parse(localStorage.getItem(FKEY) || '[]') } catch { return [] } }
export const clearFailed = () => { try { localStorage.removeItem(FKEY) } catch {} }

export function enqueue(path, body) {
  // HEAD смотрит как сотрудник: в очередь не кладём, иначе после выхода запись ушла бы от имени HEAD
  if (viewAs() && !testAs()) { readOnlyHit(); return Promise.reject(Object.assign(new Error('read only'), { status: 403 })) }
  const q = load(); const item = { path, body: { client_uid: uuid(), ...body } }
  // та же запись уже ждёт в очереди (повторное нажатие) — второй раз не кладём
  if (!q.some(x => x.path === path && x.body.client_uid === item.body.client_uid)) save([...q, item])
  return flush()
}

let running = null
export function flush() {  // одна отправка за раз
  if (!running) running = doFlush().finally(() => { running = null; window.dispatchEvent(new Event('artgame:queue')) })
  return running
}

async function doFlush() {
  if (viewAs() && !testAs()) return load().length   // своё неотправленное HEAD отправит, когда вернётся к себе
  await ready
  let q = load()
  while (q.length) {
    try { await api(q[0].path, { method: 'POST', body: q[0].body }) }
    catch (e) {
      if (!e.status || e.status >= 500) break   // сеть/сервер — ждём
      // 4xx — сервер не принял: раньше пропадало молча (HEAD 08.11 «расход никуда не подгрузился») — теперь видно, почему
      const f = failed(); f.unshift({ path: q[0].path, amount: q[0].body.amount ?? null, note: q[0].body.note || '', error: e.message, at: Date.now() })
      try { localStorage.setItem(FKEY, JSON.stringify(f.slice(0, 20))) } catch {}
      window.dispatchEvent(new CustomEvent('artgame:dropped', { detail: e.message }))
    }
    const sent = q[0]
    q = load().filter(x => x !== sent); await save(q)   // пока отправляли, могли добавить новое — не затираем
  }
  return q.length
}

window.addEventListener('online', flush)
setInterval(() => { if (load().length) flush() }, 15000)  // повтор, если сеть «есть», но запрос не прошёл
