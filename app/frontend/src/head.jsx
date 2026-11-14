import React, { useEffect, useState } from 'react'
import { FeedbackInbox } from './feedback.jsx'
import { api, setViewAs, viewAs } from './api.js'
import { flush } from './queue.js'
import { money } from './crm.jsx'
import { LedgerForm } from './finance.jsx'
import { Spark, mln } from './charts.jsx'
import { closeAsks, useClosing } from './closing.jsx'

// Кабинет HEAD — «Пульт» (HEAD 08.11): сверху то, что ждёт решения, дальше деньги месяца, кто сегодня на объектах,
// команда и последние действия. Отсюда же — «Смотреть как сотрудник».
const tm = s => new Date(s).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
const ym = () => new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Almaty' }).slice(0, 7)
const ZONE = { mural: 'Роспись', print: 'Печать', design: 'Дизайн', sales: 'Продажи', marketing: 'Маркетинг' }

export function usePulse(on) {
  const [p, setP] = useState(null)
  useEffect(() => { if (on) api('/head/pulse').then(setP, () => setP(false)) }, [on])
  return p
}

export function Pulse({ me, pulse, go }) {
  const p = pulse
  const [fin, setFin] = useState(null)
  const [fb, setFb] = useState(null)   // обращения после ответа — заново с сервера
  const [year, setYear] = useState(null)
  const [kpi, setKpi] = useState(null)
  const [open, setOpen] = useState(null)   // HEAD 10.11: каждая плитка «Деньги» раскрывает расшифровку
  const [det, setDet] = useState({})
  const cl = useClosing(true)   // HEAD 12.11: сделки на закрытие и закрытые мимо паспорта — первыми
  const [spend, setSpend] = useState(null)   // «+ Расход» (HEAD 12.11): форма журнала денег прямо на Пульте
  const [spent, setSpent] = useState('')
  const openSpend = () => { setSpent(''); api('/fin/dict').then(setSpend, e => setSpent(e.message)) }
  const toggle = k => {
    setOpen(open === k ? null : k)
    if (open !== k && !['profit', 'lost'].includes(k) && !det[k])
      api(`/fin/kpi/${k}?ym=` + ym()).then(r => setDet(d => ({ ...d, [k]: r })), e => setDet(d => ({ ...d, [k]: { err: e.message } })))
  }
  useEffect(() => { api('/fin/summary?ym=' + ym()).then(setFin, e => setFin({ err: e.message })); api('/fin/year').then(setYear, () => {})
    api('/fin/kpi?ym=' + ym()).then(setKpi, () => {}) }, [])
  if (p === null) return <div className="card muted">Загрузка…</div>
  if (p === false) return <div className="card muted">Пульт не загрузился. Обновите страницу.</div>
  const r = p.review
  const asks = [...closeAsks(cl),
    r.shifts && { k: 'review', t: `Смены на утверждение: ${r.shifts}`, s: [r.rated_good ? `${r.rated_good} с оценкой 4–5★ — одним нажатием` : '',
      r.shifts_late ? `${r.shifts_late} дольше 2 суток` : ''].filter(Boolean).join(' · ') || 'в срок', hot: r.shifts_late },
    r.appeals && { k: 'review', t: `Обращения на правку: ${r.appeals}`, s: 'не внёс вовремя или ошибся — утвердить или отклонить' },
    r.expenses && { k: 'review', t: `Расходы на проверке: ${r.expenses}`, s: `на ${money(r.expenses_sum)}` + (r.over_cap ? ` · ${r.over_cap} выше потолка цены` : ''), hot: r.expenses_late || r.over_cap },
    r.payments && { k: 'review', t: `Оплаты клиентов на сверку: ${r.payments}`, s: `на ${money(r.payments_sum)} · сверить чек и выписку` },
    p.bills?.length && { k: 'fin:cash', t: `Оплатить сегодня: ${p.bills.length}`, s: p.bills.map(b => b.title + (b.amount ? ' ' + money(b.amount) : '')).join(' · '),
      hot: p.bills.some(b => b.status === 'overdue') },
    p.pending.length && { k: 'people', t: `Ждут роли: ${p.pending.length}`, s: p.pending.map(x => x.full_name).join(', '), hot: true },
    p.catalogs && { k: 'design:cat', t: `Каталоги дизайна на утверждение: ${p.catalogs}`, s: 'утвердить или вернуть' },
    p.dm?.unread && { k: 'chat', t: `Чат: новых ${p.dm.unread}`, s: `от ${p.dm.people} чел. · ответить`, hot: true },
    p.media && { k: 'prod', t: `Материал с объектов на утверждение: ${p.media}`, s: 'в «Продакшн» и рилс к оплате' },
    p.posts && { k: 'mkt', t: `Публикации на утверждение: ${p.posts}`, s: 'контент-план маркетинга — «Утверждаю» или «Вернуть»' },
  ].filter(Boolean)
  const curating = r.curating ? `Ещё ${r.curating} ждут оценки куратора (до 24 ч), потом придут сюда` : ''
  const name = (me.full_name || '').split(' ')[0]
  const active = p.team.reduce((n, t) => n + +t.active, 0)
  return <>
    <div className="card dark pulse-hero">
      <span className="muted small">{new Date().toLocaleDateString('ru-RU', { weekday: 'long', day: 'numeric', month: 'long' })}</span>
      <h1>{name ? `${name}, ` : ''}{asks.length ? 'ждёт решения' : 'всё решено'}</h1>
      <div className="pulse-kpi">
        <button className={r.shifts + r.expenses + (r.appeals || 0) + (r.payments || 0) ? 'hot' : ''} onClick={() => go('review')}><b>{r.shifts + r.expenses + (r.appeals || 0) + (r.payments || 0)}</b><span>на проверке</span></button>
        <button className={p.pending.length ? 'hot' : ''} onClick={() => go('people')}><b>{p.pending.length}</b><span>новых людей</span></button>
        <button onClick={() => document.getElementById('pulse-today')?.scrollIntoView({ behavior: 'smooth' })}><b>{p.today.length}</b><span>смен сегодня</span></button>
      </div>
    </div>

    <div className="card spendcard">{spend ? <><h3>Расход</h3>
      <LedgerForm d={spend} spend cancel={() => setSpend(null)} done={() => { setSpend(null); setSpent('Записано в «Деньги».') }} /></>
      : <><button onClick={openSpend}>+ Расход</button><p className="small muted">{spent || 'Аренда, коммуналка, покупка, своя трата — сумма, статья и чек. Чек ляжет в «06 РАСХОДЫ HEAD».'}</p></>}</div>
    {asks.length > 0 && <div className="card"><h3>Ждёт вашего решения</h3>
      {asks.map((a, i) => <div key={i} className={'qrow' + (a.red ? ' hot' : '')} onClick={() => go(a.k)}>
        <div className="qmain"><b>{a.t}</b><div className={'small ' + (a.hot ? 'why' : 'muted')}>{a.s}</div></div><span className="muted">›</span>
      </div>)}
      {curating && <p className="small muted">{curating}</p>}
    </div>}

    <div className="qrow card dmpulse" onClick={() => go('chat')}><div className="qmain"><b>📣 Написать команде</b>
      <div className="small muted">всем или по ролям — придёт в приложение и в бот; одному — только в приложение</div></div><span className="muted">›</span></div>

    <FeedbackInbox items={fb ?? p.feedback} reload={() => api('/head/pulse').then(x => setFb(x.feedback))} />

    <div className="card pulse-money"><div className="head"><h3>Деньги · {new Date().toLocaleDateString('ru-RU', { month: 'long' })}</h3>
      <span className="muted" role="button" onClick={() => go('fin')}>Финансы ›</span></div>
      {!fin ? <p className="small muted">Считаю…</p> : fin.err ? <p className="small muted">{fin.err}</p> : <>
        <div className="kpis">
          {[['revenue', 'Выручка с НДС', mln(fin.revenue?.gross), '', 'сдано в этом месяце'],
            ['profit', 'Прибыль до ИПН', mln(fin.profit), fin.profit < 0 ? 'neg' : 'pos', 'как посчитано'],
            ['cash_in', 'Пришло', mln(fin.cash?.in), '', fin.cash?.in_undated > 0 ? `без даты в сделке ${mln(fin.cash.in_undated)}` : 'оплаты клиентов'],
            ['lost', 'Упущенная выручка', kpi?.lost ? mln(kpi.lost.sum) : kpi?.bx_error ? '—' : '…', kpi?.lost?.sum ? 'neg' : '', kpi?.lost ? `проиграно: ${kpi.lost.count}` : ''],
            ['support', 'Ждут оплаты: саппорт', kpi ? mln(kpi.due_support) : '…', '', 'в понедельник'],
            ['expenses', 'Ждут оплаты: расходы', kpi ? mln(kpi.due_expenses) : '…', '', 'свои деньги, чеки'],
            ['debt', 'Долг клиентов', kpi?.debt ? mln(kpi.debt.sum) : kpi?.bx_error ? '—' : '…', '', kpi?.debt ? `по сданным: ${kpi.debt.count}` : ''],
            ['in_work', 'В работе', kpi?.in_work ? mln(kpi.in_work.sum) : kpi?.bx_error ? '—' : '…', '', kpi?.in_work ? `сделок на выполнении: ${kpi.in_work.count}` : '']]
            .map(([k, t, v, cls, sub]) => <div key={k} role="button" className={open === k ? 'on' : ''} onClick={() => toggle(k)}>
              <span>{t}</span><b className={cls}>{v}</b><small>{sub} {open === k ? '▴' : '›'}</small></div>)}
        </div>
        {open === 'profit' && <div className="profitwhy small">
          <div className="row"><span>Выручка без НДС</span><b>{mln(fin.revenue?.net)}</b></div>
          {[['payroll', 'ФОТ (смены, оклады, % МОП)'], ['fixed', 'Постоянные (аренда, подписки)'], ['variable', 'Переменные (реклама и пр.)'], ['project', 'Расходы проектов (чеки)'],
            ['stock', 'Закупки склада'], ['canvas', 'Мастерская холстов'], ['sales', 'Отдел продаж'], ['materials', 'Материалы (история)']]
            .filter(([k]) => fin.costs?.[k]).map(([k, t]) => <div key={k} className="row"><span>− {t}</span><b>{mln(fin.costs[k])}</b></div>)}
          <div className="row"><span>= Прибыль до ИПН</span><b>{mln(fin.profit)}</b></div>
          <p className="muted">Месяц идёт: выручка — только сданные проекты, расходы — всё, что уже начислено и одобрено.</p></div>}
        {open === 'lost' && kpi?.lost && <div className="profitwhy lostlist small">
          <b>Проиграно в этом месяце</b>
          {!kpi.lost.items?.length ? <p className="muted">Проигранных сделок нет.</p> : kpi.lost.items.map(x => <div key={x.id} className="row">
            <div><b>№{x.id} {x.title}</b><div className={x.reason ? '' : 'why'}>{x.reason || 'причина не указана'}</div>
              <div className="muted">{x.stage}{x.day ? ' · ' + new Date(x.day + 'T12:00').toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' }) : ''}{x.by_deal ? ' · «Упущено» пусто, взята сумма сделки' : ''}</div></div>
            <b className="nowrap">{x.amount ? mln(x.amount) : '—'}</b></div>)}
          <p className="muted">Причина — из поля причины отказа в сделке. Тестовые сделки не считаются.</p></div>}
        {open && !['profit', 'lost'].includes(open) && <div className="profitwhy lostlist small">
          {!det[open] ? <p className="muted">Загрузка…</p> : det[open].err ? <p className="why">{det[open].err}</p> : <>
            {!det[open].items.length && <p className="muted">Пусто.</p>}
            {det[open].items.map((x, i) => <div key={i} className="row">
              <div><b>{x.title}</b>{x.sub && <div className={x.warn ? 'why' : 'muted'}>{x.sub}</div>}
                {x.lines?.map((l, j) => <div key={j} className="muted">{l.t} · {money(l.amount)}{l.receipt_url && <> · <a href={l.receipt_url} target="_blank" rel="noreferrer">чек</a></>}</div>)}</div>
              <b className="nowrap">{mln(x.amount)}</b></div>)}
            <p className="muted">{det[open].note}</p>
            {['support', 'expenses'].includes(open) && <button className="mini" onClick={() => go('fin')}>К выплате в понедельник ›</button>}</>}
        </div>}
        {kpi?.bx_error && <p className="small muted">Битрикс не ответил — упущено, долг и «в работе» появятся позже.</p>}
        {year?.months?.length > 1 && <><Spark values={year.months.map(m => m.net)} /><p className="small muted">Выручка без НДС по месяцам {year.year}</p></>}
      </>}
    </div>

    <div className="card" id="pulse-today"><h3>Сегодня на объектах</h3>
      {!p.today.length ? <p className="small muted">Смен сегодня пока нет.</p> : p.today.map(s => <div key={s.id} className="row">
        <div><b>{s.full_name}</b> <span className="small muted">{s.role_title}</span>
          <div className="small muted">{s.object_title} · {ZONE[s.zone_code] || s.zone_code}</div></div>
        <span className="small">{tm(s.started_at)}{s.ended_at ? '–' + tm(s.ended_at) : ''}</span>
      </div>)}
      <p className="small muted">За 7 дней: смен {(+p.week.approved) + (+p.week.rejected)} проверено ({p.week.rejected} отклонено), работали {p.week.people} чел.</p>
    </div>

    <div className="card"><div className="head"><h3>Команда · {active}</h3><button className="ghost mini" onClick={() => go('people')}>Команда</button></div>
      <div className="teamgrid">{p.team.filter(t => +t.active).map(t => <div key={t.code}><b>{t.active}</b><span className="small muted">{t.title}</span></div>)}</div>
      {!active && <p className="small muted">Ролей ещё никому не назначено.</p>}
    </div>

  </>
}

// Посмотреть приложение глазами человека или роли. Только просмотр; вход и выход пишутся в журнал HEAD.
export function startViewAs(target) {
  return api('/view-as/start', { method: 'POST', body: { target: String(target) }, noView: true })
    .then(() => { setViewAs(String(target)); location.reload() })
}
export async function stopViewAs() {
  const t = viewAs()
  if (t.startsWith('test:')) await flush().catch(() => {})   // тест: отправить своё неотправленное от тестового сотрудника
  setViewAs('')
  return api('/view-as/stop', { method: 'POST', body: { target: t || '-' }, noView: true }).catch(() => {}).finally(() => location.reload())
}

export function ViewAsCard() {
  const [o, setO] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState('')
  useEffect(() => { api('/view-as/options', { noView: true }).then(setO, e => setErr(e.message)) }, [])
  const go = t => { setBusy(String(t)); startViewAs(t).catch(e => { setErr(e.message); setBusy('') }) }
  const people = (o?.people || []).filter(x => x.status !== 'blocked')
  return <div className="card viewas-card">
    <h3>Смотреть глазами сотрудника</h3>
    <p className="small muted">Приложение откроется так, как его видит человек: его меню, его сделки и смены. Только просмотр — ничего от его имени не отправится. Вход и выход — в вашем журнале.</p>
    {err && <p className="small why">{err}</p>}
    {!o ? <p className="small muted">Загрузка…</p> : <>
      {people.length ? people.map(x => <div key={x.id} className="row">
        <div><b>{x.full_name}</b> <span className="small muted">{x.role_title || (x.status === 'pending' ? 'ждёт роли' : '—')}</span></div>
        <button className="ghost mini" disabled={!!busy} onClick={() => go(x.id)}>{busy === String(x.id) ? 'Открываю…' : 'Смотреть'}</button>
      </div>) : <p className="small muted">В приложении пока никого, кроме вас.</p>}
      <p className="small muted" style={{ marginTop: 14 }}>Или роль целиком — меню и разделы роли на ваших данных (если человека ещё нет):</p>
      <div className="chips">{o.roles.map(r => <button key={r.code} className="ghost" disabled={!!busy} onClick={() => go('role:' + r.code)}>{r.title}</button>)}</div>
      {o.test && <div className="testas">
        <h3>Пройти как сотрудник · тест</h3>
        <p className="small muted">Здесь можно действовать: начать и закончить смену, загрузить фото, отправить расход. Всё идёт по-настоящему — в базу, на Диск в папку сделки, на проверку — от тестового сотрудника «Тест · роль». Только на test.</p>
        <div className="chips">{o.roles.map(r => <button key={r.code} disabled={!!busy} onClick={() => go('test:' + r.code)}>{r.title}</button>)}</div>
        <button className="ghost mini" disabled={!!busy} onClick={() => confirm('Удалить всех «Тест · …» и всё, что они сделали: смены, фото, расходы, записи журнала?') &&
          api('/view-as/purge', { method: 'POST', noView: true }).then(r => setErr(r.people ? `Удалено тестовых сотрудников: ${r.people} — со всеми сменами и расходами.` : 'Тестовых данных нет.'), e => setErr(e.message))}>
          Стереть тестовые данные</button>
        <p className="small muted">После теста нажмите — «Тест · …» исчезнет отовсюду: проверка, проекты, журнал, финансы.</p>
      </div>}
    </>}
  </div>
}

// Полоса сверху на всех экранах, пока HEAD смотрит чужими глазами: кто, что это только просмотр, выход одним нажатием.
export function ViewAsBar({ me, ROLE = {} }) {
  const v = me?._view_as
  const [msg, setMsg] = useState('')
  useEffect(() => {
    document.body.classList.toggle('viewas', !!v)
    const on = e => { setMsg(e.detail); setTimeout(() => setMsg(''), 3500) }
    window.addEventListener('artgame:ro', on)
    return () => window.removeEventListener('artgame:ro', on)
  }, [v])
  if (!v) return null
  return <div className="viewas-bar" role="status">
    <div className="vtext"><span className="eye">{v.kind === 'test' ? '🧪' : '👁'}</span><span>{v.kind === 'test' ? 'Тест: вы работаете как ' : 'Вы смотрите как '}<b>{me.full_name}</b>{v.kind === 'person' && me.role_code ? ` · ${ROLE[me.role_code] || me.role_code}` : ''}{v.note ? ` · ${v.note}` : ''}
      <i>{msg || (v.kind === 'test' ? 'всё сохраняется по-настоящему' : 'только просмотр')}</i></span></div>
    <button onClick={stopViewAs}>Вернуться к себе</button>
  </div>
}
