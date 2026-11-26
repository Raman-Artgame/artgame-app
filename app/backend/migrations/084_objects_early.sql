-- HEAD 26.11: «когда захожу на сделку, как выгрузить материал?» — дизайнер грузит эскиз файлом прямо в карточке сделки,
-- файл ложится в папку сделки ДИЗАЙН. У сделки до стадии «Отправка счёта» строки в objects ещё нет — заводим её со статусом
-- early: только ради папки и файлов. В списках объектов (смены, Продакшн, проекты) её нет: там status='active'/'done'.
-- Когда сделка дойдёт до работы, синхронизация сама поставит active.
ALTER TABLE objects DROP CONSTRAINT IF EXISTS objects_status_check;
ALTER TABLE objects ADD CONSTRAINT objects_status_check CHECK (status IN ('active', 'done', 'archived', 'early'));
