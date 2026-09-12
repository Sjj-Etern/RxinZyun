import { Router, Request, Response } from 'express';
import http from 'http';
import https from 'https';
import pool from '../db';
import { authMiddleware } from '../middleware/auth';
import { appendCompletedScanStages } from '../services/auditChain';
import { config } from '../config';

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
    res.status(400).json({ error: '本药品未开处方' });
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

// 【通信工程师负责】以下事件桥接代码：将 HIS 扫码进度/完成状态通过 HTTP
// 通知调度后端；追溯码本身的扫码校验与状态写入由硬件工程师负责。
// 节点3扫码复核完成后通知医院大屏后端，触发车2继续配送。
// 节点3对应所有追溯码第一次实际扫码完成（判定含 scanned_outbound 与 scanned_confirm，防重复扫码破坏计数）。
async function notifyBackendNode3Completed(prescriptionCode: string): Promise<void> {
  const base = config.services.hospitalBackendUrl;
  const target = new URL(`${base}/workflow/pharmacist-success-trigger`);
  const body = JSON.stringify({ prescription_code: prescriptionCode });
  const transport = target.protocol === 'https:' ? https : http;

  for (let attempt = 1; attempt <= 3; attempt += 1) {
    try {
      await new Promise<void>((resolve, reject) => {
        const req = transport.request({
          hostname: target.hostname,
          port: Number(target.port) || (target.protocol === 'https:' ? 443 : 80),
          path: target.pathname + target.search,
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) },
          timeout: config.services.hospitalBackendTimeoutMs,
        }, (response) => {
          let raw = '';
          response.setEncoding('utf8');
          response.on('data', (chunk) => { raw += chunk; });
          response.on('end', () => {
            const statusCode = response.statusCode || 0;
            if (statusCode >= 200 && statusCode < 300) {
              console.log(`[节点3完成通知] 大屏后端响应 ${statusCode}: ${raw}`);
              resolve();
              return;
            }
            reject(new Error(`大屏后端响应 ${statusCode}: ${raw}`));
          });
        });
        req.on('error', reject);
        req.on('timeout', () => req.destroy(new Error('通知大屏后端超时')));
        req.write(body);
        req.end();
      });
      return;
    } catch (error: any) {
      console.error(`[节点3完成通知] 第${attempt}次失败: ${error.message}`);
      if (attempt === 3) throw error;
      await new Promise((resolve) => setTimeout(resolve, attempt * 500));
    }
  }
}

// 扫码进度通知：每次出库扫码后向大屏后端推送进度（已扫第几个/共几个），供大屏 N5 节点实时显示
function notifyBackendScanProgress(prescriptionCode: string, scanned: number, total: number, medicineName: string): void {
  const base = config.services.hospitalBackendUrl;
  const target = new URL(`${base}/workflow/scan-progress`);
  const body = JSON.stringify({ prescription_code: prescriptionCode, scanned, total, medicine_name: medicineName });
  const transport = target.protocol === 'https:' ? https : http;
  const req = transport.request({
    hostname: target.hostname,
    port: Number(target.port) || (target.protocol === 'https:' ? 443 : 80),
    path: target.pathname + target.search,
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) },
    timeout: config.services.hospitalBackendTimeoutMs,
  }, (response) => {
    let raw = '';
    response.setEncoding('utf8');
    response.on('data', (chunk) => { raw += chunk; });
    response.on('end', () => {
      console.log(`[扫码进度] 大屏后端响应 ${response.statusCode}: ${raw}`);
    });
  });
  req.on('error', (error) => console.error(`[扫码进度] 通知大屏后端失败: ${error.message}`));
  req.on('timeout', () => {
    req.destroy();
    console.error('[扫码进度] 通知大屏后端超时');
  });
  req.write(body);
  req.end();
}

