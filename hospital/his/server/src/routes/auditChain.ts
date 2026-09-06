import { Router, Request, Response } from 'express';
import pool from '../db';
import { authMiddleware } from '../middleware/auth';
import {
  appendAuditRecord,
  buildPrescriptionSnapshot,
  calculateAuditRecordHash,
  canonicalize,
  ensureAuditChainTable,
  hash,
  hashJson,
  type PrescriptionSnapshot,
  verifyAuditChain,
} from '../services/auditChain';
import { analyzePrescriptionChange } from '../services/changeAnalysis';

const router = Router();
router.use(authMiddleware);

type Attribution = { prescriptionId: number; actorId: number; actorName: string; actorSource: string };
type SnapshotDiff = { field: string; before: unknown; after: unknown };

const parseJson = <T>(value: string): T => JSON.parse(value) as T;

const diffValues = (before: unknown, after: unknown, path = ''): SnapshotDiff[] => {
  if (JSON.stringify(canonicalize(before)) === JSON.stringify(canonicalize(after))) return [];
  if (Array.isArray(before) && Array.isArray(after)) {
    const result: SnapshotDiff[] = [];
    const total = Math.max(before.length, after.length);
    for (let index = 0; index < total; index += 1) {
      result.push(...diffValues(before[index], after[index], `${path}[${index}]`));
    }
    return result;
  }
  if (before && after && typeof before === 'object' && typeof after === 'object') {
    const keys = new Set([...Object.keys(before as object), ...Object.keys(after as object)]);
    return Array.from(keys).flatMap((key) => diffValues(
      (before as Record<string, unknown>)[key],
      (after as Record<string, unknown>)[key],
      path ? `${path}.${key}` : key
    ));
  }
  return [{ field: path || 'root', before: before ?? null, after: after ?? null }];
};

const serializeChange = (row: any) => ({
  ...row,
  changes: parseJson<SnapshotDiff[]>(row.changes_json),
  old_snapshot: parseJson<PrescriptionSnapshot>(row.old_snapshot_json),
  new_snapshot: parseJson<PrescriptionSnapshot>(row.new_snapshot_json),
});

async function serializeChangeWithBranches(conn: any, row: any) {
  const change = serializeChange(row);
  if (row.status !== 'pending') return change;

  const [baselineRows] = await conn.query(
    `SELECT id, current_hash FROM audit_chain_records
     WHERE entity_type = 'prescription' AND entity_id = ?
       AND event_type = 'PRESCRIPTION_COMPLETED' AND snapshot_hash = ?
     ORDER BY id DESC LIMIT 1`,
    [String(row.prescription_id), row.old_snapshot_hash]
  );
  if (!baselineRows.length) return { ...change, baseline_record_id: null, base_continuation_records: [], branch_records: [] };

  const baseline = baselineRows[0];
  const [continuationRows] = await conn.query(
    `SELECT id, event_type, entity_type, entity_id, trace_code_hash, prescription_hash,
            operator_hash, flow_status, event_time, payload_hash, previous_hash, current_hash,
            snapshot_hash, change_id, created_at
     FROM audit_chain_records WHERE id > ? ORDER BY id ASC`,
    [baseline.id]
  );

  let previousHash = String(baseline.current_hash);
  const makeBranchRecord = (
    kind: 'change' | 'completion' | 'continuation',
    eventType: string,
    eventTime: unknown,
    payloadHash: string,
    entityId: string,
    sourceRecordId: number | null = null
  ) => {
    const currentHash = calculateAuditRecordHash(payloadHash, previousHash);
    const record = {
      kind,
      source_record_id: sourceRecordId,
      event_type: eventType,
      entity_id: entityId,
      event_time: eventTime,
      payload_hash: payloadHash,
      previous_hash: previousHash,
      current_hash: currentHash,
    };
    previousHash = currentHash;
    return record;
  };

  const changeEventType = row.change_type === 'deleted' ? 'DATA_DELETED' : 'DATA_CHANGED';
  const changedPayloadHash = hashJson({
    branchVersion: 'local-audit-branch-v1',
    changeId: Number(row.id),
    eventType: changeEventType,
    prescriptionId: Number(row.prescription_id),
    snapshotHash: row.new_snapshot_hash,
  });
  const completionPayloadHash = hashJson({
    branchVersion: 'local-audit-branch-v1',
    changeId: Number(row.id),
    eventType: 'PRESCRIPTION_COMPLETED',
    prescriptionId: Number(row.prescription_id),
    snapshotHash: row.new_snapshot_hash,
  });
  const branchRecords = [
    makeBranchRecord('change', changeEventType, row.detected_at, changedPayloadHash, String(row.prescription_id)),
    makeBranchRecord('completion', 'PRESCRIPTION_COMPLETED', row.detected_at, completionPayloadHash, String(row.prescription_id)),
    ...continuationRows.map((record: any) => makeBranchRecord(
      'continuation', record.event_type, record.event_time, record.payload_hash,
      String(record.entity_id), Number(record.id)
    )),
  ];

  return {
    ...change,
    baseline_record_id: Number(baseline.id),
    base_continuation_records: continuationRows,
    branch_records: branchRecords,
  };
}

