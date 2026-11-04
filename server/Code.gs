/**
 * ARTGAME — Журнал работ (MVP v2, 04.11.2026)
 * Сервер на Google Apps Script, привязан к Таблице «Журнал работ».
 * Вход — по Telegram (проверка initData токеном бота). Регистрация → уведомление HEAD в бот → HEAD назначает роль и зоны.
 * Константы ARTGAME только читаются (здесь не используются). В Битрикс ничего не пишется.
 */

const TZ = 'Asia/Almaty';
const AUTH_MAX_AGE_SEC = 7 * 24 * 3600;

// Зоны деятельности. Человек может иметь допуск к нескольким и в начале смены выбирает, где работает.
const ZONES = ['Роспись', 'Печать', 'Дизайн', 'Продажи'];

// Роли: зоны по умолчанию и какие зоны роль проверяет. HEAD видит и проверяет всё, назначает роли.
const ROLES = {
  'Саппорт':                       { zones: ['Роспись'] },
  'Художник':                      { zones: ['Роспись'] },
  'Художник Про':                  { zones: ['Роспись'] },
  'Главный художник':              { zones: ['Роспись'], checks: ['Роспись'] },
  'Оператор настенного принтера':  { zones: ['Печать'] },
  'Мастер настенной печати':       { zones: ['Печать'], checks: ['Печать'] },
  'МОП':                           { zones: ['Продажи'] },
  'VIP МОП':                       { zones: ['Продажи'] },
  'Главный дизайнер':              { zones: ['Дизайн'], checks: ['Дизайн'] },
  'Помощник дизайнера':            { zones: ['Дизайн'] },
  'HEAD':                          { zones: ZONES, checks: ZONES, admin: true }
};
// Уровень в росписи — для тех, у кого есть допуск «Роспись» (в т.ч. печатники). Нужен для оплаты и КПД позже.
const ART_LEVELS = ['Саппорт', 'Художник', 'Художник Про', 'Главный художник'];
const OFFICE = { id: 'OFFICE', name: 'Офис / без объекта', city: '', type: '' };
// Папка «ПРОЕКТЫ» на общем Диске ARTGAME.KZ. Внутри: <год>/<MM МЕСЯЦ>/«<ID> · <НАЗВАНИЕ> — <ГОРОД>».
const PROJECTS_ROOT_ID = '1_33LDppwOu02ToP4c3uUS-mPux5mPIJf';
const MONTHS = ['ЯНВАРЬ', 'ФЕВРАЛЬ', 'МАРТ', 'АПРЕЛЬ', 'МАЙ', 'ИЮНЬ', 'ИЮЛЬ', 'АВГУСТ', 'СЕНТЯБРЬ', 'ОКТЯБРЬ', 'НОЯБРЬ', 'ДЕКАБРЬ'];
const PHOTO_SUBFOLDER = 'Журнал работ (фото и чеки)';

const SH = { people: 'Люди', objects: 'Объекты', shifts: 'Смены', expenses: 'Расходы', dict: 'Справочник', summary: 'Сводка', log: 'Журнал действий' };

const HEAD = {
  people:   ['Telegram ID', 'Имя', 'Телефон', 'Город', 'Хочет роль', 'Роль', 'Допуски (зоны)', 'Уровень в росписи', 'Статус', 'Username', 'Зарегистрирован', 'Назначил', 'Дата назначения'],
  objects:  ['ID объекта', 'Название', 'Город', 'Тип', 'Площадь по смете, м²', 'Бюджет материалов, ₸', 'Статус', 'ГИП (Telegram ID)', 'Папка на Диске'],
  shifts:   ['ID', 'ID объекта', 'Объект', 'Telegram ID', 'Имя', 'Зона', 'Роль', 'Начало', 'Конец', 'Перерыв, мин', 'Часы', 'Сделано, м²', 'Фото до', 'Фото после', 'Комментарий', 'Статус', 'Проверил', 'Дата проверки', 'Причина возврата'],
  expenses: ['ID', 'Дата', 'ID объекта', 'Объект', 'Telegram ID', 'Имя', 'Зона', 'Категория', 'Сумма, ₸', 'Чьи деньги', 'Фото чека', 'Комментарий', 'Статус', 'Проверил', 'Дата проверки', 'Причина возврата'],
  dict:     ['Категории расходов', 'Чьи деньги', 'Города'],
  log:      ['Когда', 'Telegram ID', 'Имя', 'Действие', 'Запись', 'Подробно']
};

