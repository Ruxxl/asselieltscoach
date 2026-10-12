/**
 * Хранилище Assel IELTS в Google Таблице: сервер (backend/services/sheets.py) дублирует сюда
 * учеников, покупки курсов, платежи Halyk и прогресс по урокам, а после каждого деплоя на Render
 * восстанавливает из неё свою базу — SQLite на бесплатном Render стирается при перезапуске.
 *
 * Установка: в таблице «Расширения → Apps Script», заменить код этим файлом, вписать свой пароль
 * в SECRET, «Начать развертывание → Новое развертывание → Веб-приложение»: запуск от «Меня»,
 * доступ «Все». URL веб-приложения и тот же пароль положить в Render как SHEETS_WEBHOOK_URL и
 * SHEETS_SECRET.
 *
 * Листы и колонки создаются сами. Править значения руками можно, но колонку "key" не менять:
 * по ней сервер находит строку при обновлении.
 */

const SECRET = 'ВПИШИТЕ_СЮДА_ПАРОЛЬ';

function doPost(e) {
  let req;
  try {
    req = JSON.parse(e.postData.contents);
  } catch (err) {
    return json_({ ok: false, error: 'bad json' });
  }
  // Заглушка собрана из частей, чтобы «Заменить всё» при вписывании пароля не задело и эту проверку.
  if (!SECRET || SECRET === 'ВПИШИТЕ_' + 'СЮДА_ПАРОЛЬ' || req.secret !== SECRET) {
    return json_({ ok: false, error: 'forbidden' });
  }

  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    if (req.action === 'upsert') {
      upsert_(req.sheet, req.rows || []);
      return json_({ ok: true });
    }
    if (req.action === 'dump') {
      const data = {};
      (req.sheets || []).forEach(function (name) { data[name] = readSheet_(name); });
      return json_({ ok: true, data: data });
    }
    return json_({ ok: false, error: 'unknown action' });
  } finally {
    lock.releaseLock();
  }
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

function getSheet_(name) {
  const book = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = book.getSheetByName(name);
  if (!sheet) {
    sheet = book.insertSheet(name);
    // Всё храним текстом: иначе Таблица превратит номер заказа "000123" в число 123,
    // а длинные Telegram id — в экспоненту.
    sheet.getRange('A:Z').setNumberFormat('@');
    sheet.getRange(1, 1).setValue('key');
    sheet.setFrozenRows(1);
  }
  return sheet;
}

function headers_(sheet) {
  return sheet.getRange(1, 1, 1, Math.max(sheet.getLastColumn(), 1)).getValues()[0].map(String);
}

/** Строки — объекты с полем key: найденную по key строку обновляем (только переданные поля), иначе добавляем. */
function upsert_(name, rows) {
  if (!rows.length) return;
  const sheet = getSheet_(name);
  let headers = headers_(sheet);

  rows.forEach(function (row) {
    Object.keys(row).forEach(function (field) {
      if (headers.indexOf(field) === -1) {
        headers.push(field);
        sheet.getRange(1, headers.length).setValue(field);
      }
    });
  });

  const lastRow = sheet.getLastRow();
  const keys = lastRow > 1 ? sheet.getRange(2, 1, lastRow - 1, 1).getValues().map(function (r) { return String(r[0]); }) : [];

  rows.forEach(function (row) {
    const idx = keys.indexOf(String(row.key));
    if (idx === -1) {
      const values = headers.map(function (h) { return row[h] === undefined || row[h] === null ? '' : String(row[h]); });
      sheet.getRange(sheet.getLastRow() + 1, 1, 1, values.length).setNumberFormat('@').setValues([values]);
      keys.push(String(row.key));
    } else {
      Object.keys(row).forEach(function (field) {
        const value = row[field] === null ? '' : String(row[field]);
        sheet.getRange(idx + 2, headers.indexOf(field) + 1).setNumberFormat('@').setValue(value);
      });
    }
  });
}

function readSheet_(name) {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(name);
  if (!sheet || sheet.getLastRow() < 2) return [];
  const values = sheet.getDataRange().getValues();
  const headers = values[0].map(String);
  return values.slice(1).map(function (r) {
    const obj = {};
    headers.forEach(function (h, i) { obj[h] = r[i] === '' ? null : String(r[i]); });
    return obj;
  });
}