// 每次出库扫码（未全部完成时）向大屏后端推送扫码进度
async function checkScanProgressAndNotify(conn: any, prescriptionId: number | null, medicineId: number | null): Promise<void> {
  if (!prescriptionId) return;
  try {
    const [countRows] = await conn.query(
      `SELECT
         (SELECT COALESCE(SUM(quantity), 0) FROM prescription_items WHERE prescription_id = ?) AS total,
         (SELECT COUNT(*)
          FROM prescription_trace_codes ptc
          JOIN medicine_trace_codes tc ON tc.id = ptc.trace_code_id
          WHERE ptc.prescription_id = ? AND tc.status IN ('scanned_outbound', 'scanned_confirm')) AS scanned`,
      [prescriptionId, prescriptionId]
    );
    const total = Number(countRows[0]?.total || 0);
    const scanned = Number(countRows[0]?.scanned || 0);
    if (total === 0 || scanned >= total) return; // 全部扫完由节点3完成通知处理

    const [codeRows] = await conn.query(
      'SELECT prescription_code FROM prescriptions WHERE id = ?', [prescriptionId]
    );
    const prescriptionCode = codeRows[0]?.prescription_code;
    if (!prescriptionCode) return;

    let medicineName = '';
    if (medicineId) {
      const [medRows] = await conn.query(
        'SELECT name FROM medicines WHERE id = ?', [medicineId]
      );
      medicineName = medRows[0]?.name || '';
    }
    console.log(`[扫码进度] 处方 ${prescriptionCode} 已扫 ${scanned}/${total}（最近：${medicineName}），通知大屏后端`);
    notifyBackendScanProgress(prescriptionCode, scanned, total, medicineName);
  } catch (error: any) {
    console.error(`[扫码进度] 检查或通知失败: ${error.message}`);
  }
}

async function checkNode3CompletedAndNotify(conn: any, prescriptionId: number | null): Promise<void> {
  if (!prescriptionId) return;

  try {
    // 判定包含 scanned_confirm：只要每个码完成过第一次扫码（无论是否又被第二次扫码推进到确认状态），
    // 即视为第一轮出库完成。防止药师重复扫码把状态推到 scanned_confirm 后 outbound 计数归零、永不触发。
    const [countRows] = await conn.query(
      `SELECT
         (SELECT COALESCE(SUM(quantity), 0) FROM prescription_items WHERE prescription_id = ?) AS total,
         (SELECT COUNT(*)
          FROM prescription_trace_codes ptc
          JOIN medicine_trace_codes tc ON tc.id = ptc.trace_code_id
          WHERE ptc.prescription_id = ? AND tc.status IN ('scanned_outbound', 'scanned_confirm')) AS outbound`,
      [prescriptionId, prescriptionId]
    );
    const total = Number(countRows[0]?.total || 0);
    const outbound = Number(countRows[0]?.outbound || 0);
    if (total === 0 || outbound !== total) return;

    const [prescriptionRows] = await conn.query(
      'SELECT prescription_code FROM prescriptions WHERE id = ?',
      [prescriptionId]
    );
    const prescriptionCode = prescriptionRows[0]?.prescription_code;
    if (!prescriptionCode) return;

    console.log(`[节点3完成] 处方 ${prescriptionCode} 全部追溯码已完成第一次扫码（${total} 条），通知大屏后端`);
    await notifyBackendNode3Completed(prescriptionCode);
  } catch (error: any) {
    // 回调失败不回滚已完成的扫码，避免大屏暂时不可用阻塞 HIS。
    console.error(`[节点3完成] 检查或通知失败: ${error.message}`);
  }
}

// 节点4扫码全部确认后通知医院大屏后端，触发车2 nurse-success（替代车2 nurse_arrive 消息的编排职责）。
// 节点4对应所有追溯码第二次实际扫码完成（scan3_time / scanned_confirm）。
function notifyBackendNode4Completed(prescriptionCode: string): void {
  const base = config.services.hospitalBackendUrl;
  const target = new URL(`${base}/workflow/nurse-success-trigger`);
  const body = JSON.stringify({ prescription_code: prescriptionCode });
  const transport = target.protocol === 'https:' ? https : http;
  const req = transport.request({
    hostname: target.hostname,
    port: Number(target.port) || (target.protocol === 'https:' ? 443 : 80),
    path: target.pathname + target.search,
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) },
    timeout: config.services.hospitalBackendTimeoutMs,
  }, (response) => {
    let raw = '';
    response.setEncoding('utf8');
    response.on('data', (chunk) => { raw += chunk; });
    response.on('end', () => {
      console.log(`[节点4完成通知] 大屏后端响应 ${response.statusCode}: ${raw}`);
    });
  });
  req.on('error', (error) => console.error(`[节点4完成通知] 通知大屏后端失败: ${error.message}`));
  req.on('timeout', () => {
    req.destroy();
    console.error('[节点4完成通知] 通知大屏后端超时');
  });
  req.write(body);
  req.end();
}

