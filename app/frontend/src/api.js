// В Telegram — подпись initData; с компьютера — сессия по коду от бота (HEAD 06.11), хранится в браузере.
const initData = () => window.Telegram?.WebApp?.initData || ''
const KEY = 'artgame.web.token'
export const inTelegram = () => !!initData()
export const webToken = () => { try { return localStorage.getItem(KEY) || '' } catch { return '' } }
export const setWebToken = t => { try { t ? localStorage.setItem(KEY, t) : localStorage.removeItem(KEY) } catch { /* без памяти */ } }

export async function api(path, opts = {}) {
  const auth = initData() ? { 'X-Telegram-Init-Data': initData() } : webToken() ? { Authorization: `Bearer ${webToken()}` } : {}
  const r = await fetch(`/api${path}`, {
    ...opts,
    headers: { 'Content-Type': 'application/json', ...auth, ...(opts.headers || {}) },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  })
  const data = await r.json().catch(() => ({}))
  if (r.status === 401 && !initData() && webToken()) { setWebToken(''); window.dispatchEvent(new Event('artgame:logout')) }
  if (!r.ok) throw Object.assign(new Error(data.detail || r.status), { status: r.status })
  return data
}
