-- Пробный день без ручной переписки (HEAD 28.11: «как кандидат получит информацию?», «через телеграм бота», «выбор даты… ГИП подтверждал»):
-- кандидат привязывается к боту по кнопке после анкеты; выбирает день, куратор ГИП подтверждает с временем и местом;
-- бот сам пишет кандидату и напоминает накануне. WhatsApp — запасной путь, когда Telegram нет.
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS tg_id              bigint,
                       ADD COLUMN IF NOT EXISTS trial_time         text,
                       ADD COLUMN IF NOT EXISTS trial_place        text,
                       ADD COLUMN IF NOT EXISTS trial_bring        text,
                       ADD COLUMN IF NOT EXISTS trial_state        text CHECK (trial_state IN ('pick', 'wait', 'ok')),
                       ADD COLUMN IF NOT EXISTS trial_sent_at      timestamptz,   -- кандидат получил приглашение (бот или WhatsApp от HEAD)
                       ADD COLUMN IF NOT EXISTS trial_remind_at    timestamptz,   -- напоминание накануне ушло
                       ADD COLUMN IF NOT EXISTS trial_nag_at       timestamptz;   -- куратору: оцени пробный день
CREATE INDEX IF NOT EXISTS candidates_tg ON candidates (tg_id) WHERE tg_id IS NOT NULL;
