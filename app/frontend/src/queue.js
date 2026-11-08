// Офлайн-очередь: запись сохраняется на телефоне и уходит, когда появится сеть.
// client_uid не даёт серверу создать дубль при повторной отправке.
import { api, readOnlyHit, testAs, viewAs } from './api.js'
const KEY = 'artgame.queue.v1'
const load = () => { try { return JSON.parse(localStorage.getItem(KEY) || '[]') } catch { return [] } }
const save = q => { try { localStorage.setItem(KEY, JSON.stringify(q)) } catch {} }

export const pending = () => load().length
const FKEY = 'artgame.queue.failed'
export const failed = () => { try { return JSON.parse(localStorage.getItem(FKEY) || '[]') } catch { return [] } }
export const clearFailed = () => { try { localStorage.removeItem(FKEY) } catch {} }

export function enqueue(path, body) {
  // HEAD смотрит как сотрудник: в очередь не кладём, иначе после выхода запись ушла бы от имени HEAD
  if (viewAs() && !testAs()) { readOnlyHit(); return Promise.reject(Object.assign(new Error('read only'), { status: 403 })) }
  const q = load(); q.push({ path, body: { client_uid: crypto.randomUUID(), ...body } }); save(q)
  return flush()
}

let running = null
export function flush() {  // одна отправка за раз
  if (!running) running = doFlush().finally(() => { running = null; window.dispatchEvent(new Event('artgame:queue')) })
  return running
}

async function doFlush() {
  if (viewAs() && !testAs()) return load().length   // своё неотправленное HEAD отправит, когда вернётся к себе
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
    q = q.slice(1); save(q)
  }
  return q.length
}

window.addEventListener('online', flush)
setInterval(() => { if (load().length) flush() }, 15000)  // повтор, если сеть «есть», но запрос не прошёл
