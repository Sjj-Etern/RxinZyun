import { Router, Request, Response } from 'express';
import pool from '../db';
import { authMiddleware } from '../middleware/auth';
import { appendAuditRecord } from '../services/auditChain';
import http from 'http';

const router = Router();
router.use(authMiddleware);

// GET /api/medicine-trace-codes — list with pagination, filterable by medicine_id
router.get('/', async (req: Request, res: Response) => {
  try {
    const page = parseInt(req.query.page as string) || 1;
    const pageSize = parseInt(req.query.pageSize as string) || 10;
    const medicineId = parseInt(req.query.medicine_id as string);
    const offset = (page - 1) * pageSize;

    let countSql = 'SELECT COUNT(*) as total FROM medicine_trace_codes tc';
    let listSql = `SELECT tc.*, u1.real_name AS scan1_user_name, u2.real_name AS scan2_user_name, u3.real_name AS scan3_user_name
      FROM medicine_trace_codes tc
      LEFT JOIN users u1 ON tc.scan1_user_id = u1.id
      LEFT JOIN users u2 ON tc.scan2_user_id = u2.id
      LEFT JOIN users u3 ON tc.scan3_user_id = u3.id`;
    const params: any[] = [];

    if (!isNaN(medicineId)) {
      const where = ' WHERE tc.medicine_id = ?';
      countSql += where;
      listSql += where;
      params.push(medicineId);
    }

    listSql += ' ORDER BY COALESCE(tc.scan3_time, tc.scan2_time, tc.scan1_time, tc.created_at) DESC, tc.id ASC LIMIT ? OFFSET ?';

    const [countRows] = await pool.query<any[]>(countSql, params);
    const total = (countRows[0] as any)?.total || 0;

    const listParams = [...params, pageSize, offset];
    const [rows] = await pool.query(listSql, listParams);

    res.json({ total, page, pageSize, list: rows });
  } catch (err: any) {
    res.status(500).json({ error: '服务器错误: ' + err.message });
  }
});

// 药品追溯码前缀映射（硬编码兜底，数据库表优先）
const MEDICINE_PREFIX_MAP: Record<string, string> = {
  '米索前列醇片': '8422747',
  '阿莫西林胶囊': '1730604',
  '康恩贝肠炎宁片': '8410131',
  '肠炎宁片': '8410131',
  '苏黄止咳胶囊': '8390696',
  '去痛片': '8341039',
  '奥美拉唑肠溶胶囊': '8169438',
  '奥美拉唑': '8169438',
  '蒙脱石散': '8425186',
  '元和正胃片': '8377024',
  '氨苄西林胶囊': '8340166',
};

// 从数据库查询所有前缀（优先），表不存在或为空时回退到硬编码
const getPrefixMap = async (conn: any): Promise<Map<number, string>> => {
  try {
    const [rows] = await conn.query('SELECT medicine_id, prefix FROM medicine_trace_prefixes');
    if (rows.length > 0) {
      return new Map(rows.map((r: any) => [r.medicine_id, r.prefix]));
    }
  } catch (_e) {
    // 表可能还没创建，回退到硬编码
  }
  // 回退：按药品名匹配硬编码前缀
  const [medicines] = await conn.query('SELECT id, name FROM medicines');
  const map = new Map<number, string>();
  for (const m of medicines) {
    if (MEDICINE_PREFIX_MAP[m.name]) {
      map.set(m.id, MEDICINE_PREFIX_MAP[m.name]);
    }
  }
  return map;
};

const randomTraceCode = (prefix?: string): string => {
  const chars = '0123456789';
  if (prefix) {
    // 前缀7位 + 随机13位 = 20位追溯码
    let code = prefix;
    for (let i = 0; i < 13; i++) {
      code += chars[Math.floor(Math.random() * chars.length)];
    }
    return code;
  }
  // 无前缀时全部随机20位
  let code = '';
  for (let i = 0; i < 20; i++) {
    code += chars[Math.floor(Math.random() * chars.length)];
  }
  return code;
};