async function inspectCompletedPrescriptions(conn: any, attribution?: Attribution) {
  await ensureAuditChainTable(conn);
  const [baselines] = await conn.query(
    `SELECT r.* FROM audit_chain_records r
     JOIN (
       SELECT entity_id, MAX(id) AS max_id
       FROM audit_chain_records
       WHERE event_type = 'PRESCRIPTION_COMPLETED' AND snapshot_hash IS NOT NULL
       GROUP BY entity_id
     ) latest ON latest.max_id = r.id`
  );
  const createdIds: number[] = [];

  for (const baseline of baselines) {
    const prescriptionId = Number(baseline.entity_id);
    const [latestPendingRows] = await conn.query(
      `SELECT new_snapshot_json, new_snapshot_hash
       FROM audit_chain_changes
       WHERE prescription_id = ? AND status = 'pending'
       ORDER BY id DESC LIMIT 1`,
      [prescriptionId]
    );
    const previousJson = latestPendingRows[0]?.new_snapshot_json || baseline.snapshot_json;
    const previousHash = latestPendingRows[0]?.new_snapshot_hash || baseline.snapshot_hash;
    const previous = parseJson<PrescriptionSnapshot>(previousJson);
    const current = await buildPrescriptionSnapshot(conn, prescriptionId);
    const comparisonSnapshot = current || {
      prescription: { ...previous.prescription, deleted: true },
      items: [],
    };
    const currentJson = JSON.stringify(canonicalize(comparisonSnapshot));
    const currentHash = hash(currentJson);
    if (currentHash === previousHash) continue;

    const [existing] = await conn.query(
      `SELECT id FROM audit_chain_changes
       WHERE prescription_id = ? AND new_snapshot_hash = ? AND status = 'pending' LIMIT 1`,
      [prescriptionId, currentHash]
    );
    if (existing.length > 0) continue;

    const changes = current
      ? diffValues(previous, comparisonSnapshot)
      : [{ field: 'prescription', before: previous.prescription, after: null }];
    const matchedAttribution = attribution?.prescriptionId === prescriptionId ? attribution : null;
    const [result] = await conn.query(
      `INSERT INTO audit_chain_changes
       (prescription_id, prescription_code, change_type, old_snapshot_json, new_snapshot_json, changes_json,
        old_snapshot_hash, new_snapshot_hash, actor_id, actor_name, actor_source, detected_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NOW())`,
      [prescriptionId, comparisonSnapshot.prescription.prescription_code || null, current ? 'updated' : 'deleted', previousJson, currentJson,
        JSON.stringify(changes), previousHash, currentHash, matchedAttribution?.actorId || null,
        matchedAttribution?.actorName || null,
        matchedAttribution?.actorSource || '数据库直接修改（无应用层身份）']
    );
    createdIds.push(Number((result as any).insertId));
  }
  return createdIds;
}

async function runAiAnalysis(changeId: number) {
  const [claim]: any = await pool.query(
    `UPDATE audit_chain_changes SET ai_status = 'running'
     WHERE id = ? AND ai_status IN ('pending', 'failed')`,
    [changeId]
  );
  if (!claim.affectedRows) return;
  try {
    const [rows] = await pool.query<any[]>('SELECT * FROM audit_chain_changes WHERE id = ?', [changeId]);
    if (!rows.length) return;
    const row = rows[0];
    const result = await analyzePrescriptionChange({
      prescriptionCode: row.prescription_code || `#${row.prescription_id}`,
      actorName: row.actor_name,
      actorSource: row.actor_source,
      changes: parseJson<SnapshotDiff[]>(row.changes_json),
    });
    await pool.query(
      'UPDATE audit_chain_changes SET ai_analysis = ?, ai_status = ? WHERE id = ?',
      [result.text, result.source === 'deepseek' ? 'completed' : 'rules_fallback', changeId]
    );
  } catch (error: any) {
    await pool.query(
      'UPDATE audit_chain_changes SET ai_analysis = ?, ai_status = ? WHERE id = ?',
      [`DeepSeek 分析失败：${error.message}`, 'failed', changeId]
    );
  }
}