async function checkNode4CompletedAndNotify(conn: any, prescriptionId: number | null): Promise<void> {
  if (!prescriptionId) return;

  try {
    const [countRows] = await conn.query(
      `SELECT
         (SELECT COALESCE(SUM(quantity), 0) FROM prescription_items WHERE prescription_id = ?) AS total,
         (SELECT COUNT(*)
          FROM prescription_trace_codes ptc
          JOIN medicine_trace_codes tc ON tc.id = ptc.trace_code_id
          WHERE ptc.prescription_id = ? AND tc.status = 'scanned_confirm') AS confirmed`,
      [prescriptionId, prescriptionId]
    );
    const total = Number(countRows[0]?.total || 0);
    const confirmed = Number(countRows[0]?.confirmed || 0);
    if (total === 0 || confirmed !== total) return;

    const [prescriptionRows] = await conn.query(
      'SELECT prescription_code FROM prescriptions WHERE id = ?',
      [prescriptionId]
    );
    const prescriptionCode = prescriptionRows[0]?.prescription_code;
    if (!prescriptionCode) return;

    console.log(`[节点4完成] 处方 ${prescriptionCode} 全部追溯码已完成第二次扫码（${total} 条），通知大屏后端`);
    notifyBackendNode4Completed(prescriptionCode);
  } catch (error: any) {
    // 回调失败不回滚已完成的扫码，避免大屏暂时不可用阻塞 HIS。
    console.error(`[节点4完成] 检查或通知失败: ${error.message}`);
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
      const numericCode = traceCode.replace(/\D/g, '');
      const prefix = numericCode.slice(0, 7);
      const [matchedMedicines] = prefix.length === 7
        ? await pool.query<any[]>(
          `SELECT m.id AS medicine_id, m.name AS medicine_name, m.specification, m.manufacturer, m.unit
           FROM medicine_trace_prefixes p
           JOIN medicines m ON m.id = p.medicine_id
           WHERE p.prefix = ? LIMIT 1`,
          [prefix]
        )
        : [[]];
      if (matchedMedicines.length) {
        res.status(404).json({
          error: '追溯码尚未入库',
          can_import: true,
          trace_code: numericCode,
          ...matchedMedicines[0],
        });
        return;
      }
      res.status(404).json({ error: '没有对应药品类别，无法入库', can_import: false });
      return;
    }

    res.json(rows[0]);
  } catch (err: any) {
    res.status(500).json({ error: '服务器错误: ' + err.message });
  }
});