const validatePrescriptionLink = (record: any, prescriptionId: number | null, res: Response): boolean => {
  const linkedPrescriptionId = record.prescription_id ? Number(record.prescription_id) : null;

  if (!linkedPrescriptionId) {
    res.status(400).json({ error: '该追溯码未关联处方，不能扫码' });
    return false;
  }

  if (prescriptionId && linkedPrescriptionId !== prescriptionId) {
    res.status(400).json({ error: '该追溯码不属于当前处方' });
    return false;
  }

  return true;
};

const getTraceCodeCandidates = (value: unknown): string[] => {
  const raw = String(value || '').trim();
  if (!raw) return [];

  const candidates = new Set<string>([raw]);

  try {
    const decoded = decodeURIComponent(raw);
    if (decoded) candidates.add(decoded.trim());
  } catch (_e) {}

  try {
    const url = new URL(raw);
    ['trace_code', 'traceCode', 'code', 'c'].forEach((key) => {
      const paramValue = url.searchParams.get(key);
      if (paramValue) candidates.add(paramValue.trim());
    });
  } catch (_e) {}

  for (const text of Array.from(candidates)) {
    const compact = text.replace(/[\s-]/g, '');
    if (/^\d{20,}$/.test(compact)) {
      candidates.add(compact);
    }
    const digitMatches = text.match(/\d{20,}/g) || [];
    for (const match of digitMatches) {
      candidates.add(match);
    }
  }

  return Array.from(candidates).filter(Boolean);
};

const findTraceCodeByInput = async (traceCodeInput: unknown) => {
  const candidates = getTraceCodeCandidates(traceCodeInput);
  if (candidates.length === 0) return null;

  const placeholders = candidates.map(() => '?').join(', ');
  const [rows] = await pool.query<any[]>(
    `SELECT * FROM medicine_trace_codes WHERE trace_code IN (${placeholders})`,
    candidates
  );

  return rows[0] || null;
};

const getNormalizedTraceCode = (traceCodeInput: unknown) => {
  const candidates = getTraceCodeCandidates(traceCodeInput);
  return candidates.find((candidate) => /^\d{7,}$/.test(candidate)) || candidates[0] || '';
};

const findTraceCodeByInputForUpdate = async (conn: any, traceCodeInput: unknown) => {
  const candidates = getTraceCodeCandidates(traceCodeInput);
  if (candidates.length === 0) return null;

  const placeholders = candidates.map(() => '?').join(', ');
  const [rows] = await conn.query(
    `SELECT tc.*, m.name AS medicine_name, m.specification, m.manufacturer,
            m.drug_form, m.unit, m.price
     FROM medicine_trace_codes tc
     JOIN medicines m ON tc.medicine_id = m.id
     WHERE tc.trace_code IN (${placeholders})
     FOR UPDATE`,
    candidates
  );

  return rows[0] || null;
};

