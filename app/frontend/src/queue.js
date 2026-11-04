// Офлайн-очередь: запись сохраняется на телефоне и уходит, когда появится сеть.
// client_uid не даёт серверу создать дубль при повторной отправке.
import { api } from './api.js'
const KEY = 'artgame.queue.v1'
const load = () => { try { return JSON.parse(localStorage.getItem(KEY) || '[]') } catch { return [] } }
const save = q => { try { localStorage.setItem(KEY, JSON.stringify(q)) } catch {} }

export const pending = () => load().length

export function enqueue(path, body) {
  const q = load(); q.push({ path, body: { client_uid: crypto.randomUUID(), ...body } }); save(q)
  return flush()
}

let running = null
export function flush() {  // одна отправка за раз
  if (!running) running = doFlush().finally(() => { running = null; window.dispatchEvent(new Event('artgame:queue')) })
  return running
}

async function doFlush() {
  let q = load()
  while (q.length) {
    try { await api(q[0].path, { method: 'POST', body: q[0].body }) }
    catch (e) { if (!e.status || e.status >= 500) break; console.warn('drop', e) }  // сеть/сервер — ждём; 4xx — ошибка данных
    q = q.slice(1); save(q)
  }
  return q.length
}

window.addEventListener('online', flush)
setInterval(() => { if (load().length) flush() }, 15000)  // повтор, если сеть «есть», но запрос не прошёл