// POST /api/medicine-trace-codes/register-by-prefix — 扫码确认后按前 7 位匹配药品并入库。
router.post('/register-by-prefix', async (req: Request, res: Response) => {
  const conn = await pool.getConnection();
  try {
    const traceCode = String(req.body.trace_code || '').replace(/\D/g, '');
    if (traceCode.length < 7) {
      res.status(400).json({ error: '追溯码至少需要 7 位数字' });
      return;
    }

    await conn.beginTransaction();
    const [existing] = await conn.query<any[]>(
      'SELECT id FROM medicine_trace_codes WHERE trace_code = ? FOR UPDATE',
      [traceCode]
    );
    if (existing.length) {
      await conn.rollback();
      res.status(409).json({ error: '该追溯码已经入库' });
      return;
    }

    const [medicines] = await conn.query<any[]>(
      `SELECT m.id AS medicine_id, m.name AS medicine_name, m.generic_name, m.specification,
              m.drug_form, m.manufacturer, m.unit, m.price, m.stock, m.category,
              m.is_narcotic, m.image_url
       FROM medicine_trace_prefixes p
       JOIN medicines m ON m.id = p.medicine_id
       WHERE p.prefix = ? LIMIT 1 FOR UPDATE`,
      [traceCode.slice(0, 7)]
    );
    if (!medicines.length) {
      await conn.rollback();
      res.status(400).json({ error: '没有对应药品类别，无法入库' });
      return;
    }

    const medicine = medicines[0];
    const [result] = await conn.query(
      'INSERT INTO medicine_trace_codes (medicine_id, trace_code, status) VALUES (?, ?, ?)',
      [medicine.medicine_id, traceCode, 'pending']
    );
    await conn.query('UPDATE medicines SET stock = stock + 1 WHERE id = ?', [medicine.medicine_id]);
    await conn.commit();
    res.status(201).json({
      ...medicine,
      id: Number((result as any).insertId),
      trace_code: traceCode,
      status: 'pending',
      stock: Number(medicine.stock || 0) + 1,
      action: '扫码入库',
    });
  } catch (err: any) {
    await conn.rollback();
    res.status(500).json({ error: '扫码入库失败: ' + err.message });
  } finally {
    conn.release();
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
    if (currentStatus === 'pending' || currentStatus === 'scanned_identify') {
      // 两次实际扫码：第一次出库（节点3），第二次确认（节点4）。
      updateSql = 'UPDATE medicine_trace_codes SET status = ?, scan2_time = NOW(), scan2_user_id = ?, prescription_id = COALESCE(?, prescription_id) WHERE id = ?';
      updateParams.push('scanned_outbound', userId, prescriptionId, id);
    } else if (currentStatus === 'scanned_outbound') {
      updateSql = 'UPDATE medicine_trace_codes SET status = ?, scan3_time = NOW(), scan3_user_id = ?, prescription_id = COALESCE(?, prescription_id) WHERE id = ?';
      updateParams.push('scanned_confirm', userId, prescriptionId, id);
    } else {
      await conn.rollback();
      res.status(400).json({ error: '该追溯码已完成全部扫描' });
      return;
    }

    await conn.query(updateSql, updateParams);

    await appendCompletedScanStages(conn, Number(prescriptionId || record.prescription_id), userId);

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

    // 第一次实际扫码完成整张处方后，通知大屏后端触发车2 pharmacist-success。
    if (currentStatus === 'pending' || currentStatus === 'scanned_identify') {
      await checkScanProgressAndNotify(conn, prescriptionId || record.prescription_id, record.medicine_id);
      await checkNode3CompletedAndNotify(conn, prescriptionId || record.prescription_id);
    }
    // 节点4扫码全部确认检测：scanned_outbound → scanned_confirm 时检查该处方是否全部确认
    if (currentStatus === 'scanned_outbound') {
      // 兜底：若节点3触发时机被错过（如通知失败/重复扫码），第二次扫码时补检（判定含 scanned_confirm）
      await checkNode3CompletedAndNotify(conn, prescriptionId || record.prescription_id);
      await checkNode4CompletedAndNotify(conn, prescriptionId || record.prescription_id);
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

    if (currentStatus === 'scanned_confirm') {
      updateSql = 'UPDATE medicine_trace_codes SET status = ?, scan3_time = NULL, scan3_user_id = NULL WHERE id = ?';
      updateParams.push('scanned_outbound', id);
    } else if (currentStatus === 'scanned_outbound') {
      updateSql = 'UPDATE medicine_trace_codes SET status = ?, scan2_time = NULL, scan2_user_id = NULL WHERE id = ?';
      updateParams.push('pending', id);
    } else if (currentStatus === 'scanned_identify') {
      updateSql = 'UPDATE medicine_trace_codes SET status = ?, scan1_time = NULL, scan1_user_id = NULL WHERE id = ?';
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
    const prescriptionId = Number(req.body.prescription_id);
    if (!trace_code || !Number.isInteger(prescriptionId) || prescriptionId <= 0) {
      res.status(400).json({ error: '请选择处方并扫描有效追溯码' });
      return;
    }

    await conn.beginTransaction();

    const userId = (req as any).user?.id;
    const record = await findTraceCodeByInputForUpdate(conn, trace_code);
    if (!record) {
      await conn.rollback();
      res.status(404).json({ error: '追溯码不存在，请先扫码入库' });
      return;
    }

    const [prescriptionRows] = await conn.query<any[]>(
      'SELECT id, status FROM prescriptions WHERE id = ? FOR UPDATE',
      [prescriptionId]
    );
    if (!prescriptionRows.length || !['approved', 'dispensed'].includes(prescriptionRows[0].status)) {
      await conn.rollback();
      res.status(400).json({ error: '当前处方不存在或不在可发药状态' });
      return;
    }

    const linkedPrescriptionId = record.prescription_id ? Number(record.prescription_id) : null;
    if (linkedPrescriptionId && linkedPrescriptionId !== prescriptionId) {
      await conn.rollback();
      res.status(409).json({ error: '该追溯码已绑定其他处方' });
      return;
    }

    // Advance scan status
    let updateSql: string;
    const updateParams: any[] = [];
    let actionName: string;
    if (record.status === 'pending' || record.status === 'scanned_identify') {
      if (linkedPrescriptionId) {
        await conn.rollback();
        res.status(409).json({ error: '该追溯码关联状态异常，请检查后重试' });
        return;
      }

      const [itemRows] = await conn.query<any[]>(
        `SELECT id, quantity
         FROM prescription_items
         WHERE prescription_id = ? AND medicine_id = ?
         ORDER BY id ASC LIMIT 1 FOR UPDATE`,
        [prescriptionId, record.medicine_id]
      );
      if (!itemRows.length) {
        await conn.rollback();
        res.status(400).json({ error: `当前处方不包含药品：${record.medicine_name}` });
        return;
      }

      const prescriptionItemId = Number(itemRows[0].id);
      const requiredQuantity = Number(itemRows[0].quantity || 0);
      const [boundRows] = await conn.query<any[]>(
        'SELECT COUNT(*) AS count FROM prescription_trace_codes WHERE prescription_item_id = ?',
        [prescriptionItemId]
      );
      if (Number(boundRows[0]?.count || 0) >= requiredQuantity) {
        await conn.rollback();
        res.status(409).json({ error: `${record.medicine_name} 已达到处方数量 ${requiredQuantity}` });
        return;
      }

      await conn.query(
        `INSERT INTO prescription_trace_codes (prescription_id, prescription_item_id, medicine_id, trace_code_id)
         VALUES (?, ?, ?, ?)`,
        [prescriptionId, prescriptionItemId, record.medicine_id, record.id]
      );
      updateSql = 'UPDATE medicine_trace_codes SET status = ?, scan2_time = NOW(), scan2_user_id = ?, prescription_id = ? WHERE id = ?';
      updateParams.push('scanned_outbound', userId, prescriptionId, record.id);
      actionName = '出库';
    } else if (record.status === 'scanned_outbound') {
      updateSql = 'UPDATE medicine_trace_codes SET status = ?, scan3_time = NOW(), scan3_user_id = ? WHERE id = ?';
      updateParams.push('scanned_confirm', userId, record.id);
      actionName = '确认';
    } else {
      await conn.rollback();
      res.status(400).json({ error: '本药品已出库，无法再次扫码', status: record.status, completed: true });
      return;
    }

    await conn.query(updateSql, updateParams);

    await appendCompletedScanStages(conn, prescriptionId, userId);

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

    // 第一次实际扫码完成整张处方后，通知大屏后端触发车2 pharmacist-success。
    if (record.status === 'pending' || record.status === 'scanned_identify') {
      await checkScanProgressAndNotify(conn, prescriptionId, record.medicine_id);
      await checkNode3CompletedAndNotify(conn, prescriptionId);
    }
    // 节点4扫码全部确认检测：scanned_outbound → scanned_confirm 时检查该处方是否全部确认
    if (record.status === 'scanned_outbound') {
      // 兜底：若节点3触发时机被错过（如通知失败/重复扫码），第二次扫码时补检（判定含 scanned_confirm）
      await checkNode3CompletedAndNotify(conn, prescriptionId);
      await checkNode4CompletedAndNotify(conn, prescriptionId);
    }

    res.json({
      ...updated[0],
      action: actionName,
      completed: actionName === '确认',
    });
  } catch (err: any) {
    await conn.rollback();
    res.status(err.status || 500).json({ error: err.status ? err.message : '服务器错误: ' + err.message });
  } finally {
    conn.release();
  }
});

export default router;
