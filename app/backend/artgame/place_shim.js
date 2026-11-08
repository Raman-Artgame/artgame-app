/* ARTGAME: замена window.claude для рабочих мест внутри приложения.
   db → /api/p/<место>/<ссылка>/_db, downloads → файл через сервер (в Telegram — downloadFile),
   user.canEdit → редактор места. mcp → сделки Битрикса через сервер (только чтение, только свои сделки; места МОП и Калькулятор).
   sample (ИИ) и permissions пока нет — страница сама прячет эти кнопки. */
(function () {
  var P = window.ARTGAME_PLACE || {}
  var m = location.pathname.match(/^(\/api\/p\/[^/]+\/[^/]+)\//)
  var BASE = m ? m[1] : ''
  var POLL = 15000

  function req(u, o) {
    return fetch(BASE + u, o).then(function (r) {
      return r.json().catch(function () { return {} }).then(function (d) {
        if (!r.ok) { var e = new Error(d.detail || String(r.status)); e.code = r.status === 403 ? 'permission_denied' : 'unavailable'; throw e }
        return d
      })
    })
  }
  function snap(d) { return { id: d.id, exists: !!d.exists, data: function () { return d.data || undefined } } }
  function watch(load, cb, err) {
    var last = null, stop = false
    function tick() {
      if (stop) return
      load().then(function (d) { var s = JSON.stringify(d); if (s !== last) { last = s; cb(d) } }, function (e) { err && err(e) })
    }
    tick()
    var t = setInterval(tick, POLL)
    return function () { stop = true; clearInterval(t) }
  }
  function docRef(path) {
    var get = function () { return req('/_db/' + path) }
    return {
      id: path.split('/').pop(), path: path,
      get: function () { return get().then(snap) },
      set: function (data) {
        return req('/_db/' + path, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })
      },
      update: function (data) {
        return get().then(function (d) { return docRef(path).set(Object.assign({}, d.data || {}, data)) })
      },
      onSnapshot: function (cb, err) { return watch(get, function (d) { cb(snap(d)) }, err) },
    }
  }
  function colRef(name) {
    var list = function () { return req('/_db/' + name) }
    return {
      doc: function (id) { return docRef(name + '/' + (id || Math.random().toString(36).slice(2, 12))) },
      get: function () { return list().then(qs) },
      onSnapshot: function (cb, err) { return watch(list, function (d) { cb(qs(d)) }, err) },
    }
    function qs(d) {
      var docs = (d.docs || []).map(function (x) { return { id: x.id, exists: true, data: function () { return x.data } } })
      return { empty: !docs.length, size: docs.length, docs: docs, forEach: function (f) { docs.forEach(f) } }
    }
  }
  var db = { doc: docRef, collection: colRef }

  var downloads = {
    save: function (o) {
      var name = o.filename || 'file'
      var blob = o.data instanceof Blob ? o.data : new Blob([o.data])
      return fetch(BASE + '/_dl?name=' + encodeURIComponent(name), { method: 'POST', headers: { 'Content-Type': blob.type || 'application/octet-stream' }, body: blob })
        .then(function (r) { if (!r.ok) throw Object.assign(new Error('download'), { code: 'unavailable' }); return r.json() })
        .then(function (d) {
          try { if (window.ARTGAME_ON_DOWNLOAD) window.ARTGAME_ON_DOWNLOAD({ name: name, fid: d.url.split('/').pop() }) } catch (e) {}
          var url = location.origin + d.url
          var tg = null
          try { tg = window.parent && window.parent.Telegram && window.parent.Telegram.WebApp } catch (e) {}
          if (tg && tg.downloadFile && tg.isVersionAtLeast && tg.isVersionAtLeast('8.0')) {
            tg.downloadFile({ url: url, file_name: name })
            return { status: 'delivered' }
          }
          var a = document.createElement('a'); a.href = url; a.download = name
          document.body.appendChild(a); a.click(); a.remove()
          return { status: 'saved' }
        })
    },
  }
  var user = { canEdit: function () { return Promise.resolve(!!P.editor) } }
  // Битрикс: страница КП зовёт callTool(сервер, 'crm_get' | 'crm_fields', args) — отвечает наш сервер через шлюз ARTGAME.
  function bx(tool, args) {
    return fetch(BASE + '/_bx/' + tool, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(args || {}) })
      .then(function (r) {
        return r.json().catch(function () { return {} }).then(function (d) {
          if (!r.ok) { var e = new Error(d.detail || String(r.status)); e.code = r.status >= 500 ? 'upstream_error' : 'tool_error'; throw e }
          return d
        })
      })
  }
  var mcp = { callTool: function (server, tool, args) { return bx(tool, args).then(function (d) { return { structuredContent: d } }) } }
  window.ARTGAME_BX = bx
  var caps = { db: db, downloads: downloads, user: user }
  if (P.bx) caps.mcp = mcp
  window.claude = { use: function (n) { return Promise.resolve(caps[n] || null) } }

  // «Учёба» (HEAD 07.11): приложение открывает место с ?hide=pay,grow — эти разделы скрыты (вкладки, плитки, ссылки),
  // переход на скрытый раздел ведёт на ?home= (по умолчанию первый видимый). Страницу места не перепаковываем.
  var qp = new URLSearchParams(location.search)
  var HIDE = (qp.get('hide') || '').split(',').filter(function (x) { return /^[a-z]+$/.test(x) })
  if (HIDE.length) {
    var css = HIDE.map(function (h) { return 'a[href="#' + h + '"],a[href^="#' + h + '-"],[data-v="' + h + '"]' }).join(',') + '{display:none!important}'
    var st = document.createElement('style'); st.textContent = css
    document.head ? document.head.appendChild(st) : document.documentElement.appendChild(st)
    var HOME = /^[a-z]+$/.test(qp.get('home') || '') ? qp.get('home') : ''
    var guard = function () {
      var h = decodeURIComponent(location.hash.slice(1)).split(/[-=/]/)[0]
      if (h && HIDE.indexOf(h) >= 0) location.replace('#' + (HOME || ''))
    }
    guard()
    window.addEventListener('hashchange', guard, true)
  }

  // Саппорту калькулятор «Карточки объекта» в «Выезде» не нужен (HEAD 08.11): ?nocalc=1 прячет его, чек-листы остаются.
  if (qp.get('nocalc') === '1') {
    var st2 = document.createElement('style'); st2.textContent = '.calc{display:none!important}'
    document.head ? document.head.appendChild(st2) : document.documentElement.appendChild(st2)
  }

  // Ссылки на другие артефакты → открыть место в приложении.
  document.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a[href]')
    if (!a) return
    var mm = a.getAttribute('href').match(/claude\.ai\/artifact\/([A-Za-z0-9]+)(#.*)?/)
    if (!mm) return
    var code = (P.artifacts || {})[mm[1]]
    e.preventDefault()
    if (code && window.parent !== window) window.parent.postMessage({ type: 'artgame:place', code: code, hash: mm[2] || '' }, location.origin)
  }, true)
})()