router.get('/', async (req: Request, res: Response) => {
  try {
    const page = parseInt(req.query.page as string) || 1;
    const pageSize = Math.min(parseInt(req.query.pageSize as string) || 50, 100);
    const offset = (page - 1) * pageSize;
    await ensureAuditChainTable(pool);
    const [countRows] = await pool.query<any[]>('SELECT COUNT(*) AS total FROM audit_chain_records');
    const [list] = await pool.query(
      `SELECT id, event_type, entity_type, entity_id, trace_code_hash, prescription_hash,
              operator_hash, flow_status, event_time, payload_hash, previous_hash, current_hash,
              snapshot_hash, change_id, created_at
       FROM audit_chain_records ORDER BY id DESC LIMIT ? OFFSET ?`,
      [pageSize, offset]
    );
    res.json({ total: countRows[0]?.total || 0, page, pageSize, list });
  } catch (err: any) {
    res.status(500).json({ error: 'Server error: ' + err.message });
  }
});

router.get('/verify', async (_req: Request, res: Response) => {
  const conn = await pool.getConnection();
  try {
    res.json(await verifyAuditChain(conn));
  } catch (err: any) {
    res.status(500).json({ error: 'Server error: ' + err.message });
  } finally {
    conn.release();
  }
});

// 比对链上处方快照与当前数据库；新异常会自动启动 DeepSeek 分析。
router.post('/inspect', async (_req: Request, res: Response) => {
  const conn = await pool.getConnection();
  try {
    const createdIds = await inspectCompletedPrescriptions(conn);
    const [changes] = await conn.query<any[]>(
      `SELECT * FROM audit_chain_changes
       WHERE status IN ('pending', 'accepted')
       ORDER BY CASE WHEN status = 'pending' THEN 0 ELSE 1 END,
                CASE WHEN status = 'pending' THEN detected_at END ASC,
                CASE WHEN status = 'accepted' THEN detected_at END DESC
       LIMIT 20`
    );
    for (const row of changes) {
      if (row.status === 'pending' && ['pending', 'failed'].includes(row.ai_status)) void runAiAnalysis(Number(row.id));
    }
    const serializedChanges = await Promise.all(changes.map((row) => serializeChangeWithBranches(conn, row)));
    res.json({ changes: serializedChanges, created: createdIds.length });
  } catch (err: any) {
    res.status(500).json({ error: '完整性检查失败: ' + err.message });
  } finally {
    conn.release();
  }
});

router.post('/changes/:id/analyze', async (req: Request, res: Response) => {
  const id = Number(req.params.id);
  try {
    await pool.query("UPDATE audit_chain_changes SET ai_status = 'pending' WHERE id = ?", [id]);
    await runAiAnalysis(id);
    const [rows] = await pool.query<any[]>('SELECT * FROM audit_chain_changes WHERE id = ?', [id]);
    if (!rows.length) {
      res.status(404).json({ error: '未找到数据变更记录' });
      return;
    }
    res.json(serializeChange(rows[0]));
  } catch (err: any) {
    res.status(500).json({ error: 'AI 分析失败: ' + err.message });
  }
});

router.post('/changes/:id/accept', async (req: Request, res: Response) => {
  if (req.user?.role !== 'admin' && req.user?.username !== 'test') {
    res.status(403).json({ error: '仅管理员或测试账号可以同步差异分支' });
    return;
  }
  const conn = await pool.getConnection();
  try {
    const id = Number(req.params.id);
    await conn.beginTransaction();
    const [rows]: any = await conn.query('SELECT * FROM audit_chain_changes WHERE id = ? FOR UPDATE', [id]);
    if (!rows.length || rows[0].status !== 'pending') {
      await conn.rollback();
      res.status(400).json({ error: '该变更不存在或已处理' });
      return;
    }
    const change = rows[0];
    const [olderRows] = await conn.query<any[]>(
      `SELECT id FROM audit_chain_changes
       WHERE status = 'pending' AND (detected_at < ? OR (detected_at = ? AND id < ?))
       ORDER BY detected_at ASC, id ASC LIMIT 1 FOR UPDATE`,
      [change.detected_at, change.detected_at, id]
    );
    if (olderRows.length) {
      await conn.rollback();
      res.status(409).json({ error: `存在更早的差异分支 #${olderRows[0].id}，请先完成最老分支` });
      return;
    }
    const snapshot = parseJson<PrescriptionSnapshot>(change.new_snapshot_json);
    const current = await buildPrescriptionSnapshot(conn, Number(change.prescription_id));
    const [newerSamePrescription] = await conn.query<any[]>(
      `SELECT id FROM audit_chain_changes
       WHERE prescription_id = ? AND status = 'pending' AND id > ? LIMIT 1`,
      [change.prescription_id, id]
    );
    const currentMatches = current && hash(JSON.stringify(canonicalize(current))) === change.new_snapshot_hash;
    const deletionMatches = change.change_type === 'deleted' && !current;
    if (!currentMatches && !deletionMatches && !newerSamePrescription.length) {
      await conn.rollback();
      res.status(409).json({ error: '数据库内容再次变化，请重新检测后再更新链' });
      return;
    }
    const traceCodes = snapshot.items.map((item) => String(item.trace_code || '')).filter(Boolean);
    await appendAuditRecord(conn, {
      eventType: change.change_type === 'deleted' ? 'DATA_DELETED' : 'DATA_CHANGED', entityType: 'prescription', entityId: change.prescription_id,
      flowStatus: change.change_type === 'deleted' ? 'deletion_accepted' : 'change_accepted', traceCodes, prescriptionId: change.prescription_id,
      prescriptionCode: change.prescription_code, operatorId: req.user!.id, snapshot, changeId: id,
    });
    await appendAuditRecord(conn, {
      eventType: 'PRESCRIPTION_COMPLETED', entityType: 'prescription', entityId: change.prescription_id,
      flowStatus: 'prescription_recompleted', traceCodes, prescriptionId: change.prescription_id,
      prescriptionCode: change.prescription_code, operatorId: req.user!.id, snapshot, changeId: id,
    });
    await conn.query(
      "UPDATE audit_chain_changes SET status = 'accepted', accepted_at = NOW(), accepted_by = ? WHERE id = ?",
      [req.user!.id, id]
    );
    await conn.commit();
    res.json({ message: '新数据链已设为活动链，原链仍保留用于追责' });
  } catch (err: any) {
    await conn.rollback();
    res.status(500).json({ error: '更新区块链失败: ' + err.message });
  } finally {
    conn.release();
  }
});

