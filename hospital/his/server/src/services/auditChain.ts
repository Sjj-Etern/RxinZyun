import crypto from 'crypto';
import { config } from '../config';

const GENESIS_HASH = '0'.repeat(64);
const CHAIN_VERSION = 'local-audit-chain-v2';
let auditSchemaReady = false;

export type AuditEventType =
  | 'PRESCRIPTION_CREATED'
  | 'PHARMACIST_SCAN_CONFIRMED'
  | 'NURSE_SCAN_CONFIRMED'
  | 'PRESCRIPTION_COMPLETED'
  | 'DATA_CHANGED'
  | 'DATA_DELETED'
  | 'DATA_CHANGE_REVERTED';

export type PrescriptionSnapshot = {
  prescription: Record<string, unknown>;
  items: Array<Record<string, unknown>>;
};

type AuditRecordInput = {
  eventType: AuditEventType;
  entityType: 'prescription';
  entityId: number | string;
  flowStatus: string;
  traceCodes?: string[];
  prescriptionId: number | string;
  prescriptionCode?: string | null;
  operatorId?: number | string | null;
  snapshot?: PrescriptionSnapshot;
  changeId?: number | null;
};

type AuditPayload = {
  eventTime: string;
  eventType: string;
  entityId: string;
  entityType: string;
  flowStatus: string;
  operatorHash: string | null;
  prescriptionHash: string | null;
  traceCodeHash: string | null;
  snapshotHash?: string;
  changeId?: number;
};

const auditSalt = config.auth.auditHashSalt;
export const hash = (value: string) => crypto.createHash('sha256').update(value).digest('hex');

const formatDateForMysql = (date: Date) => {
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
};

export const canonicalize = (value: unknown): unknown => {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (value && typeof value === 'object') {
    return Object.keys(value as Record<string, unknown>)
      .sort()
      .reduce<Record<string, unknown>>((result, key) => {
        result[key] = canonicalize((value as Record<string, unknown>)[key]);
        return result;
      }, {});
  }
  return value;
};

export const hashJson = (value: unknown) => hash(JSON.stringify(canonicalize(value)));
export const calculateAuditRecordHash = (payloadHash: string, previousHash: string) =>
  hashJson({ chainVersion: CHAIN_VERSION, payloadHash, previousHash });

const hashPrivateValue = (label: string, value: string | number | null | undefined) => {
  if (value === null || value === undefined || value === '') return null;
  return hash(`${auditSalt}:${label}:${String(value)}`);
};

const hashTraceCodes = (traceCodes: string[]) => {
  const hashes = traceCodes
    .filter(Boolean)
    .map((traceCode) => hashPrivateValue('trace_code', traceCode))
    .filter((traceCodeHash): traceCodeHash is string => Boolean(traceCodeHash))
    .sort();
  return hashes.length > 0 ? hashJson(hashes) : null;
};

const ensureColumn = async (conn: any, table: string, column: string, definition: string) => {
  const [rows] = await conn.query(
    `SELECT COUNT(*) AS total FROM information_schema.COLUMNS
     WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ? AND COLUMN_NAME = ?`,
    [table, column]
  );
  if (Number(rows[0]?.total || 0) === 0) {
    await conn.query(`ALTER TABLE ${table} ADD COLUMN ${column} ${definition}`);
  }
};