const P  = { id: 1, name: 2, phone: 3, city: 4, want: 5, role: 6, zones: 7, level: 8, status: 9, username: 10, added: 11, by: 12, at: 13 };
const SC = { id: 1, objId: 2, obj: 3, tg: 4, name: 5, zone: 6, role: 7, start: 8, end: 9, brk: 10, hours: 11, m2: 12, photoBefore: 13, photoAfter: 14, comment: 15, status: 16, checker: 17, checkedAt: 18, reason: 19 };
const EC = { id: 1, date: 2, objId: 3, obj: 4, tg: 5, name: 6, zone: 7, cat: 8, sum: 9, whose: 10, photo: 11, comment: 12, status: 13, checker: 14, checkedAt: 15, reason: 16 };
const ST = { open: 'открыта', review: 'на проверке', ok: 'принята', back: 'возвращена' };
const PS = { pending: 'ждёт', active: 'активен', off: 'отключён' };

// ───────────────────────── Установка ─────────────────────────

/** Запустить из редактора. Можно запускать повторно: данные не трогает. */
function setup() {
  const ss = SpreadsheetApp.getActive();
  ss.setSpreadsheetTimeZone(TZ);
  Object.keys(HEAD).forEach(k => ensureSheet_(ss, SH[k], HEAD[k]));

  const dict = ss.getSheetByName(SH.dict);
  if (dict.getLastRow() < 2) {
    const cats = ['Краска', 'Кисти и валики', 'Лак', 'Малярный скотч и плёнка', 'Грунт', 'Растворитель', 'Чернила / расходники принтера', 'Такси / доставка', 'Аренда (вышка, леса)', 'Другое'];
    const whose = ['Свои (вернуть)', 'Подотчёт', 'Карта компании'];
    const cities = ['Астана', 'Шымкент', 'Алматы', 'Другой'];
    const n = Math.max(cats.length, whose.length, cities.length);
    const rows = [];
    for (let i = 0; i < n; i++) rows.push([cats[i] || '', whose[i] || '', cities[i] || '']);
    dict.getRange(2, 1, rows.length, 3).setValues(rows);
  }

  const dv = (list) => SpreadsheetApp.newDataValidation().requireValueInList(list, true).setAllowInvalid(false).build();
  const people = ss.getSheetByName(SH.people);
  people.getRange(2, P.role, 999).setDataValidation(dv(Object.keys(ROLES)));
  people.getRange(2, P.level, 999).setDataValidation(dv(ART_LEVELS));
  people.getRange(2, P.status, 999).setDataValidation(dv([PS.pending, PS.active, PS.off]));
  ss.getSheetByName(SH.objects).getRange('D2:D').setDataValidation(dv(['Роспись', 'Холст', 'Печать', 'Дизайн', 'Другое']));
  ss.getSheetByName(SH.objects).getRange('G2:G').setDataValidation(dv(['в работе', 'закрыт']));

  // Сводка по объектам: считает только принятые записи
  const sum = ensureSheet_(ss, SH.summary, ['ID объекта', 'Объект', 'Часы (принято)', 'Сделано, м² (принято)', 'Расходы, ₸ (принято)', 'Бюджет материалов, ₸', 'Остаток бюджета, ₸', 'На проверке: смен', 'На проверке: чеков']);
  const map = (body) => '=MAP(A2:A, LAMBDA(id, IF(id="","", ' + body + ')))';
  const spent = "SUMIFS('Расходы'!I:I, 'Расходы'!C:C, id, 'Расходы'!M:M, \"принята\")";
  const budget = "IFERROR(INDEX('Объекты'!F:F, MATCH(id, 'Объекты'!A:A, 0)), 0)";
  sum.getRange('A2').setFormula("=FILTER('Объекты'!A2:B, 'Объекты'!A2:A<>\"\")");
  sum.getRange('C2').setFormula(map("SUMIFS('Смены'!K:K, 'Смены'!B:B, id, 'Смены'!P:P, \"принята\")"));
  sum.getRange('D2').setFormula(map("SUMIFS('Смены'!L:L, 'Смены'!B:B, id, 'Смены'!P:P, \"принята\")"));
  sum.getRange('E2').setFormula(map(spent));
  sum.getRange('F2').setFormula(map(budget));
  sum.getRange('G2').setFormula(map(budget + ' - ' + spent));
  sum.getRange('H2').setFormula(map("COUNTIFS('Смены'!B:B, id, 'Смены'!P:P, \"на проверке\")"));
  sum.getRange('I2').setFormula(map("COUNTIFS('Расходы'!C:C, id, 'Расходы'!M:M, \"на проверке\")"));

  ss.getSheetByName(SH.shifts).getRange('H2:I').setNumberFormat('dd.MM.yyyy HH:mm');
  ss.getSheetByName(SH.expenses).getRange('B2:B').setNumberFormat('dd.MM.yyyy HH:mm');
  ss.getSheetByName(SH.expenses).getRange('I2:I').setNumberFormat('#,##0');
  people.getRange('A2:A').setNumberFormat('@');

  const props = PropertiesService.getScriptProperties();
  if (!props.getProperty('PHOTO_FOLDER_ID')) props.setProperty('PHOTO_FOLDER_ID', DriveApp.createFolder('ARTGAME_Zhurnal_rabot_foto').getId());

  const def = ss.getSheetByName('Лист1') || ss.getSheetByName('Sheet1');
  if (def && def.getLastRow() === 0 && ss.getSheets().length > 1) ss.deleteSheet(def);
  Logger.log('Готово. Дальше: свойство BOT_TOKEN и «Развернуть → Веб-приложение».');
}