// 比赛演示入口：admin 与 test 拥有相同的演示权限。
router.post('/demo/tamper', async (req: Request, res: Response) => {
  const isTestUser = req.user?.username === 'test';
  if (req.user?.role !== 'admin' && !isTestUser) {
    res.status(403).json({ error: '仅管理员或测试账号可以制造数量篡改' });
    return;
  }

  const conn = await pool.getConnection();
  try {
    await ensureAuditChainTable(conn);
    const requestedId = Number(req.body.prescription_id || 0);
    const queryParams: Array<string | number> = [];
    const requestedFilter = requestedId ? 'AND r.entity_id = ?' : '';
    if (requestedId) queryParams.push(String(requestedId));
    const [completed]: any = await conn.query(
      `SELECT r.entity_id FROM audit_chain_records r
       WHERE r.event_type = 'PRESCRIPTION_COMPLETED' AND r.snapshot_hash IS NOT NULL
       ${requestedFilter}
       ORDER BY r.id DESC LIMIT 1`,
      queryParams
    );
    if (!completed.length) {
      res.status(400).json({ error: '没有已完成且含快照的处方，请先完成两轮扫码' });
      return;
    }
    const prescriptionId = Number(completed[0].entity_id);
    await conn.beginTransaction();
    const [items]: any = await conn.query(
      'SELECT id, quantity FROM prescription_items WHERE prescription_id = ? ORDER BY id LIMIT 1 FOR UPDATE',
      [prescriptionId]
    );
    if (!items.length) {
      await conn.rollback();
      res.status(400).json({ error: '处方中没有药品明细' });
      return;
    }
    const before = Number(items[0].quantity || 0);
    const after = before + 1;
    await conn.query('UPDATE prescription_items SET quantity = ? WHERE id = ?', [after, items[0].id]);
    const created = await inspectCompletedPrescriptions(conn, {
      prescriptionId, actorId: req.user!.id, actorName: req.user!.real_name,
      actorSource: '比赛演示入口（已登录账号）',
    });
    await conn.commit();
    for (const id of created) void runAiAnalysis(id);
    res.json({ prescription_id: prescriptionId, item_id: items[0].id, before, after, change_id: created[0] });
  } catch (err: any) {
    await conn.rollback();
    res.status(500).json({ error: '演示数据修改失败: ' + err.message });
  } finally {
    conn.release();
  }
});

router.delete('/', async (req: Request, res: Response) => {
  if (req.user?.role !== 'admin' && req.user?.username !== 'test') {
    res.status(403).json({ error: '仅管理员或测试账号可以清空测试链' });
    return;
  }
  const conn = await pool.getConnection();
  try {
    await ensureAuditChainTable(conn);
    await conn.beginTransaction();
    await conn.query('DELETE FROM audit_chain_changes');
    await conn.query('DELETE FROM audit_chain_records');
    await conn.commit();
    res.json({ message: '测试区块链及变更分析已清空，处方业务数据未删除' });
  } catch (err: any) {
    await conn.rollback();
    res.status(500).json({ error: '清空区块链失败: ' + err.message });
  } finally {
    conn.release();
  }
});

export default router;