export const ensureAuditChainTable = async (conn: any) => {
  if (auditSchemaReady) return;
  await conn.query(`
    CREATE TABLE IF NOT EXISTS audit_chain_records (
      id BIGINT NOT NULL AUTO_INCREMENT,
      event_type VARCHAR(50) NOT NULL,
      entity_type VARCHAR(50) NOT NULL,
      entity_id VARCHAR(100) NOT NULL,
      trace_code_hash CHAR(64) NULL,
      prescription_hash CHAR(64) NULL,
      operator_hash CHAR(64) NULL,
      flow_status VARCHAR(50) NOT NULL,
      event_time DATETIME NOT NULL,
      payload_json TEXT NOT NULL,
      payload_hash CHAR(64) NOT NULL,
      previous_hash CHAR(64) NOT NULL,
      current_hash CHAR(64) NOT NULL,
      snapshot_json LONGTEXT NULL,
      snapshot_hash CHAR(64) NULL,
      change_id BIGINT NULL,
      created_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (id),
      UNIQUE INDEX uk_current_hash (current_hash),
      INDEX idx_event_type (event_type),
      INDEX idx_entity (entity_type, entity_id),
      INDEX idx_event_time (event_time)
    ) ENGINE = InnoDB DEFAULT CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci
  `);

  // 兼容已有 v1 表，首次启动时原地补列，不删除历史记录。
  await ensureColumn(conn, 'audit_chain_records', 'snapshot_json', 'LONGTEXT NULL AFTER current_hash');
  await ensureColumn(conn, 'audit_chain_records', 'snapshot_hash', 'CHAR(64) NULL AFTER snapshot_json');
  await ensureColumn(conn, 'audit_chain_records', 'change_id', 'BIGINT NULL AFTER snapshot_hash');

  await conn.query(`
    CREATE TABLE IF NOT EXISTS audit_chain_changes (
      id BIGINT NOT NULL AUTO_INCREMENT,
      prescription_id INT NOT NULL,
      prescription_code VARCHAR(100) NULL,
      change_type VARCHAR(30) NOT NULL DEFAULT 'updated',
      old_snapshot_json LONGTEXT NOT NULL,
      new_snapshot_json LONGTEXT NOT NULL,
      changes_json LONGTEXT NOT NULL,
      old_snapshot_hash CHAR(64) NOT NULL,
      new_snapshot_hash CHAR(64) NOT NULL,
      actor_id INT NULL,
      actor_name VARCHAR(100) NULL,
      actor_source VARCHAR(100) NOT NULL DEFAULT 'database_direct',
      ai_analysis MEDIUMTEXT NULL,
      ai_status VARCHAR(30) NOT NULL DEFAULT 'pending',
      status VARCHAR(30) NOT NULL DEFAULT 'pending',
      detected_at DATETIME NOT NULL,
      accepted_at DATETIME NULL,
      accepted_by INT NULL,
      PRIMARY KEY (id),
      INDEX idx_change_prescription (prescription_id, status),
      INDEX idx_change_detected (detected_at)
    ) ENGINE = InnoDB DEFAULT CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci
  `);
  await ensureColumn(conn, 'audit_chain_changes', 'change_type', "VARCHAR(30) NOT NULL DEFAULT 'updated' AFTER prescription_code");
  auditSchemaReady = true;
};

export const createPrescriptionDeletionChange = async (
  conn: any,
  prescriptionId: number,
  actor?: { id: number; name: string; source: string }
) => {
  await ensureAuditChainTable(conn);
  const [baselineRows] = await conn.query(
    `SELECT snapshot_json, snapshot_hash
     FROM audit_chain_records
     WHERE entity_type = 'prescription' AND entity_id = ?
       AND event_type IN ('NURSE_SCAN_CONFIRMED', 'PRESCRIPTION_COMPLETED') AND snapshot_hash IS NOT NULL
     ORDER BY id DESC LIMIT 1`,
    [String(prescriptionId)]
  );
  if (!baselineRows.length) return null;

  const [pendingRows] = await conn.query(
    `SELECT new_snapshot_json, new_snapshot_hash
     FROM audit_chain_changes
     WHERE prescription_id = ? AND status = 'pending'
     ORDER BY id DESC LIMIT 1`,
    [prescriptionId]
  );
  const previousJson = pendingRows[0]?.new_snapshot_json || baselineRows[0].snapshot_json;
  const previousHash = pendingRows[0]?.new_snapshot_hash || baselineRows[0].snapshot_hash;
  const previous = JSON.parse(previousJson) as PrescriptionSnapshot & { prescription: Record<string, unknown> };
  const deletedSnapshot = {
    prescription: { ...previous.prescription, deleted: true },
    items: [],
  };
  const deletedJson = JSON.stringify(canonicalize(deletedSnapshot));
  const deletedHash = hash(deletedJson);
  const [existing] = await conn.query(
    `SELECT id FROM audit_chain_changes
     WHERE prescription_id = ? AND new_snapshot_hash = ? AND status = 'pending' LIMIT 1`,
    [prescriptionId, deletedHash]
  );
  if (existing.length) return Number(existing[0].id);

  const [result] = await conn.query(
    `INSERT INTO audit_chain_changes
     (prescription_id, prescription_code, change_type, old_snapshot_json, new_snapshot_json, changes_json,
      old_snapshot_hash, new_snapshot_hash, actor_id, actor_name, actor_source, detected_at)
     VALUES (?, ?, 'deleted', ?, ?, ?, ?, ?, ?, ?, ?, NOW())`,
    [prescriptionId, String(previous.prescription.prescription_code || '') || null,
      previousJson, deletedJson,
      JSON.stringify([{ field: 'prescription', before: previous.prescription, after: null }]),
      previousHash, deletedHash, actor?.id || null, actor?.name || null,
      actor?.source || '数据库直接删除（无应用层身份）']
  );
  return Number((result as any).insertId);
};

