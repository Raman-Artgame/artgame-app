-- «Маркетинг → Медиа» видит и то, что положено в «МЕДИА» сделки на Диске руками (HEAD 26.11): когда сделку сверяли.
ALTER TABLE objects ADD COLUMN IF NOT EXISTS media_synced_at timestamptz;
CREATE INDEX IF NOT EXISTS files_drive_id ON files (drive_id) WHERE drive_id IS NOT NULL;
