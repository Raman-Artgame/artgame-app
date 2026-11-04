const initData = () => window.Telegram?.WebApp?.initData || ''

export async function api(path, opts = {}) {
  const r = await fetch(`/api${path}`, {
    ...opts,
    headers: { 'Content-Type': 'application/json', 'X-Telegram-Init-Data': initData(), ...(opts.headers || {}) },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw Object.assign(new Error(data.detail || r.status), { status: r.status })
  return data
}