export const buildPrescriptionSnapshot = async (conn: any, prescriptionId: number): Promise<PrescriptionSnapshot | null> => {
  const [prescriptions] = await conn.query(
    `SELECT id, prescription_code, patient_id, doctor_id, diagnosis, note, prescription_type,
            payment_type, medical_record_no, department, bed_no, total_amount
     FROM prescriptions WHERE id = ?`,
    [prescriptionId]
  );
  if (prescriptions.length === 0) return null;

  const [items] = await conn.query(
    `SELECT pi.id, pi.medicine_id, m.name AS medicine_name, m.specification,
            pi.drug_form, pi.dosage, pi.usage_method, pi.frequency, pi.days,
            pi.quantity, pi.note, tc.trace_code
     FROM prescription_items pi
     LEFT JOIN medicines m ON m.id = pi.medicine_id
     LEFT JOIN prescription_trace_codes ptc ON ptc.prescription_item_id = pi.id
     LEFT JOIN medicine_trace_codes tc ON tc.id = ptc.trace_code_id
     WHERE pi.prescription_id = ?
     ORDER BY pi.id ASC, tc.id ASC`,
    [prescriptionId]
  );

  const normalize = (row: Record<string, unknown>) => Object.fromEntries(
    Object.entries(row).map(([key, value]) => [key, value instanceof Date ? formatDateForMysql(value) : value])
  );
  return { prescription: normalize(prescriptions[0]), items: items.map(normalize) };
};

