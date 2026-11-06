/* ARTGAME: страница МОП внутри приложения (HEAD 06.11, единое рабочее место).
   Режимы (параметр ?mode= в адресе фрейма):
     study — вкладка «Учёба»: только учебник, тест, правила игры; рабочие вкладки (Расчёт, КП, Документы, Скрипты, Сделка, Клиентам) спрятаны.
     embed — панель внутри карточки сделки: без шапки, один раздел (#kp или #docs), сделка и расчёт подставлены сами.
   Данные для панели: localStorage 'artgame.bx.open' = {id, view: 'kp'|'docs', kp: позиция КП из расчёта, ds: {total, area}}.
   КП и «Документы» по-прежнему читают сделку через mcp (place_shim.js) и сообщают о скачанном файле (ARTGAME_ON_DOWNLOAD). */
(function () {
  var BX = window.ARTGAME_BX
  if (!BX) return
  var Q = {}
  location.search.replace(/[?&]([^=&]+)=([^&]*)/g, function (_, k, v) { Q[k] = decodeURIComponent(v) })
  var MODE = Q.mode || ''
  var deals = null, loading = null

  var css = document.createElement('style')
  css.textContent = '#kpgen fieldset:has(#dealId){display:block!important}' +
    '.agbx{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:8px 0 4px}' +
    '.agbx select{flex:1 1 240px;min-width:0;max-width:100%;padding:8px;font:inherit;border-radius:8px}' +
    '.agbx button{padding:8px 12px;font:inherit;border-radius:8px;cursor:pointer}' +
    '.agbx-st{font-size:.9em;opacity:.85;flex-basis:100%}' +
    (MODE === 'study' ? '#tabs .tab[data-v=calc],#tabs .tab[data-v=kp],#tabs .tab[data-v=docs],#tabs .tab[data-v=scripts],#tabs .tab[data-v=a],#tabs .tab[data-v=mat]{display:none!important}' +
      '.btns a[href="#calc"],.btns a[href="#kp"],.btns a[href="#docs"],.btns a[href="#scripts"],.btns a[href="#algo"],.btns a[href="#mat"]{display:none!important}' : '') +
    (MODE === 'embed' ? 'header.top,#vals-foot,#tabs{display:none!important}body{padding-top:0!important}.agbx{display:none!important}' : '')
  document.head.appendChild(css)

  // «Учёба»: рабочие разделы живут в карточке сделки — любой переход к ним ведёт в учебник
  var WORK = /^#?(calc|kp|docs|scripts|sc-.*|algo|amain|a\d\d|mat|search|q=.*)$/
  function guard() { if (MODE === 'study' && WORK.test(location.hash)) location.replace('#ucheb') }
  if (MODE === 'study') { window.addEventListener('hashchange', guard); if (!location.hash || location.hash === '#home') location.replace('#ucheb'); guard() }

  function money(n) { return n ? Math.round(n).toLocaleString('ru-RU') + ' ₸' : '' }
  function label(d) { return '№ ' + d.id + ' · ' + (d.title || '').slice(0, 60) + ' · ' + d.stage_name + (d.sum ? ' · ' + money(d.sum) : '') }
  function load(fresh) {
    if (!fresh && deals) return Promise.resolve(deals)
    if (!fresh && loading) return loading
    loading = BX('my_deals', { fresh: !!fresh }).then(function (r) { deals = r.deals || []; loading = null; return deals },
      function (e) { loading = null; throw e })
    return loading
  }
  function picker(onPick) {
    var box = document.createElement('div'); box.className = 'agbx'
    var sel = document.createElement('select')
    var upd = document.createElement('button'); upd.type = 'button'; upd.textContent = 'Обновить'; upd.className = 'btn ghost'
    var st = document.createElement('div'); st.className = 'agbx-st'
    box.appendChild(sel); box.appendChild(upd); box.appendChild(st)
    function fill(fresh) {
      sel.innerHTML = '<option value="">Мои сделки — загрузка…</option>'
      load(fresh).then(function (list) {
        sel.innerHTML = '<option value="">Мои сделки в Битриксе (' + list.length + ') — выберите</option>' +
          list.map(function (d) { return '<option value="' + d.id + '">' + label(d).replace(/</g, '&lt;') + '</option>' }).join('')
        if (!list.length) st.textContent = 'Открытых сделок, где вы ответственный, нет.'
      }, function (e) { sel.innerHTML = '<option value="">Сделки не загрузились</option>'; st.textContent = e.message })
    }
    sel.onchange = function () { if (sel.value) onPick(+sel.value, st) }
    upd.onclick = function () { fill(true) }
    fill(false)
    return box
  }

  /* ---- КП ---- */
  function kpPick(id) {
    var inp = document.getElementById('dealId'), btn = document.getElementById('loadBtn')
    if (!inp || !btn) return false
    inp.value = id; btn.click(); return true
  }
  // позиция из расчёта карточки → в КП, когда сделка подтянулась (генератор очищает список при загрузке клиента)
  function kpAdd(kp) {
    var tries = 0
    var t = setInterval(function () {
      var st = document.getElementById('crmStatus')
      if (!window.KPGEN || !st || !/загружена|не найден|ошибк/i.test(st.textContent || '')) { if (++tries > 80) clearInterval(t); return }
      clearInterval(t)
      try { if (!KPGEN.count()) KPGEN.add(kp, { service: kp.service, vat: kp.vat !== false }) } catch (e) { /* генератор другой версии */ }
    }, 250)
  }
  function mountKp() {
    var crm = document.querySelector('#kpgen .crm')
    if (!crm || crm.parentNode.querySelector('.agbx')) return
    crm.parentNode.insertBefore(picker(function (id) { kpPick(id) }), crm)
  }

  /* ---- Документы ---- */
  function docsFill(id, st, ds) {
    if (typeof DS === 'undefined') return
    st.textContent = 'Загружаю сделку ' + id + '…'
    BX('deal_card', { id: id }).then(function (c) {
      var got = []
      function put(k, v, what) { if (v !== undefined && v !== null && v !== '' && v !== 0) { DS[k] = v; if (what) got.push(what) } }
      put('num', String(c.id), 'номер')
      put('ctype', c.client.type)
      put('cname', c.client.name, 'клиент')
      put('ctel', c.client.phone, 'телефон')
      put('cmail', c.client.email, 'e-mail')
      if (c.client.type === 'Физлицо') put('signer', '')
      put('contact', c.contact)
      put('objAddr', [c.city, c.address].filter(Boolean).join(', '), 'адрес объекта')
      put('objName', c.object)
      if (!DS.area) put('area', c.area, 'площадь')
      if (!DS.total) put('total', c.sum, 'сумма')
      if (ds) {   // расчёт из карточки — источник цифр для договора и счёта
        if (ds.area) { DS.area = ds.area; got.push('площадь из расчёта') }
        if (ds.total) { DS.total = ds.total; DS.invSum = ds.prepay || ''; got.push('сумма из расчёта') }
        if (ds.adv) DS.adv = ds.adv
        if (ds.days && !DS.days) DS.days = ds.days
      }
      var rq = c.requisites || {}
      Object.keys(rq).forEach(function (k) { put(k, rq[k]) })
      if (Object.keys(rq).length) got.push('реквизиты')
      if (typeof dsSave === 'function') dsSave()
      if (typeof dsRerender === 'function') dsRerender()
      mountDocs()
      var miss = c.requisites === null && c.client.type !== 'Физлицо' ? ' Реквизиты (БИН, банк) вставьте из карточки клиента или анкеты.' : ''
      // анкета/переписка, вставленная в карточке сделки («Заполнить карточку») — разбираем тем же «Заполнить из текста»
      var ta = document.getElementById('ds-paste'), pb = document.getElementById('ds-parse')
      if (ds && ds.anketa && ta && pb) { ta.value = ds.anketa; ta.dispatchEvent(new Event('input', { bubbles: true })); pb.click(); got.push('анкета'); miss = '' }
      // «Заполнить из текста» перерисовывает форму — строку сделки и статус ставим заново
      var say = function () { mountDocs(); var s2 = document.querySelector('#app .agbx-st')
        if (s2) s2.textContent = 'Сделка ' + c.id + ' (' + c.stage_name + '): заполнено — ' + (got.join(', ') || 'ничего') + '. Проверьте поля.' + miss }
      say(); setTimeout(say, 400)
    }, function (e) { st.textContent = e.message })
  }
  function mountDocs() {
    var num = document.getElementById('ds-num')
    if (!num) return
    var row = num.closest('.frow')
    if (!row || (row.previousElementSibling && row.previousElementSibling.classList.contains('agbx'))) return
    row.parentNode.insertBefore(picker(docsFill), row)
  }

  /* ---- открыть сделку из карточки приложения ---- */
  function pending() {
    var o = null
    try { o = JSON.parse(localStorage.getItem('artgame.bx.open') || 'null'); localStorage.removeItem('artgame.bx.open') } catch (e) {}
    if (!o || !o.id || Date.now() - (o.t || 0) > 60000) return
    var tries = 0
    if (o.view === 'hash' && o.hash) {
      if (location.hash !== o.hash) location.hash = o.hash
    } else if (o.view === 'calc') {
      if (location.hash !== '#calc') location.hash = '#calc'
    } else if (o.view === 'kp') {
      if (location.hash !== '#kp') location.hash = '#kp'
      var t = setInterval(function () { if (kpPick(o.id) || ++tries > 40) { clearInterval(t); if (o.kp) kpAdd(o.kp) } }, 250)
    } else {
      if (location.hash !== '#docs') location.hash = '#docs'
      var t2 = setInterval(function () {
        if (typeof DS === 'undefined') { if (++tries > 40) clearInterval(t2); return }
        if (!DS.doc) { DS.doc = 'dogovor'; if (typeof dsSave === 'function') dsSave(); if (typeof dsRerender === 'function') dsRerender() }
        mountDocs()
        var st = document.querySelector('#app .agbx-st')
        if (st || ++tries > 40) { clearInterval(t2); if (st) docsFill(o.id, st, o.ds) }
      }, 250)
    }
  }

  /* ---- документ скачан → запись в сделку Битрикса (сервер, от имени МОП) ---- */
  function kpFields() {
    // позиции КП: массив генератора, если он его отдаёт, иначе — поля формы (#items — это div, не массив)
    var its = (typeof items !== 'undefined' && Array.isArray(items)) ? items : []
    if (!its.length) {
      var by = {}
      Array.prototype.forEach.call(document.querySelectorAll('#items [data-f][data-i]'), function (e) { (by[e.dataset.i] = by[e.dataset.i] || {})[e.dataset.f] = e.value })
      its = Object.keys(by).map(function (k) { return by[k] })
    }
    var total = 0, area = 0
    var level = '', service = 'mural', height = false
    its.forEach(function (i) { var q = +String(i.qty).replace(',', '.') || 0, pr = +String(i.price).replace(/\s/g, '') || 0; total += q * pr; if (!area) area = q
      var m = /(Лёгкий|Средний|Сложный|Авторский)/.exec(i.name || '') || /(Лёгкий|Средний|Сложный|Авторский)/.exec(i.sub || ''); if (m && !level) level = m[1]
      if (/печат/i.test(i.name || '')) service = 'print' })
    try { if (typeof S !== 'undefined' && S && S.paint) { level = level || S.paint.level; height = !!(S.ex && S.ex.height); if (S.tab === 'print') service = 'print' } } catch (e) { /* нет калькулятора */ }
    return { total: total, area: area, level: level, service: service, height: height }
  }
  window.ARTGAME_ON_DOWNLOAD = function (f) {
    var n = f.name || '', deal = 0, fields = {}, st = null
    if (/^КП /i.test(n)) {
      var el = document.getElementById('num'); deal = parseInt(el && el.value, 10) || 0; fields = kpFields(); st = document.getElementById('pdfStatus')
    } else if (/^ARTGAME_(Dogovor|Schet|AVR)/i.test(n) && typeof DS !== 'undefined') {
      deal = parseInt(DS.num, 10) || 0
      fields = { total: DS.total, area: DS.area, adv: DS.adv, days: DS.days, warr: DS.warr, objAddr: DS.objAddr, invSum: DS.invSum || DS.total }
      st = document.getElementById('dsst')
    }
    if (!deal) return
    BX('doc_saved', { deal: deal, name: n, fid: f.fid, fields: fields }).then(function (r) {
      try { if (window.parent !== window) window.parent.postMessage({ type: 'artgame:doc', deal: deal, name: n, bx: r.bx, stage: r.stage || null, held: r.held || null }, location.origin) } catch (e) {}
      if (!st) return
      var msg = r.bx === 'ok' ? ' Записано в сделку № ' + deal + (r.stage ? ', стадия обновлена.' : '.')
        : r.bx === 'off' ? ' В Битрикс не записано: ключ записи ещё не задан.' : r.bx === 'error' ? ' В Битрикс не записалось: ' + (r.error || '') : ''
      st.textContent = (st.textContent || '') + msg
    }, function (e) { if (st) st.textContent = (st.textContent || '') + ' В Битрикс не записалось: ' + e.message })
  }

  new MutationObserver(function () { mountKp(); mountDocs() }).observe(document.documentElement, { childList: true, subtree: true })
  mountKp(); mountDocs(); pending()
})()