const createOtherMedicine = async (conn: any, prefix: string) => {
  const [result] = await conn.query(
    `INSERT INTO medicines
     (name, generic_name, specification, drug_form, manufacturer, unit, price, stock, category, is_narcotic, image_url)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    ['其他', '其他', null, null, null, '盒', 0, 1, '处方药', 0, null]
  );
  const medicineId = result.insertId;
  await conn.query(
    'INSERT INTO medicine_trace_prefixes (medicine_id, prefix) VALUES (?, ?)',
    [medicineId, prefix]
  );
  return medicineId;
};

const ensureTraceCodeRecordForScan = async (conn: any, traceCodeInput: unknown) => {
  const existing = await findTraceCodeByInputForUpdate(conn, traceCodeInput);
  if (existing) return { record: existing, created: false };

  const traceCode = getNormalizedTraceCode(traceCodeInput);
  if (!/^\d{7,}$/.test(traceCode)) {
    throw Object.assign(new Error('追溯码至少需要包含7位数字'), { status: 400 });
  }

  const prefix = traceCode.slice(0, 7);
  const [prefixRows] = await conn.query(
    `SELECT p.medicine_id
     FROM medicine_trace_prefixes p
     WHERE p.prefix = ?
     LIMIT 1
     FOR UPDATE`,
    [prefix]
  );

  const medicineId = prefixRows.length > 0
    ? prefixRows[0].medicine_id
    : await createOtherMedicine(conn, prefix);

  if (prefixRows.length > 0) {
    await conn.query('UPDATE medicines SET stock = COALESCE(stock, 0) + 1 WHERE id = ?', [medicineId]);
  }

  await conn.query(
    'INSERT INTO medicine_trace_codes (medicine_id, trace_code) VALUES (?, ?)',
    [medicineId, traceCode]
  );

  const record = await findTraceCodeByInputForUpdate(conn, traceCode);
  return { record, created: true };
};

// ===== 节点3扫码复核完成 → 通知医院后端触发车2 pharmacist-success =====
// 判断依据：处方所有追溯码均已扫到出库状态（status='scanned_outbound'，即节点3扫码结束）
// 由 HIS 扫码端点检测完成后，HTTP 通知后端 /workflow/pharmacist-success-trigger
// 后端按 .env 的 PHARMACIST_SUCCESS_DELAY 延迟后启动车2 pharmacist-success 连续发送
function notifyBackendNode3Completed(prescriptionCode: string): void {
  const base = process.env.HOSPITAL_BACKEND_URL || 'http://127.0.0.1:8080/api/v1';
  const target = new URL(`${base}/workflow/pharmacist-success-trigger`);
  const body = JSON.stringify({ prescription_code: prescriptionCode });
  const req = http.request({
    hostname: target.hostname,
    port: Number(target.port) || 80,
    path: target.pathname + target.search,
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) },
    timeout: 5000,
  }, (response) => {
    let raw = '';
    response.setEncoding('utf8');
    response.on('data', (c) => { raw += c; });
    response.on('end', () => {
      console.log(`[节点3完成通知] 后端响应 ${response.statusCode}: ${raw}`);
    });
  });
  req.on('error', (e) => console.error(`[节点3完成通知] 通知后端失败: ${e.message}`));
  req.on('timeout', () => { req.destroy(); console.error('[节点3完成通知] 通知后端超时'); });
  req.write(body);
  req.end();
}

// 检测该处方是否所有追溯码均已出库（节点3扫码结束），若是则通知后端
async function checkNode3CompletedAndNotify(conn: any, prescriptionId: number | null): Promise<void> {
  if (!prescriptionId) return;
  try {
    const [countRows] = await conn.query(
      `SELECT COUNT(*) AS pending FROM medicine_trace_codes WHERE prescription_id = ? AND status = 'pending'`,
      [prescriptionId]
    );
    const pending = countRows[0]?.pending || 0;
    if (pending !== 0) return; // 仍有未出库追溯码，节点3未结束

    const [totalRows] = await conn.query(
      `SELECT COUNT(*) AS total FROM medicine_trace_codes WHERE prescription_id = ?`,
      [prescriptionId]
    );
    const total = totalRows[0]?.total || 0;
    if (total === 0) return;

    const [prescRows] = await conn.query(
      `SELECT prescription_code FROM prescriptions WHERE id = ?`,
      [prescriptionId]
    );
    const prescriptionCode = prescRows[0]?.prescription_code;
    if (!prescriptionCode) return;

    console.log(`[节点3完成] 处方 ${prescriptionCode} 全部追溯码已出库（${total} 条），通知后端触发 pharmacist-success`);
    notifyBackendNode3Completed(prescriptionCode);
  } catch (e: any) {
    console.error(`[节点3完成] 检测失败: ${e.message}`);
  }
}

// POST /api/medicine-trace-codes — create user's code, then auto-generate remaining based on stock
router.post('/', async (req: Request, res: Response) => {
  const conn = await pool.getConnection();
  try {
    const { medicine_id, trace_code } = req.body;
    if (!medicine_id || !trace_code) {
      res.status(400).json({ error: 'medicine_id 和 trace_code 为必填项' });
      return;
    }

    await conn.beginTransaction();

    // Get medicine stock and name (for prefix lookup)
    const [medRows] = await conn.query<any[]>('SELECT name, stock FROM medicines WHERE id = ? FOR UPDATE', [medicine_id]);
    if (medRows.length === 0) {
      await conn.rollback();
      res.status(404).json({ error: '药品不存在' });
      return;
    }
    const stock = medRows[0].stock;

    // 获取前缀映射表
    const prefixMap = await getPrefixMap(conn);
    const prefix = prefixMap.get(medicine_id);

    // Count existing trace codes for this medicine
    const [countRows] = await conn.query<any[]>('SELECT COUNT(*) as cnt FROM medicine_trace_codes WHERE medicine_id = ?', [medicine_id]);
    const existingCount = countRows[0].cnt;

    // Insert user's trace code first
    const normalizedTraceCode = trace_code.trim();
    const [result] = await conn.query(
      'INSERT INTO medicine_trace_codes (medicine_id, trace_code) VALUES (?, ?)',
      [medicine_id, normalizedTraceCode]
    );
    const userInsertId = (result as any).insertId;

    await appendAuditRecord(conn, {
      eventType: 'DRUG_INBOUND',
      entityType: 'trace_code',
      entityId: userInsertId,
      flowStatus: 'inbound',
      traceCode: normalizedTraceCode,
      operatorId: req.user?.id,
    });

    // Auto-generate remaining codes if stock > existingCount + 1
    const needCount = stock - existingCount - 1;
    const generatedCodes: string[] = [];
    if (needCount > 0) {
      const values: any[] = [];
      const placeholders: string[] = [];
      for (let i = 0; i < needCount; i++) {
        const code = randomTraceCode(prefix);
        placeholders.push('(?, ?)');
        values.push(medicine_id, code);
        generatedCodes.push(code);
      }
      await conn.query(`INSERT INTO medicine_trace_codes (medicine_id, trace_code) VALUES ${placeholders.join(', ')}`, values);
      await appendAuditRecord(conn, {
        eventType: 'DRUG_INBOUND',
        entityType: 'trace_code',
        entityId: `batch:${medicine_id}:${userInsertId}`,
        flowStatus: 'inbound_batch',
        traceCodes: generatedCodes,
        operatorId: req.user?.id,
      });
    }

    await conn.commit();

    res.status(201).json({
      id: userInsertId,
      message: `已添加追溯码，自动生成 ${generatedCodes.length} 条`,
      generatedCount: generatedCodes.length,
    });
  } catch (err: any) {
    await conn.rollback();
    if (err.code === 'ER_DUP_ENTRY') {
      res.status(409).json({ error: '该追溯码已被使用' });
      return;
    }
    res.status(500).json({ error: '服务器错误: ' + err.message });
  } finally {
    conn.release();
  }
});
// POST /api/medicine-trace-codes/generate-all — batch generate for all medicines
router.post('/generate-all', async (_req: Request, res: Response) => {
  try {
    // Get all medicines with stock > 0
    const [medicines] = await pool.query<any[]>('SELECT id, name, stock FROM medicines WHERE stock > 0');

    // 获取前缀映射表
    const prefixMap = await getPrefixMap(pool);

    let totalGenerated = 0;
    const results: string[] = [];

    for (const med of medicines) {
      // Count existing trace codes
      const [countRows] = await pool.query<any[]>('SELECT COUNT(*) as cnt FROM medicine_trace_codes WHERE medicine_id = ?', [med.id]);
      const existingCount = countRows[0].cnt;
      const needCount = med.stock - existingCount;

      if (needCount > 0) {
        const prefix = prefixMap.get(med.id);
        const values: any[] = [];
        const placeholders: string[] = [];
        for (let i = 0; i < needCount; i++) {
          const code = randomTraceCode(prefix);
          placeholders.push('(?, ?)');
          values.push(med.id, code);
        }
        await pool.query(`INSERT INTO medicine_trace_codes (medicine_id, trace_code) VALUES ${placeholders.join(', ')}`, values);
        totalGenerated += needCount;
        results.push(`${med.name}: 已生成 ${needCount} 条`);
      }
    }

    res.json({
      message: `批量生成完成，共生成 ${totalGenerated} 条追溯码`,
      totalGenerated,
      details: results,
    });
  } catch (err: any) {
    res.status(500).json({ error: '服务器错误: ' + err.message });
  }
});

// POST /api/medicine-trace-codes/regenerate-all — 清空全部追溯码并重新生成（使用药品前缀）
router.post('/regenerate-all', async (_req: Request, res: Response) => {
  const conn = await pool.getConnection();
  try {
    await conn.beginTransaction();

    // 1. 清空处方关联，避免外键阻止测试阶段重建追溯码
    try {
      await conn.query('DELETE FROM prescription_trace_codes');
    } catch (err: any) {
      if (err.code !== 'ER_NO_SUCH_TABLE') throw err;
    }

    // 2. 清空全部追溯码
    const [deleteResult] = await conn.query<any>('DELETE FROM medicine_trace_codes');
    const deletedCount = (deleteResult as any)?.affectedRows || 0;

    // 3. 获取所有库存 > 0 的药品
    const [medicines] = await conn.query<any[]>('SELECT id, name, stock FROM medicines WHERE stock > 0');

    // 获取前缀映射表（使用当前连接以支持事务）
    const prefixMap = await getPrefixMap(conn);

    let totalGenerated = 0;
    const details: string[] = [];

    for (const med of medicines) {
      const prefix = prefixMap.get(med.id);
      const values: any[] = [];
      const placeholders: string[] = [];

      for (let i = 0; i < med.stock; i++) {
        const code = randomTraceCode(prefix);
        placeholders.push('(?, ?)');
        values.push(med.id, code);
      }

      if (placeholders.length > 0) {
        await conn.query(
          `INSERT INTO medicine_trace_codes (medicine_id, trace_code) VALUES ${placeholders.join(', ')}`,
          values
        );
        totalGenerated += med.stock;
        details.push(`${med.name}: 生成 ${med.stock} 条 (前缀: ${prefix || '无'})`);
      }
    }

    await conn.commit();

    res.json({
      message: `已清空 ${deletedCount} 条旧追溯码，重新生成 ${totalGenerated} 条新追溯码`,
      deletedCount,
      totalGenerated,
      details,
    });
  } catch (err: any) {
    await conn.rollback();
    res.status(500).json({ error: '操作失败，已回滚: ' + err.message });
  } finally {
    conn.release();
  }
});

// PUT /api/medicine-trace-codes/:id — update
router.put('/:id', async (req: Request, res: Response) => {
  try {
    const id = parseInt(req.params.id);
    const { trace_code } = req.body;

    if (!trace_code) {
      res.status(400).json({ error: '追溯码为必填项' });
      return;
    }

    const [checkRows] = await pool.query<any[]>(
      'SELECT id FROM medicine_trace_codes WHERE id = ?', [id]
    );
    if (checkRows.length === 0) {
      res.status(404).json({ error: '追溯码不存在' });
      return;
    }

    await pool.query(
      'UPDATE medicine_trace_codes SET trace_code = ? WHERE id = ?',
      [trace_code.trim(), id]
    );

    res.json({ message: '追溯码已更新' });
  } catch (err: any) {
    if (err.code === 'ER_DUP_ENTRY') {
      res.status(409).json({ error: '该追溯码已被使用' });
      return;
    }
    res.status(500).json({ error: '服务器错误: ' + err.message });
  }
});

// DELETE /api/medicine-trace-codes/:id — delete
router.delete('/:id', async (req: Request, res: Response) => {
  try {
    const id = parseInt(req.params.id);

    const [checkRows] = await pool.query<any[]>(
      'SELECT id, prescription_id FROM medicine_trace_codes WHERE id = ?', [id]
    );
    if (checkRows.length === 0) {
      res.status(404).json({ error: '追溯码不存在' });
      return;
    }

    if (checkRows[0].prescription_id) {
      res.status(400).json({ error: '该追溯码已关联处方，不能删除' });
      return;
    }

    try {
      const [linkRows] = await pool.query<any[]>(
        'SELECT COUNT(*) AS cnt FROM prescription_trace_codes WHERE trace_code_id = ?',
        [id]
      );
      if ((linkRows[0]?.cnt || 0) > 0) {
        res.status(400).json({ error: '该追溯码已关联处方，不能删除' });
        return;
      }
    } catch (err: any) {
      if (err.code !== 'ER_NO_SUCH_TABLE') {
        throw err;
      }
    }

    await pool.query('DELETE FROM medicine_trace_codes WHERE id = ?', [id]);
    res.json({ message: '追溯码已删除' });
  } catch (err: any) {
    res.status(500).json({ error: '服务器错误: ' + err.message });
  }
});

// GET /api/medicine-trace-codes/lookup — lookup trace code without advancing scan status
router.get('/lookup', async (req: Request, res: Response) => {
  try {
    const traceCode = String(req.query.trace_code || '').trim();
    if (!traceCode) {
      res.status(400).json({ error: '追溯码不能为空' });
      return;
    }

    const candidates = getTraceCodeCandidates(traceCode);
    if (candidates.length === 0) {
      res.status(400).json({ error: '追溯码不能为空' });
      return;
    }

    const placeholders = candidates.map(() => '?').join(', ');
    const [rows] = await pool.query<any[]>(
      `SELECT tc.*, m.id AS medicine_id, m.name AS medicine_name, m.generic_name,
              m.specification, m.drug_form, m.manufacturer, m.unit, m.price, m.stock,
              m.category, m.is_narcotic, m.image_url
       FROM medicine_trace_codes tc
       JOIN medicines m ON tc.medicine_id = m.id
       WHERE tc.trace_code IN (${placeholders})`,
      candidates
    );

    if (rows.length === 0) {
      res.status(404).json({ error: '追溯码未找到' });
      return;
    }

    res.json(rows[0]);
  } catch (err: any) {
    res.status(500).json({ error: '服务器错误: ' + err.message });
  }
});

// PUT /api/medicine-trace-codes/:id/scan — advance scan status
router.put('/:id/scan', async (req: Request, res: Response) => {
  const conn = await pool.getConnection();
  try {
    const id = parseInt(req.params.id);
    const userId = (req as any).user?.id;
    const prescriptionId = req.body.prescription_id ? parseInt(req.body.prescription_id) : null;

    await conn.beginTransaction();

    const [rows] = await conn.query<any[]>(
      'SELECT * FROM medicine_trace_codes WHERE id = ? FOR UPDATE', [id]
    );
    if (rows.length === 0) {
      await conn.rollback();
      res.status(404).json({ error: '追溯码不存在' });
      return;
    }

    const record = rows[0];
    if (!validatePrescriptionLink(record, prescriptionId, res)) {
      await conn.rollback();
      return;
    }

    const currentStatus: string = record.status;

    let updateSql: string;
    const updateParams: any[] = [];
    let auditEventType: 'DRUG_OUTBOUND' | 'NURSE_RECEIVED' | null = null;

    // 2 次扫码流程：pending -> scanned_outbound(出库, scan2) -> scanned_confirm(确认, scan3)
    // 已取消"识别"(scan1) 步骤，每药共扫 2 次
    if (currentStatus === 'pending') {
      updateSql = 'UPDATE medicine_trace_codes SET status = ?, scan2_time = NOW(), scan2_user_id = ?, prescription_id = COALESCE(?, prescription_id) WHERE id = ?';
      updateParams.push('scanned_outbound', userId, prescriptionId, id);
      auditEventType = 'DRUG_OUTBOUND';
    } else if (currentStatus === 'scanned_outbound') {
      updateSql = 'UPDATE medicine_trace_codes SET status = ?, scan3_time = NOW(), scan3_user_id = ?, prescription_id = COALESCE(?, prescription_id) WHERE id = ?';
      updateParams.push('scanned_confirm', userId, prescriptionId, id);
      auditEventType = 'NURSE_RECEIVED';
    } else {
      await conn.rollback();
      res.status(400).json({ error: '该追溯码已完成全部扫描' });
      return;
    }

    await conn.query(updateSql, updateParams);

    if (auditEventType) {
      await appendAuditRecord(conn, {
        eventType: auditEventType,
        entityType: 'trace_code',
        entityId: id,
        flowStatus: auditEventType === 'DRUG_OUTBOUND' ? 'scanned_outbound' : 'scanned_confirm',
        traceCode: record.trace_code,
        prescriptionId: prescriptionId || record.prescription_id,
        operatorId: userId,
      });
    }

    // Return updated record with operator names
    const [updated] = await conn.query<any[]>(
      `SELECT tc.*, u1.real_name AS scan1_user_name, u2.real_name AS scan2_user_name, u3.real_name AS scan3_user_name
       FROM medicine_trace_codes tc
       LEFT JOIN users u1 ON tc.scan1_user_id = u1.id
       LEFT JOIN users u2 ON tc.scan2_user_id = u2.id
       LEFT JOIN users u3 ON tc.scan3_user_id = u3.id
       WHERE tc.id = ?`, [id]
    );

    await conn.commit();

    // 节点3扫码复核完成检测：pending → scanned_outbound 时检查该处方是否全部出库
    if (currentStatus === 'pending') {
      await checkNode3CompletedAndNotify(conn, prescriptionId || record.prescription_id);
    }

    res.json(updated[0]);
  } catch (err: any) {
    await conn.rollback();
    res.status(500).json({ error: '服务器错误: ' + err.message });
  } finally {
    conn.release();
  }
});
// PUT /api/medicine-trace-codes/:id/unscan — revoke scan (go back one step)
router.put('/:id/unscan', async (req: Request, res: Response) => {
  try {
    const id = parseInt(req.params.id);

    const [rows] = await pool.query<any[]>(
      'SELECT * FROM medicine_trace_codes WHERE id = ?', [id]
    );
    if (rows.length === 0) {
      res.status(404).json({ error: '追溯码不存在' });
      return;
    }

    const record = rows[0];
    const currentStatus: string = record.status;

    let updateSql: string;
    const updateParams: any[] = [];

    // 2 次扫码撤回：scanned_confirm -> scanned_outbound(清 scan3) -> pending(清 scan2)
    if (currentStatus === 'scanned_confirm') {
      updateSql = 'UPDATE medicine_trace_codes SET status = ?, scan3_time = NULL, scan3_user_id = NULL WHERE id = ?';
      updateParams.push('scanned_outbound', id);
    } else if (currentStatus === 'scanned_outbound') {
      updateSql = 'UPDATE medicine_trace_codes SET status = ?, scan2_time = NULL, scan2_user_id = NULL WHERE id = ?';
      updateParams.push('pending', id);
    } else {
      res.status(400).json({ error: '该追溯码尚未扫描，无法撤回' });
      return;
    }

    await pool.query(updateSql, updateParams);

    // Return updated record
    const [updated] = await pool.query<any[]>(
      `SELECT tc.*, u1.real_name AS scan1_user_name, u2.real_name AS scan2_user_name, u3.real_name AS scan3_user_name
       FROM medicine_trace_codes tc
       LEFT JOIN users u1 ON tc.scan1_user_id = u1.id
       LEFT JOIN users u2 ON tc.scan2_user_id = u2.id
       LEFT JOIN users u3 ON tc.scan3_user_id = u3.id
       WHERE tc.id = ?`, [id]
    );

    res.json(updated[0]);
  } catch (err: any) {
    res.status(500).json({ error: '服务器错误: ' + err.message });
  }
});

// POST /api/medicine-trace-codes/scan-by-code — scan by trace_code string (for mobile scanner)
router.post('/scan-by-code', async (req: Request, res: Response) => {
  const conn = await pool.getConnection();
  try {
    const { trace_code } = req.body;
    if (!trace_code) {
      res.status(400).json({ error: '追溯码不能为空' });
      return;
    }

    await conn.beginTransaction();

    const userId = (req as any).user?.id;
    const { record, created } = await ensureTraceCodeRecordForScan(conn, trace_code);
    if (!record) {
      await conn.rollback();
      res.status(404).json({ error: '追溯码未找到' });
      return;
    }

    if (created) {
      await appendAuditRecord(conn, {
        eventType: 'DRUG_INBOUND',
        entityType: 'trace_code',
        entityId: record.id,
        flowStatus: 'inbound',
        traceCode: record.trace_code,
        operatorId: userId,
      });
      await conn.commit();
      res.json({
        ...record,
        action: '录入',
        completed: false,
        created,
      });
      return;
    }

    // Advance scan status
    let updateSql: string;
    const updateParams: any[] = [];
    let actionName: string;
    let auditEventType: 'DRUG_OUTBOUND' | 'NURSE_RECEIVED' | null = null;

    // 2 次扫码流程：pending -> scanned_outbound(出库, scan2) -> scanned_confirm(确认, scan3)
    // 已取消"识别"(scan1) 步骤，每药共扫 2 次
    if (record.status === 'pending') {
      updateSql = 'UPDATE medicine_trace_codes SET status = ?, scan2_time = NOW(), scan2_user_id = ? WHERE id = ?';
      updateParams.push('scanned_outbound', userId, record.id);
      actionName = '出库';
      auditEventType = 'DRUG_OUTBOUND';
    } else if (record.status === 'scanned_outbound') {
      updateSql = 'UPDATE medicine_trace_codes SET status = ?, scan3_time = NOW(), scan3_user_id = ? WHERE id = ?';
      updateParams.push('scanned_confirm', userId, record.id);
      actionName = '确认';
      auditEventType = 'NURSE_RECEIVED';
    } else {
      await conn.commit();
      res.json({
        message: '该追溯码已完成全部扫描',
        status: record.status,
        completed: true,
        created,
      });
      return;
    }

    await conn.query(updateSql, updateParams);

    if (auditEventType) {
      await appendAuditRecord(conn, {
        eventType: auditEventType,
        entityType: 'trace_code',
        entityId: record.id,
        flowStatus: auditEventType === 'DRUG_OUTBOUND' ? 'scanned_outbound' : 'scanned_confirm',
        traceCode: record.trace_code,
        prescriptionId: record.prescription_id,
        operatorId: userId,
      });
    }

    // Return updated record with medicine info
    const [updated] = await conn.query<any[]>(
      `SELECT tc.*, m.name AS medicine_name, m.specification, m.manufacturer,
        u1.real_name AS scan1_user_name, u2.real_name AS scan2_user_name, u3.real_name AS scan3_user_name
       FROM medicine_trace_codes tc
       JOIN medicines m ON tc.medicine_id = m.id
       LEFT JOIN users u1 ON tc.scan1_user_id = u1.id
       LEFT JOIN users u2 ON tc.scan2_user_id = u2.id
       LEFT JOIN users u3 ON tc.scan3_user_id = u3.id
       WHERE tc.id = ?`, [record.id]
    );

    await conn.commit();

    // 节点3扫码复核完成检测：pending → scanned_outbound 时检查该处方是否全部出库
    if (record.status === 'pending') {
      await checkNode3CompletedAndNotify(conn, record.prescription_id);
    }

    res.json({
      ...updated[0],
      action: actionName,
      completed: actionName === '确认',
      created,
    });
  } catch (err: any) {
    await conn.rollback();
    res.status(err.status || 500).json({ error: err.status ? err.message : '服务器错误: ' + err.message });
  } finally {
    conn.release();
  }
});

export default router;