/** Создаёт лист; если в листе только старая шапка — заменяет её новой. */
function ensureSheet_(ss, name, header) {
  let sh = ss.getSheetByName(name);
  if (!sh) sh = ss.insertSheet(name);
  if (sh.getLastRow() <= 1) {
    sh.getRange(1, 1, 1, Math.max(header.length, sh.getLastColumn() || 1)).clearContent();
    sh.getRange(1, 1, 1, header.length).setValues([header]).setFontWeight('bold');
    sh.setFrozenRows(1);
  }
  return sh;
}

// ───────────────────────── Веб-приложение ─────────────────────────

/** API для страницы со своего адреса (GitHub Pages): POST {action, initData, payload} → JSON */
function doPost(e) {
  let body = {};
  try { body = JSON.parse(e.postData.contents); } catch (err) {}
  return ContentService.createTextOutput(JSON.stringify(api(body.action, body.initData, body.payload)))
    .setMimeType(ContentService.MimeType.JSON);
}

/** Адрес приложения для кнопок в сообщениях бота: свойство APP_URL (GitHub Pages), иначе адрес Apps Script. */
function appUrl_() {
  return String(PropertiesService.getScriptProperties().getProperty('APP_URL') || '').trim() || ScriptApp.getService().getUrl();
}

// Мост для страницы на GitHub Pages: невидимое окно Google принимает запросы через postMessage и вызывает api().
const APP_ORIGIN = 'https://raman-artgame.github.io';
const BRIDGE_HTML = '<!DOCTYPE html><html><body><script>' +
  'var A=' + JSON.stringify(APP_ORIGIN) + ';' +
  'window.addEventListener("message",function(ev){if(ev.origin!==A)return;var m=ev.data||{};if(m.type!=="artgame-call")return;' +
  'var send=function(r){ev.source.postMessage({type:"artgame-reply",id:m.id,r:r},A);};' +
  'google.script.run.withSuccessHandler(send).withFailureHandler(function(e){send({ok:false,error:String(e&&e.message||e)});}).api(m.action,m.initData,m.payload);});' +
  'window.top.postMessage({type:"artgame-bridge-ready"},A);' +
  '<\/script></body></html>';