export const appendAuditRecord = async (conn: any, input: AuditRecordInput) => {
  await ensureAuditChainTable(conn);
  const eventTime = formatDateForMysql(new Date());
  const traceCodeHash = input.traceCodes ? hashTraceCodes(input.traceCodes) : null;
  const prescriptionHash = hashPrivateValue('prescription', `${input.prescriptionId}:${input.prescriptionCode || ''}`);
  const snapshotJson = input.snapshot ? JSON.stringify(canonicalize(input.snapshot)) : null;
  const snapshotHash = snapshotJson ? hash(snapshotJson) : null;
  const payload: AuditPayload = {
    eventTime, eventType: input.eventType, entityId: String(input.entityId), entityType: input.entityType,
    flowStatus: input.flowStatus, operatorHash: hashPrivateValue('operator', input.operatorId),
    prescriptionHash, traceCodeHash,
    ...(snapshotHash ? { snapshotHash } : {}),
    ...(input.changeId ? { changeId: input.changeId } : {}),
  };
  const payloadJson = JSON.stringify(canonicalize(payload));
  const payloadHash = hash(payloadJson);

  const [lastRows] = await conn.query('SELECT current_hash FROM audit_chain_records ORDER BY id DESC LIMIT 1 FOR UPDATE');
  const previousHash = lastRows[0]?.current_hash || GENESIS_HASH;
  const currentHash = calculateAuditRecordHash(payloadHash, previousHash);
  const [result] = await conn.query(
    `INSERT INTO audit_chain_records
     (event_type, entity_type, entity_id, trace_code_hash, prescription_hash, operator_hash,
      flow_status, event_time, payload_json, payload_hash, previous_hash, current_hash,
      snapshot_json, snapshot_hash, change_id)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    [input.eventType, input.entityType, String(input.entityId), traceCodeHash, prescriptionHash,
      payload.operatorHash, input.flowStatus, eventTime, payloadJson, payloadHash, previousHash,
      currentHash, snapshotJson, snapshotHash, input.changeId || null]
  );
  return { id: Number((result as any).insertId), currentHash, previousHash, payloadHash };
};

const eventExists = async (conn: any, prescriptionId: number, eventType: AuditEventType) => {
  const [rows] = await conn.query(
    `SELECT id FROM audit_chain_records
     WHERE entity_type = 'prescription' AND entity_id = ? AND event_type = ? LIMIT 1`,
    [String(prescriptionId), eventType]
  );
  return rows.length > 0;
};

/** 第一次扫码完成生成药师确认节点，第二次扫码完成生成护士复核节点。 */
export const appendCompletedScanStages = async (conn: any, prescriptionId: number, operatorId?: number | null) => {
  await ensureAuditChainTable(conn);
  const [counts] = await conn.query(
    `SELECT
       (SELECT COALESCE(SUM(quantity), 0) FROM prescription_items WHERE prescription_id = ?) AS total,
       (SELECT COUNT(*)
        FROM prescription_trace_codes ptc
        JOIN medicine_trace_codes tc ON tc.id = ptc.trace_code_id
        WHERE ptc.prescription_id = ? AND tc.status IN ('scanned_outbound', 'scanned_confirm')) AS pharmacist_done,
       (SELECT COUNT(*)
        FROM prescription_trace_codes ptc
        JOIN medicine_trace_codes tc ON tc.id = ptc.trace_code_id
        WHERE ptc.prescription_id = ? AND tc.status = 'scanned_confirm') AS nurse_done`,
    [prescriptionId, prescriptionId, prescriptionId]
  );
  const total = Number(counts[0]?.total || 0);
  if (total === 0) return;
  const snapshot = await buildPrescriptionSnapshot(conn, prescriptionId);
  if (!snapshot) return;
  const prescriptionCode = String(snapshot.prescription.prescription_code || '');
  const traceCodes = snapshot.items.map((item) => String(item.trace_code || '')).filter(Boolean);

  if (Number(counts[0]?.pharmacist_done || 0) === total && !(await eventExists(conn, prescriptionId, 'PHARMACIST_SCAN_CONFIRMED'))) {
    await appendAuditRecord(conn, {
      eventType: 'PHARMACIST_SCAN_CONFIRMED', entityType: 'prescription', entityId: prescriptionId,
      flowStatus: 'pharmacist_confirmed', traceCodes, prescriptionId, prescriptionCode, operatorId, snapshot,
    });
  }
  if (Number(counts[0]?.nurse_done || 0) === total) {
    if (!(await eventExists(conn, prescriptionId, 'NURSE_SCAN_CONFIRMED'))) {
      await appendAuditRecord(conn, {
        eventType: 'NURSE_SCAN_CONFIRMED', entityType: 'prescription', entityId: prescriptionId,
        flowStatus: 'nurse_confirmed', traceCodes, prescriptionId, prescriptionCode, operatorId, snapshot,
      });
    }
  }
};

export const verifyAuditChain = async (conn: any) => {
  await ensureAuditChainTable(conn);
  const [rows] = await conn.query(
    `SELECT id, event_type, entity_type, entity_id, trace_code_hash, prescription_hash,
            operator_hash, flow_status, DATE_FORMAT(event_time, '%Y-%m-%d %H:%i:%s') AS event_time,
            payload_hash, previous_hash, current_hash, snapshot_hash, change_id
     FROM audit_chain_records ORDER BY id ASC`
  );
  let previousHash = GENESIS_HASH;
  for (const row of rows) {
    const payload: AuditPayload = {
      eventTime: row.event_time, eventType: row.event_type, entityId: String(row.entity_id),
      entityType: row.entity_type, flowStatus: row.flow_status, operatorHash: row.operator_hash,
      prescriptionHash: row.prescription_hash, traceCodeHash: row.trace_code_hash,
      ...(row.snapshot_hash ? { snapshotHash: row.snapshot_hash } : {}),
      ...(row.change_id ? { changeId: Number(row.change_id) } : {}),
    };
    const payloadHash = hash(JSON.stringify(canonicalize(payload)));
    const chainVersion = row.snapshot_hash ? CHAIN_VERSION : 'local-audit-chain-v1';
    const currentHash = hashJson({ chainVersion, payloadHash, previousHash });
    if (row.previous_hash !== previousHash || row.payload_hash !== payloadHash || row.current_hash !== currentHash) {
      return { valid: false, total: rows.length, broken_at: row.id,
        expected_previous_hash: previousHash, actual_previous_hash: row.previous_hash };
    }
    previousHash = row.current_hash;
  }
  return { valid: true, total: rows.length, last_hash: previousHash };
};

/** 仅供 test 账号重置本人的测试处方使用：移除该处方节点后重算剩余链，保持哈希链可校验。 */
export const purgeTestPrescriptionAudit = async (conn: any, prescriptionId: number) => {
  await conn.query('DELETE FROM audit_chain_changes WHERE prescription_id = ?', [prescriptionId]);
  const [removed] = await conn.query(
    "DELETE FROM audit_chain_records WHERE entity_type = 'prescription' AND entity_id = ?",
    [String(prescriptionId)]
  );
  const [rows] = await conn.query(
    'SELECT id, payload_hash, snapshot_hash FROM audit_chain_records ORDER BY id ASC FOR UPDATE'
  );
  let previousHash = GENESIS_HASH;
  for (const row of rows) {
    const chainVersion = row.snapshot_hash ? CHAIN_VERSION : 'local-audit-chain-v1';
    const currentHash = hashJson({ chainVersion, payloadHash: row.payload_hash, previousHash });
    await conn.query(
      'UPDATE audit_chain_records SET previous_hash = ?, current_hash = ? WHERE id = ?',
      [previousHash, currentHash, row.id]
    );
    previousHash = currentHash;
  }
  return Number(removed.affectedRows || 0);
};
