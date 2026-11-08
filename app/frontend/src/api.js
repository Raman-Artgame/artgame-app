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
export const RO_MSG = 'Режим просмотра: от имени сотрудника ничего не меняется.'
export const readOnlyHit = (msg = RO_MSG) => window.dispatchEvent(new CustomEvent('artgame:ro', { detail: msg }))

export async function api(path, opts = {}) {
  const auth = initData() ? { 'X-Telegram-Init-Data': initData() } : webToken() ? { Authorization: `Bearer ${webToken()}` } : {}
  const va = !opts.noView && viewAs() ? { 'X-View-As': viewAs() } : {}
  const r = await fetch(`/api${path}`, {
    ...opts,
    headers: { 'Content-Type': 'application/json', ...auth, ...va, ...(opts.headers || {}) },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  })
  const data = await r.json().catch(() => ({}))
  if (r.status === 401 && !initData() && webToken()) { setWebToken(''); window.dispatchEvent(new Event('artgame:logout')) }
  if (r.status === 403 && data.view_as) readOnlyHit(data.detail)
  if (!r.ok) throw Object.assign(new Error(data.detail || r.status), { status: r.status })
  return data
}
