-- Repair medicine-location mappings without overwriting existing coordinates.
-- Existing rows keep x/y/z/yaw; missing medicines receive neutral defaults.

START TRANSACTION;

UPDATE medicine_locations ml
JOIN medicines m ON m.id = ml.medicine_id
SET ml.medicine_name = m.name
WHERE ml.medicine_name <> m.name;

INSERT INTO medicine_locations (medicine_id, medicine_name, x, y, z, yaw)
SELECT m.id, m.name, 1, 1, 1, 0
FROM medicines m
LEFT JOIN medicine_locations ml ON ml.medicine_id = m.id
WHERE ml.id IS NULL;

COMMIT;