function doGet(e) {
  if (e && e.parameter && e.parameter.bridge) {
    return HtmlService.createHtmlOutput(BRIDGE_HTML).setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
  }
  return HtmlService.createHtmlOutputFromFile('Index')
    .setTitle('ARTGAME')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1, maximum-scale=1')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

/** Единая точка входа: google.script.run.api(action, initData, payload) */
function api(action, initData, payload) {
  try {
    const tg = verifyInitData_(initData);
    payload = payload || {};
    if (action === 'boot') return ok_(boot_(tg));
    if (action === 'register') return ok_(register_(tg, payload));
    const me = getPerson_(tg.id);
    if (!me || me.status !== PS.active) throw new Error('Доступ ещё не открыт. HEAD получил заявку.');
    switch (action) {
      case 'startShift': return ok_(startShift_(me, payload));
      case 'endShift':   return ok_(endShift_(me, payload));
      case 'addExpense': return ok_(addExpense_(me, payload));
      case 'mine':       return ok_(mine_(me));
      case 'queue':      return ok_(queue_(me));
      case 'decide':     return ok_(decide_(me, payload));
      case 'team':       return ok_(team_(me));
      case 'setPerson':  return ok_(setPerson_(me, payload));
      default: throw new Error('Неизвестное действие');
    }
  } catch (e) {
    return { ok: false, error: String(e && e.message || e) };
  }
}
function ok_(data) { return { ok: true, data: data }; }

// ───────────────────────── Telegram ─────────────────────────

function verifyInitData_(initData) {
  if (!initData) throw new Error('Открой приложение из Telegram-бота.');
  const token = botToken_();
  // Пробуем три вида значений: как пришли, раскодированные один и два раза (Google и Telegram по-разному кодируют ссылку).
  const raw = {};
  initData.split('&').forEach(p => { const i = p.indexOf('='); if (i > 0) raw[p.slice(0, i)] = p.slice(i + 1); });
  if (!raw.hash) throw new Error('Нет подписи Telegram.');
  const dec = v => { try { return decodeURIComponent(v); } catch (e) { return v; } };
  const variants = [
    Object.fromEntries(Object.entries(raw).map(([k, v]) => [k, dec(v)])),
    raw,
    Object.fromEntries(Object.entries(raw).map(([k, v]) => [k, dec(dec(v))]))
  ];
  const secret = Utilities.computeHmacSha256Signature(Utilities.newBlob(token).getBytes(), Utilities.newBlob('WebAppData').getBytes());
  const hexOf = (pairs) => {
    const dcs = Object.keys(pairs).filter(k => k !== 'hash').sort().map(k => k + '=' + pairs[k]).join('\n');
    return Utilities.computeHmacSha256Signature(Utilities.newBlob(dcs).getBytes(), secret).map(b => ('0' + ((b + 256) % 256).toString(16)).slice(-2)).join('');
  };
  const noSig = v => Object.fromEntries(Object.entries(v).filter(([k]) => k !== 'signature'));
  const pairs = variants.concat(variants.map(noSig)).find(v => hexOf(v) === raw.hash);
  if (!pairs) throw new Error('Подпись Telegram не прошла. Проверь BOT_TOKEN в свойствах скрипта: должен быть токен бота ' + token.split(':')[0] + ' без пробелов (длина ' + token.length + ').');
  if (Date.now() / 1000 - Number(pairs.auth_date || 0) > AUTH_MAX_AGE_SEC) throw new Error('Вход устарел. Закрой и открой приложение из бота.');
  let user = {};
  try { user = JSON.parse(dec(raw.user || '')); } catch (e) { try { user = JSON.parse(dec(dec(raw.user || ''))); } catch (e2) {} }
  if (!user.id) throw new Error('Telegram не передал пользователя.');
  return { id: String(user.id), first: user.first_name || '', last: user.last_name || '', username: user.username || '' };
}

function botToken_() {
  const t = String(PropertiesService.getScriptProperties().getProperty('BOT_TOKEN') || '').trim();
  if (!t) throw new Error('Не задан BOT_TOKEN в свойствах скрипта.');
  return t;
}

/** Сообщение в Telegram. Ошибки не роняют основное действие. button: {text, tab} открывает приложение на вкладке. */
function notify_(chatId, text, button) {
  try {
    const body = { chat_id: chatId, text: text, parse_mode: 'HTML' };
    if (button) {
      const url = appUrl_() + (button.tab ? '?tab=' + button.tab : '');
      body.reply_markup = JSON.stringify({ inline_keyboard: [[{ text: button.text, web_app: { url: url } }]] });
    }
    UrlFetchApp.fetch('https://api.telegram.org/bot' + botToken_() + '/sendMessage', {
      method: 'post', contentType: 'application/json', payload: JSON.stringify(body), muteHttpExceptions: true
    });
  } catch (e) { Logger.log('notify: ' + e); }
}

function heads_() { return people_().filter(p => p.role === 'HEAD' && p.status === PS.active); }
const h_ = s => String(s == null ? '' : s).replace(/[<>&]/g, c => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;' }[c]));

// ───────────────────────── Данные ─────────────────────────

function sheet_(key) { return SpreadsheetApp.getActive().getSheetByName(SH[key]); }
function rows_(key) {
  const sh = sheet_(key), last = sh.getLastRow();
  return last < 2 ? [] : sh.getRange(2, 1, last - 1, sh.getLastColumn()).getValues();
}
const split_ = s => String(s || '').split(',').map(x => x.trim()).filter(Boolean);

function people_() {
  return rows_('people').map((r, i) => ({
    row: i + 2, id: String(r[P.id - 1]), name: r[P.name - 1], phone: String(r[P.phone - 1]), city: r[P.city - 1], want: r[P.want - 1],
    role: r[P.role - 1], zones: split_(r[P.zones - 1]), level: r[P.level - 1], status: r[P.status - 1], username: r[P.username - 1],
    added: r[P.added - 1] instanceof Date ? fmt_(r[P.added - 1]) : ''
  }));
}
function getPerson_(id) { return people_().find(p => p.id === String(id)) || null; }

function checksZones_(me) { return (ROLES[me.role] && ROLES[me.role].checks) || []; }
function isAdmin_(me) { return !!(ROLES[me.role] && ROLES[me.role].admin); }

function objects_() {
  const list = rows_('objects').filter(r => r[0] && r[6] !== 'закрыт')
    .map(r => ({ id: String(r[0]), name: r[1], city: r[2], type: r[3], gip: String(r[7] || '') }));
  return list.concat([OFFICE]);
}
function findObject_(id) {
  const o = objects_().find(o => o.id === String(id));
  if (!o) throw new Error('Объект не найден или закрыт.');
  return o;
}
function dict_() {
  const d = rows_('dict');
  return { cats: d.map(r => r[0]).filter(String), whose: d.map(r => r[1]).filter(String), cities: d.map(r => r[2]).filter(String) };
}
function nextId_(key, prefix) {
  const sh = sheet_(key), last = sh.getLastRow();
  let max = 0;
  if (last >= 2) sh.getRange(2, 1, last - 1, 1).getValues().forEach(r => { const n = Number(String(r[0]).replace(prefix, '')); if (n > max) max = n; });
  return prefix + ('0000' + (max + 1)).slice(-4);
}
function log_(me, action, recId, details) { sheet_('log').appendRow([new Date(), me.id, me.name, action, recId || '', details || '']); }
function fmt_(d) { return d instanceof Date ? Utilities.formatDate(d, TZ, 'dd.MM HH:mm') : ''; }
/** Фото и чеки кладутся в папку объекта в «ПРОЕКТЫ», в подпапку «Журнал работ». Офис — в общую папку журнала. */
function savePhoto_(b64, name, objId) {
  if (!b64) return '';
  const folder = photoFolder_(objId);
  const bytes = Utilities.base64Decode(String(b64).replace(/^data:image\/\w+;base64,/, ''));
  return folder.createFile(Utilities.newBlob(bytes, 'image/jpeg', name + '.jpg')).getUrl();
}
function photoFolder_(objId) {
  const fallback = () => DriveApp.getFolderById(PropertiesService.getScriptProperties().getProperty('PHOTO_FOLDER_ID'));
  if (!objId || objId === OFFICE.id) return fallback();
  try {
    const project = projectFolder_(objId);
    const sub = project.getFoldersByName(PHOTO_SUBFOLDER);
    return sub.hasNext() ? sub.next() : project.createFolder(PHOTO_SUBFOLDER);
  } catch (e) { Logger.log('photoFolder: ' + e); return fallback(); }
}

/** Папка объекта: из колонки «Папка на Диске», иначе ищем «<ID> ·» в ПРОЕКТЫ, иначе создаём в текущем месяце. Ссылка запоминается. */
function projectFolder_(objId) {
  const sh = sheet_('objects'), data = rows_('objects');
  const i = data.findIndex(r => String(r[0]) === String(objId));
  if (i < 0) throw new Error('Объект не найден');
  const r = data[i], saved = String(r[8] || '');
  const m = saved.match(/[-\w]{25,}/);
  if (m) { try { return DriveApp.getFolderById(m[0]); } catch (e) {} }
  let folder = findProjectFolder_(String(objId));
  if (!folder) {
    const now = new Date(), root = DriveApp.getFolderById(PROJECTS_ROOT_ID);
    const year = child_(root, String(now.getFullYear()));
    const month = child_(year, ('0' + (now.getMonth() + 1)).slice(-2) + ' ' + MONTHS[now.getMonth()]);
    folder = month.createFolder(objId + ' · ' + String(r[1] || '').toUpperCase() + (r[2] ? ' — ' + String(r[2]).toUpperCase() : ''));
  }
  sh.getRange(i + 2, 9).setValue(folder.getUrl());
  return folder;
}
function child_(parent, name) { const it = parent.getFoldersByName(name); return it.hasNext() ? it.next() : parent.createFolder(name); }
function findProjectFolder_(objId) {
  const prefix = objId + ' ·';
  try {
    const found = DriveApp.searchFolders("title contains '" + objId.replace(/'/g, '') + " ·' and trashed = false");
    while (found.hasNext()) { const f = found.next(); if (f.getName().indexOf(prefix) === 0) return f; }
  } catch (e) { Logger.log('searchFolders: ' + e); }
  const years = DriveApp.getFolderById(PROJECTS_ROOT_ID).getFolders();
  while (years.hasNext()) {
    const y = years.next();
    if (!/^\d{4}$/.test(y.getName())) continue;
    const months = y.getFolders();
    while (months.hasNext()) {
      const it = months.next().getFolders();
      while (it.hasNext()) { const f = it.next(); if (f.getName().indexOf(prefix) === 0) return f; }
    }
  }
  return null;
}

function withLock_(fn) {
  const lock = LockService.getScriptLock(); lock.waitLock(10000);
  try { return fn(); } finally { lock.releaseLock(); }
}
function openShiftRow_(tgId) {
  const data = rows_('shifts');
  for (let i = data.length - 1; i >= 0; i--) if (String(data[i][SC.tg - 1]) === String(tgId) && data[i][SC.status - 1] === ST.open) return { row: i + 2, r: data[i] };
  return null;
}
/** Роль, с которой человек работает в зоне: в росписи — его уровень, иначе основная роль. */
function roleInZone_(me, zone) {
  if (zone === 'Роспись' && ROLES[me.role] && ROLES[me.role].zones.indexOf('Роспись') < 0) return me.level || 'Саппорт';
  if (zone === 'Роспись' && me.level) return me.level;
  return me.role;
}

// ───────────────────────── Вход и регистрация ─────────────────────────

function boot_(tg) {
  const me = getPerson_(tg.id);
  const base = { roles: Object.keys(ROLES), zones: ZONES, levels: ART_LEVELS, dict: dict_() };
  if (!me) return Object.assign(base, { state: 'new', tg: tg });
  if (me.status !== PS.active) return Object.assign(base, { state: me.status === PS.off ? 'off' : 'pending', me: me });
  const open = openShiftRow_(me.id);
  return Object.assign(base, {
    state: 'active', me: me,
    approver: checksZones_(me).length > 0, admin: isAdmin_(me),
    objects: objects_(),
    openShift: open ? { id: open.r[0], obj: open.r[SC.obj - 1], objId: String(open.r[SC.objId - 1]), zone: open.r[SC.zone - 1], role: open.r[SC.role - 1], start: open.r[SC.start - 1].getTime() } : null,
    mine: mine_(me),
    pendingCount: isAdmin_(me) ? people_().filter(p => p.status === PS.pending).length : 0
  });
}

function register_(tg, p) {
  const name = String(p.name || '').trim(), phone = String(p.phone || '').trim();
  if (name.length < 3) throw new Error('Укажи имя и фамилию.');
  if (phone.replace(/\D/g, '').length < 10) throw new Error('Укажи телефон.');
  const want = Object.keys(ROLES).indexOf(p.want) >= 0 && p.want !== 'HEAD' ? p.want : '';
  const res = withLock_(() => {
    if (getPerson_(tg.id)) throw new Error('Ты уже зарегистрирован.');
    // Самый первый человек в пустой системе становится HEAD (это должен быть ты при запуске).
    const first = heads_().length === 0 && people_().length === 0;
    const row = [tg.id, name, phone, p.city || '', want, first ? 'HEAD' : '', first ? ZONES.join(', ') : '', '', first ? PS.active : PS.pending, tg.username, new Date(), first ? 'система' : '', first ? new Date() : ''];
    sheet_('people').appendRow(row);
    return { first: first };
  });
  if (!res.first) {
    const text = '🆕 <b>Новый сотрудник</b>\n' + h_(name) + '\n📞 ' + h_(phone) + (p.city ? '\n📍 ' + h_(p.city) : '') +
      (want ? '\nХочет роль: <b>' + h_(want) + '</b>' : '') + (tg.username ? '\n@' + h_(tg.username) : '');
    heads_().forEach(hd => notify_(hd.id, text, { text: 'Назначить роль', tab: 'team' }));
  }
  log_({ id: tg.id, name: name }, 'Регистрация', '', res.first ? 'первый вход, HEAD' : 'ждёт роли');
  return res;
}

// ───────────────────────── Команда (только HEAD) ─────────────────────────

function team_(me) {
  if (!isAdmin_(me)) throw new Error('Только HEAD.');
  const order = { [PS.pending]: 0, [PS.active]: 1, [PS.off]: 2 };
  return people_().sort((a, b) => order[a.status] - order[b.status] || String(a.name).localeCompare(b.name)).map(p => { delete p.row; return p; });
}

function setPerson_(me, p) {
  if (!isAdmin_(me)) throw new Error('Только HEAD.');
  if (!ROLES[p.role]) throw new Error('Выбери роль.');
  const zones = (p.zones || []).filter(z => ZONES.indexOf(z) >= 0);
  if (!zones.length) throw new Error('Отметь хотя бы одну зону.');
  const status = [PS.pending, PS.active, PS.off].indexOf(p.status) >= 0 ? p.status : PS.active;
  if (String(p.id) === me.id && (p.role !== 'HEAD' || status !== PS.active)) throw new Error('Себя снять с HEAD нельзя.');
  const level = zones.indexOf('Роспись') >= 0 ? (ART_LEVELS.indexOf(p.level) >= 0 ? p.level : (ART_LEVELS.indexOf(p.role) >= 0 ? p.role : 'Саппорт')) : '';
  const before = withLock_(() => {
    const person = getPerson_(p.id);
    if (!person) throw new Error('Человек не найден.');
    const sh = sheet_('people');
    sh.getRange(person.row, P.role, 1, 4).setValues([[p.role, zones.join(', '), level, status]]);
    sh.getRange(person.row, P.by, 1, 2).setValues([[me.name, new Date()]]);
    return person;
  });
  log_(me, 'Роль', p.id, before.name + ': ' + p.role + ' · ' + zones.join(', ') + (level ? ' · ' + level : '') + ' · ' + status);
  if (status === PS.active && (before.status !== PS.active || before.role !== p.role || before.zones.join(', ') !== zones.join(', '))) {
    notify_(p.id, '✅ <b>Доступ открыт</b>\nРоль: ' + h_(p.role) + '\nЗоны: ' + h_(zones.join(', ')) + (level ? '\nУровень в росписи: ' + h_(level) : ''), { text: 'Открыть журнал' });
  } else if (status === PS.off && before.status !== PS.off) {
    notify_(p.id, 'Доступ к журналу ARTGAME закрыт. Вопросы — к HEAD.');
  }
  return { id: p.id };
}

// ───────────────────────── Смены и расходы ─────────────────────────

function pickZone_(me, zone) {
  if (me.zones.indexOf(zone) >= 0) return zone;
  if (me.zones.length === 1) return me.zones[0];
  throw new Error('Выбери зону работы.');
}

function startShift_(me, p) {
  return withLock_(() => {
    if (openShiftRow_(me.id)) throw new Error('У тебя уже открыта смена. Сначала закрой её.');
    const zone = pickZone_(me, p.zone);
    const o = findObject_(p.objId);
    const id = nextId_('shifts', 'S');
    const photo = savePhoto_(p.photo, 'smena_' + Utilities.formatDate(new Date(), TZ, 'yyyy-MM-dd') + '_' + id + '_do', o.id);
    sheet_('shifts').appendRow([id, o.id, o.name, me.id, me.name, zone, roleInZone_(me, zone), new Date(), '', '', '', '', photo, '', p.comment || '', ST.open, '', '', '']);
    log_(me, 'Начал смену', id, zone + ' · ' + o.name);
    return { id: id };
  });
}

function endShift_(me, p) {
  return withLock_(() => {
    const open = openShiftRow_(me.id);
    if (!open) throw new Error('Открытой смены нет.');
    const end = new Date();
    const brk = Math.max(0, Number(p.breakMin) || 0);
    const hours = Math.max(0, Math.round(((end - open.r[SC.start - 1]) / 3600000 - brk / 60) * 100) / 100);
    const m2 = Math.max(0, Number(String(p.m2 || 0).replace(',', '.')) || 0);
    const id = open.r[0];
    const photo = savePhoto_(p.photo, 'smena_' + Utilities.formatDate(end, TZ, 'yyyy-MM-dd') + '_' + id + '_posle', open.r[SC.objId - 1]);
    const sh = sheet_('shifts');
    sh.getRange(open.row, SC.end, 1, 4).setValues([[end, brk, hours, m2]]);
    if (photo) sh.getRange(open.row, SC.photoAfter).setValue(photo);
    const comment = [open.r[SC.comment - 1], p.comment].filter(String).join(' | ');
    sh.getRange(open.row, SC.comment, 1, 2).setValues([[comment, ST.review]]);
    log_(me, 'Закончил смену', id, hours + ' ч, ' + m2 + ' м²');
    return { id: id, hours: hours };
  });
}

function addExpense_(me, p) {
  const sum = Math.round(Number(String(p.sum || '').replace(/\s/g, '').replace(',', '.')));
  if (!(sum > 0)) throw new Error('Укажи сумму.');
  if (!p.photo) throw new Error('Нужно фото чека.');
  const zone = pickZone_(me, p.zone);
  const o = findObject_(p.objId);
  return withLock_(() => {
    const id = nextId_('expenses', 'E');
    const photo = savePhoto_(p.photo, 'chek_' + Utilities.formatDate(new Date(), TZ, 'yyyy-MM-dd') + '_' + id, o.id);
    sheet_('expenses').appendRow([id, new Date(), o.id, o.name, me.id, me.name, zone, p.cat || 'Другое', sum, p.whose || '', photo, p.comment || '', ST.review, '', '', '']);
    log_(me, 'Расход', id, o.name + ': ' + sum + ' ₸');
    return { id: id };
  });
}

function mine_(me) {
  const s = rows_('shifts').filter(r => String(r[SC.tg - 1]) === me.id).slice(-15).reverse().map(r => ({
    id: r[0], obj: r[SC.obj - 1], zone: r[SC.zone - 1], when: fmt_(r[SC.start - 1]), hours: r[SC.hours - 1], m2: r[SC.m2 - 1], status: r[SC.status - 1], reason: r[SC.reason - 1]
  }));
  const e = rows_('expenses').filter(r => String(r[EC.tg - 1]) === me.id).slice(-15).reverse().map(r => ({
    id: r[0], obj: r[EC.obj - 1], when: fmt_(r[EC.date - 1]), cat: r[EC.cat - 1], sum: r[EC.sum - 1], status: r[EC.status - 1], reason: r[EC.reason - 1]
  }));
  return { shifts: s, expenses: e };
}

// ───────────────────────── Проверка ─────────────────────────

/** HEAD — всё. Главный художник / Мастер печати / Главный дизайнер — своя зона. ГИП объекта — свой объект. Свои записи — никогда. */
function canCheck_(me, zone, objId, authorId) {
  if (String(authorId) === me.id) return false;
  if (checksZones_(me).indexOf(zone) >= 0) return true;
  const o = rows_('objects').find(r => String(r[0]) === String(objId));
  return !!o && String(o[7]) === me.id;
}

function queue_(me) {
  const s = rows_('shifts').filter(r => r[SC.status - 1] === ST.review && canCheck_(me, r[SC.zone - 1], r[SC.objId - 1], r[SC.tg - 1])).map(r => ({
    kind: 'shift', id: r[0], obj: r[SC.obj - 1], who: r[SC.name - 1], zone: r[SC.zone - 1], role: r[SC.role - 1], when: fmt_(r[SC.start - 1]) + '–' + fmt_(r[SC.end - 1]).slice(-5),
    hours: r[SC.hours - 1], m2: r[SC.m2 - 1], brk: r[SC.brk - 1], before: r[SC.photoBefore - 1], after: r[SC.photoAfter - 1], comment: r[SC.comment - 1]
  }));
  const e = rows_('expenses').filter(r => r[EC.status - 1] === ST.review && canCheck_(me, r[EC.zone - 1], r[EC.objId - 1], r[EC.tg - 1])).map(r => ({
    kind: 'expense', id: r[0], obj: r[EC.obj - 1], who: r[EC.name - 1], zone: r[EC.zone - 1], when: fmt_(r[EC.date - 1]), cat: r[EC.cat - 1], sum: r[EC.sum - 1],
    whose: r[EC.whose - 1], photo: r[EC.photo - 1], comment: r[EC.comment - 1]
  }));
  return { shifts: s, expenses: e };
}

function decide_(me, p) {
  const accept = !!p.accept;
  if (!accept && !String(p.reason || '').trim()) throw new Error('Напиши причину возврата.');
  const key = p.kind === 'shift' ? 'shifts' : 'expenses';
  const C = key === 'shifts' ? SC : EC;
  const r = withLock_(() => {
    const data = rows_(key);
    const i = data.findIndex(r => r[0] === p.id);
    if (i < 0) throw new Error('Запись не найдена.');
    const r = data[i];
    if (r[C.status - 1] !== ST.review) throw new Error('Запись уже проверена.');
    if (!canCheck_(me, r[C.zone - 1], r[C.objId - 1], r[C.tg - 1])) throw new Error('Эту запись проверяет другой человек.');
    sheet_(key).getRange(i + 2, C.status, 1, 4).setValues([[accept ? ST.ok : ST.back, me.name, new Date(), accept ? '' : p.reason]]);
    return r;
  });
  log_(me, accept ? 'Принял' : 'Вернул', p.id, accept ? '' : p.reason);
  if (!accept) notify_(r[C.tg - 1], '↩️ ' + (key === 'shifts' ? 'Смена' : 'Расход') + ' ' + h_(p.id) + ' (' + h_(r[C.obj - 1]) + ') возвращена.\nПричина: ' + h_(p.reason), { text: 'Открыть журнал' });
  return { id: p.id };
}
