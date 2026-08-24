import crypto from 'crypto';

const GENESIS_HASH = '0'.repeat(64);
const CHAIN_VERSION = 'local-audit-chain-v1';

type AuditEventType =
  | 'DRUG_INBOUND'
  | 'PRESCRIPTION_CREATED'
  | 'DRUG_OUTBOUND'
  | 'NURSE_RECEIVED';

type AuditRecordInput = {
  eventType: AuditEventType;
  entityType: 'trace_code' | 'prescription';
  entityId: number | string;
  flowStatus: string;
  traceCode?: string | null;
  traceCodes?: string[];
  prescriptionId?: number | string | null;
  prescriptionCode?: string | null;
  operatorId?: number | string | null;
};

type AuditPayload = {
  eventTime: string;
  eventType: AuditEventType;
  entityId: string;
  entityType: 'trace_code' | 'prescription';
  flowStatus: string;
  operatorHash: string | null;
  prescriptionHash: string | null;
  traceCodeHash: string | null;
};

const auditSalt = process.env.AUDIT_HASH_SALT || 'his-local-audit-salt';

const hash = (value: string) => crypto.createHash('sha256').update(value).digest('hex');

const formatDateForMysql = (date: Date) => {
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
};

const canonicalize = (value: unknown): unknown => {
  if (Array.isArray(value)) {
    return value.map(canonicalize);
  }
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

const hashJson = (value: unknown) => hash(JSON.stringify(canonicalize(value)));

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

export const ensureAuditChainTable = async (conn: any) => {
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
      created_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (id),
      UNIQUE INDEX uk_current_hash (current_hash),
      INDEX idx_event_type (event_type),
      INDEX idx_entity (entity_type, entity_id),
      INDEX idx_event_time (event_time)
    ) ENGINE = InnoDB DEFAULT CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci
  `);
};

export const appendAuditRecord = async (conn: any, input: AuditRecordInput) => {
  await ensureAuditChainTable(conn);

  const eventTime = formatDateForMysql(new Date());
  const traceCodeHash = input.traceCodes
    ? hashTraceCodes(input.traceCodes)
    : hashPrivateValue('trace_code', input.traceCode);
  const prescriptionHash = input.prescriptionId || input.prescriptionCode
    ? hashPrivateValue('prescription', `${input.prescriptionId || ''}:${input.prescriptionCode || ''}`)
    : null;

  const payload: AuditPayload = {
    eventTime,
    eventType: input.eventType,
    entityId: String(input.entityId),
    entityType: input.entityType,
    flowStatus: input.flowStatus,
    operatorHash: hashPrivateValue('operator', input.operatorId),
    prescriptionHash,
    traceCodeHash,
  };
  const payloadJson = JSON.stringify(canonicalize(payload));
  const payloadHash = hash(payloadJson);

  const [lastRows] = await conn.query(
    'SELECT current_hash FROM audit_chain_records ORDER BY id DESC LIMIT 1 FOR UPDATE'
  );
  const previousHash = lastRows[0]?.current_hash || GENESIS_HASH;
  const currentHash = hashJson({
    chainVersion: CHAIN_VERSION,
    payloadHash,
    previousHash,
  });

  await conn.query(
    `INSERT INTO audit_chain_records
     (event_type, entity_type, entity_id, trace_code_hash, prescription_hash, operator_hash,
      flow_status, event_time, payload_json, payload_hash, previous_hash, current_hash)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    [
      input.eventType,
      input.entityType,
      String(input.entityId),
      payload.traceCodeHash,
      payload.prescriptionHash,
      payload.operatorHash,
      input.flowStatus,
      eventTime,
      payloadJson,
      payloadHash,
      previousHash,
      currentHash,
    ]
  );

  return { currentHash, previousHash, payloadHash };
};

export const verifyAuditChain = async (conn: any) => {
  await ensureAuditChainTable(conn);
  const [rows] = await conn.query(
    `SELECT id, event_type, entity_type, entity_id, trace_code_hash, prescription_hash,
            operator_hash, flow_status, DATE_FORMAT(event_time, '%Y-%m-%d %H:%i:%s') AS event_time,
            payload_hash, previous_hash, current_hash
     FROM audit_chain_records
     ORDER BY id ASC`
  );

  let previousHash = GENESIS_HASH;
  for (const row of rows) {
    const payload: AuditPayload = {
      eventTime: row.event_time,
      eventType: row.event_type,
      entityId: String(row.entity_id),
      entityType: row.entity_type,
      flowStatus: row.flow_status,
      operatorHash: row.operator_hash,
      prescriptionHash: row.prescription_hash,
      traceCodeHash: row.trace_code_hash,
    };
    const payloadHash = hash(JSON.stringify(canonicalize(payload)));
    const currentHash = hashJson({
      chainVersion: CHAIN_VERSION,
      payloadHash,
      previousHash,
    });

    if (row.previous_hash !== previousHash || row.payload_hash !== payloadHash || row.current_hash !== currentHash) {
      return {
        valid: false,
        total: rows.length,
        broken_at: row.id,
        expected_previous_hash: previousHash,
        actual_previous_hash: row.previous_hash,
      };
    }

    previousHash = row.current_hash;
  }

  return {
    valid: true,
    total: rows.length,
    last_hash: previousHash,
  };
};
