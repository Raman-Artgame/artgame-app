// В Telegram — подпись initData; с компьютера — сессия по коду от бота (HEAD 06.11), хранится в браузере.
const initData = () => window.Telegram?.WebApp?.initData || ''
const KEY = 'artgame.web.token'
export const inTelegram = () => !!initData()
export const webToken = () => { try { return localStorage.getItem(KEY) || '' } catch { return '' } }
export const setWebToken = t => { try { t ? localStorage.setItem(KEY, t) : localStorage.removeItem(KEY) } catch { /* без памяти */ } }

// «Смотреть как сотрудник» (HEAD 08.11): кого смотрим — в памяти вкладки (закрыл приложение — снова сам).
// Заголовок X-View-As уходит с каждым запросом; сервер принимает его только от HEAD и закрывает любую запись.
const VKEY = 'artgame.viewas'
export const viewAs = () => { try { return sessionStorage.getItem(VKEY) || '' } catch { return '' } }
export const setViewAs = t => { try { t ? sessionStorage.setItem(VKEY, t) : sessionStorage.removeItem(VKEY) } catch { /* без памяти */ } }
// «Пройти как сотрудник» (только test): test:<роль> — запись открыта, всё уходит от тестового сотрудника.
export const testAs = () => viewAs().startsWith('test:')
export const RO_MSG = 'Режим просмотра: от имени сотрудника ничего не меняется.'
export const readOnlyHit = (msg = RO_MSG) => window.dispatchEvent(new CustomEvent('artgame:ro', { detail: msg }))

// Две роли (HEAD 08.11): «Я сейчас: …» — выбранная роль в памяти телефона, уходит заголовком X-Act-Role.
// Сервер принимает только свою дополнительную роль; смена сама запоминает, в какой роли она была.
const AKEY = 'artgame.act'
export const actRole = () => { try { return localStorage.getItem(AKEY) || '' } catch { return '' } }
export const setActRole = r => { try { r ? localStorage.setItem(AKEY, r) : localStorage.removeItem(AKEY) } catch { /* без памяти */ } }

// client_uid: crypto.randomUUID есть не во всех WebView Telegram (старый Android) — без него кнопки молча падали
export function uuid() {
  if (crypto.randomUUID) return crypto.randomUUID()
  const b = crypto.getRandomValues(new Uint8Array(16)); b[6] = (b[6] & 15) | 64; b[8] = (b[8] & 63) | 128
  const h = [...b].map(x => x.toString(16).padStart(2, '0')).join('')
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`
}

// Ошибка проверки полей (422) приходит списком — показываем по-русски, а не «[object Object]» (HEAD 09.11)
const FIELD = { hours: 'Часов', area_m2: 'Сделано, м²', work_done: 'Что сделал', day: 'Дата', amount: 'Сумма', object_id: 'Объект', photo_after: 'Фото' }
function errText(d) {
  if (!d || typeof d === 'string') return d
  if (!Array.isArray(d)) return d.message || JSON.stringify(d)
  return d.map(x => {
    const f = FIELD[x.loc?.[x.loc.length - 1]] || x.loc?.[x.loc.length - 1] || 'Поле'
    const c = x.ctx || {}
    if (x.type === 'less_than_equal') return `${f}: не больше ${c.le}`
    if (x.type === 'greater_than') return `${f}: больше ${c.gt}`
    if (x.type === 'greater_than_equal') return `${f}: не меньше ${c.ge}`
    if (x.type === 'string_too_short') return `${f}: слишком коротко`
    if (x.type === 'string_too_long') return `${f}: слишком длинно`
    if (x.type === 'missing') return `${f}: не заполнено`
    return `${f}: проверьте значение`
  }).join('. ')
}

export async function api(path, opts = {}) {
  const auth = initData() ? { 'X-Telegram-Init-Data': initData() } : webToken() ? { Authorization: `Bearer ${webToken()}` } : {}
  const va = !opts.noView && viewAs() ? { 'X-View-As': viewAs() } : actRole() ? { 'X-Act-Role': actRole() } : {}
  const r = await fetch(`/api${path}`, {
    ...opts,
    headers: { 'Content-Type': 'application/json', ...auth, ...va, ...(opts.headers || {}) },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  })
  const data = await r.json().catch(() => ({}))
  if (r.status === 401 && !initData() && webToken()) { setWebToken(''); window.dispatchEvent(new Event('artgame:logout')) }
  if (r.status === 403 && data.view_as) readOnlyHit(data.detail)
  if (!r.ok) throw Object.assign(new Error(errText(data.detail) || r.status), { status: r.status })
  return data
}
