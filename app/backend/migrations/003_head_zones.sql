-- HEAD работает во всех зонах (как в прототипе).
INSERT INTO person_zones (person_id, zone_code)
SELECT p.id, z.code FROM people p CROSS JOIN zones z WHERE p.role_code = 'head'
ON CONFLICT DO NOTHING;
