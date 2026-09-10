const PRESCRIPTION_TYPE_CODES: Record<string, string> = {
  '普通': '01',
  '急诊': '02',
  '儿科': '03',
  '麻醉精一': '04',
  '精二': '05',
};

let schemaReady = false;

export async function ensurePrescriptionCodeSchema(conn: any): Promise<void> {
  if (schemaReady) return;

  await conn.query(`
    CREATE TABLE IF NOT EXISTS prescription_code_sequences (
      prescription_date CHAR(8) NOT NULL,
      type_code CHAR(2) NOT NULL,
      last_sequence INT UNSIGNED NOT NULL DEFAULT 0,
      updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      PRIMARY KEY (prescription_date, type_code)
    ) ENGINE = InnoDB DEFAULT CHARACTER SET = utf8mb4
  `);

  // 首次升级时同时从现存处方和审计快照恢复历史最大号，避免已删除处方的编号再次被使用。
  await conn.query(`
    INSERT INTO prescription_code_sequences (prescription_date, type_code, last_sequence)
    SELECT SUBSTRING(code, 3, 8), LEFT(code, 2), MAX(CAST(SUBSTRING(code, 11, 3) AS UNSIGNED))
    FROM (
      SELECT prescription_code AS code FROM prescriptions
      UNION ALL
      SELECT JSON_UNQUOTE(JSON_EXTRACT(snapshot_json, '$.prescription.prescription_code')) AS code
      FROM audit_chain_records
      WHERE snapshot_json IS NOT NULL
    ) issued_codes
    WHERE code REGEXP '^[0-9]{15}$'
    GROUP BY SUBSTRING(code, 3, 8), LEFT(code, 2)
    ON DUPLICATE KEY UPDATE last_sequence = GREATEST(last_sequence, VALUES(last_sequence))
  `);

  schemaReady = true;
}

// 类型编码(2) + 日期(8) + 当日流水号(3) + 校验码(2) = 15位。
export async function generatePrescriptionCode(type: string, conn: any): Promise<string> {
  const now = new Date();
  const dateStr = [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, '0'),
    String(now.getDate()).padStart(2, '0'),
  ].join('');
  const typeCode = PRESCRIPTION_TYPE_CODES[type] || '01';

  await conn.query(
    `INSERT INTO prescription_code_sequences (prescription_date, type_code, last_sequence)
     VALUES (?, ?, 0)
     ON DUPLICATE KEY UPDATE last_sequence = last_sequence`,
    [dateStr, typeCode]
  );
  await conn.query(
    `UPDATE prescription_code_sequences
     SET last_sequence = LAST_INSERT_ID(last_sequence + 1)
     WHERE prescription_date = ? AND type_code = ?`,
    [dateStr, typeCode]
  );
  const [rows] = await conn.query('SELECT LAST_INSERT_ID() AS sequence_no');
  const sequenceNumber = Number(rows[0]?.sequence_no || 0);
  if (sequenceNumber < 1 || sequenceNumber > 999) {
    throw new Error(`处方编号流水号超出范围: ${sequenceNumber}`);
  }

  const base = typeCode + dateStr + String(sequenceNumber).padStart(3, '0');
  const digitSum = [...base].reduce((sum, digit) => sum + Number(digit), 0);
  return base + String(digitSum % 97).padStart(2, '0');
}
