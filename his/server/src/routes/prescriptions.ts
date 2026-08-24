import { Router, Request, Response } from 'express';
import pool from '../db';
import { authMiddleware, requireRole } from '../middleware/auth';
import { appendAuditRecord } from '../services/auditChain';

const router = Router();
router.use(authMiddleware);

const PRESCRIPTION_ITEM_COUNT = 5;

type PrescriptionItemPayload = {
  medicine_id?: number;
  trace_code?: string;
  drug_form?: string;
  dosage?: string;
  usage_method?: string;
  frequency?: string;
  days?: number;
  quantity?: number;
  note?: string;
};

const httpError = (status: number, message: string) => Object.assign(new Error(message), { status });
let prescriptionTraceCodesTableReady = false;

const ensurePrescriptionTraceCodesTable = async (conn: any) => {
  if (prescriptionTraceCodesTableReady) return;
  await conn.query(`
    CREATE TABLE IF NOT EXISTS prescription_trace_codes (
      id int NOT NULL AUTO_INCREMENT,
      prescription_id int NOT NULL COMMENT '关联处方ID',
      prescription_item_id int NOT NULL COMMENT '关联处方药品明细ID',
      medicine_id int NOT NULL COMMENT '关联药品ID',
      trace_code_id int NOT NULL COMMENT '关联追溯码ID',
      created_at datetime NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (id) USING BTREE,
      UNIQUE INDEX uk_trace_code_id (trace_code_id ASC) USING BTREE,
      UNIQUE INDEX uk_prescription_trace_code (prescription_id ASC, trace_code_id ASC) USING BTREE,
      INDEX idx_prescription_id (prescription_id ASC) USING BTREE,
      INDEX idx_prescription_item_id (prescription_item_id ASC) USING BTREE,
      INDEX idx_medicine_id (medicine_id ASC) USING BTREE,
      CONSTRAINT prescription_trace_codes_ibfk_1 FOREIGN KEY (prescription_id) REFERENCES prescriptions (id) ON DELETE CASCADE ON UPDATE RESTRICT,
      CONSTRAINT prescription_trace_codes_ibfk_2 FOREIGN KEY (prescription_item_id) REFERENCES prescription_items (id) ON DELETE CASCADE ON UPDATE RESTRICT,
      CONSTRAINT prescription_trace_codes_ibfk_3 FOREIGN KEY (medicine_id) REFERENCES medicines (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
      CONSTRAINT prescription_trace_codes_ibfk_4 FOREIGN KEY (trace_code_id) REFERENCES medicine_trace_codes (id) ON DELETE RESTRICT ON UPDATE RESTRICT
    ) ENGINE = InnoDB DEFAULT CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci ROW_FORMAT = Dynamic
  `);
  prescriptionTraceCodesTableReady = true;
};

// 处方类型编码映射
const PRESCRIPTION_TYPE_CODES: Record<string, string> = {
  '普通': '01',
  '急诊': '02',
  '儿科': '03',
  '麻醉精一': '04',
  '精二': '05',
};

// 生成处方编号: 类型编码(2) + 日期(8) + 流水号(3) + 校验码(2) = 15位
// 每天每种处方类型独立编号，确保唯一
async function generatePrescriptionCode(type: string, conn: any): Promise<string> {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, '0');
  const d = String(now.getDate()).padStart(2, '0');
  const dateStr = `${y}${m}${d}`;
  const typeCode = PRESCRIPTION_TYPE_CODES[type] || '01';
  const prefix = typeCode + dateStr;

  // 查询当天该类型已有的最大流水号
  const [rows] = await conn.query(
    `SELECT MAX(CAST(SUBSTRING(prescription_code, 11, 3) AS UNSIGNED)) as max_seq
     FROM prescriptions
     WHERE prescription_code LIKE ?`,
    [`${prefix}%`]
  );
  const maxSeq = rows[0]?.max_seq || 0;
  const seq = String(maxSeq + 1).padStart(3, '0');

  // 校验码: (前缀 + 流水号)各位数字之和 mod 97
  const base = prefix + seq;
  let sum = 0;
  for (const ch of base) {
    sum += parseInt(ch, 10);
  }
  const checkCode = String(sum % 97).padStart(2, '0');
  return base + checkCode;
}

// POST /api/prescriptions — create prescription (doctor only)
router.post('/', requireRole('doctor', 'admin'), async (req: Request, res: Response) => {
  const conn = await pool.getConnection();
  try {
    const { patient_id, diagnosis, note, items, prescription_type, payment_type, medical_record_no, department, bed_no } = req.body;

    if (!patient_id || !diagnosis || !items || !Array.isArray(items) || items.length === 0) {
      res.status(400).json({ error: '请填写完整的处方信息（病人、诊断、药品）' });
      return;
    }

    if (items.length > PRESCRIPTION_ITEM_COUNT) {
      res.status(400).json({ error: `每张处方最多选择${PRESCRIPTION_ITEM_COUNT}种药品` });
      return;
    }

    const seenMedicineIds = new Set<number>();
    const seenTraceCodes = new Set<string>();
    for (const item of items as PrescriptionItemPayload[]) {
      const traceCode = String(item.trace_code || '').trim();
      if (!item.medicine_id || !item.dosage || !traceCode) {
        res.status(400).json({ error: '每个药品都必须填写药品、用量和追溯码' });
        return;
      }
      const medicineId = Number(item.medicine_id);
      if (seenMedicineIds.has(medicineId)) {
        res.status(400).json({ error: '每张处方的药品不能重复' });
        return;
      }
      if (seenTraceCodes.has(traceCode)) {
        res.status(400).json({ error: `追溯码不能重复: ${traceCode}` });
        return;
      }
      seenMedicineIds.add(medicineId);
      seenTraceCodes.add(traceCode);
    }

    let totalAmount = 0;
    const resolvedItems: Array<PrescriptionItemPayload & { trace_code: string; trace_code_id: number }> = [];

    await ensurePrescriptionTraceCodesTable(conn);
    await conn.beginTransaction();

    for (const item of items as PrescriptionItemPayload[]) {
      const traceCode = String(item.trace_code || '').trim();
      const [traceRows] = await conn.query<any[]>(
        `SELECT tc.id AS trace_code_id, tc.medicine_id, tc.prescription_id, tc.status,
                tc.scan1_time, tc.scan2_time, tc.scan3_time, m.name AS medicine_name, m.price
         FROM medicine_trace_codes tc
         JOIN medicines m ON tc.medicine_id = m.id
         WHERE tc.trace_code = ?
         FOR UPDATE`,
        [traceCode]
      );

      if (traceRows.length === 0) {
        throw httpError(400, `追溯码不存在: ${traceCode}`);
      }

      const trace = traceRows[0];
      if (Number(trace.medicine_id) !== Number(item.medicine_id)) {
        throw httpError(400, `追溯码 ${traceCode} 不属于所选药品`);
      }
      if (trace.prescription_id) {
        throw httpError(400, `追溯码 ${traceCode} 已关联其他处方`);
      }
      if (trace.status !== 'pending' || trace.scan1_time || trace.scan2_time || trace.scan3_time) {
        throw httpError(400, `追溯码 ${traceCode} 已被扫描，不能用于新处方`);
      }

      totalAmount += Number(trace.price) * (item.quantity || 1);
      resolvedItems.push({ ...item, trace_code: traceCode, trace_code_id: trace.trace_code_id });
    }

    const prescriptionType = prescription_type || '普通';
    const prescriptionCode = await generatePrescriptionCode(prescriptionType, conn);

    const [prescResult] = await conn.query(
      `INSERT INTO prescriptions
       (patient_id, doctor_id, diagnosis, note, status, prescription_type, payment_type, medical_record_no, department, bed_no, total_amount, prescription_code)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [patient_id, req.user!.id, diagnosis, note || null, 'pending',
       prescriptionType, payment_type || '医保', medical_record_no || null,
       department || null, bed_no || null, totalAmount, prescriptionCode]
    );
    const prescriptionId = (prescResult as any).insertId;

    for (const item of resolvedItems) {
      const [itemResult] = await conn.query(
        `INSERT INTO prescription_items (prescription_id, medicine_id, drug_form, dosage, usage_method, frequency, days, quantity, note)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        [
          prescriptionId, item.medicine_id, item.drug_form || null,
          item.dosage, item.usage_method || '口服', item.frequency || '每日3次',
          item.days || 3, item.quantity || 1, item.note || null,
        ]
      );
      const prescriptionItemId = (itemResult as any).insertId;

      await conn.query(
        'UPDATE medicine_trace_codes SET prescription_id = ? WHERE id = ?',
        [prescriptionId, item.trace_code_id]
      );
      await conn.query(
        `INSERT INTO prescription_trace_codes (prescription_id, prescription_item_id, medicine_id, trace_code_id)
         VALUES (?, ?, ?, ?)`,
        [prescriptionId, prescriptionItemId, item.medicine_id, item.trace_code_id]
      );
    }

    await appendAuditRecord(conn, {
      eventType: 'PRESCRIPTION_CREATED',
      entityType: 'prescription',
      entityId: prescriptionId,
      flowStatus: 'prescription_created',
      traceCodes: resolvedItems.map((item) => item.trace_code),
      prescriptionId,
      prescriptionCode,
      operatorId: req.user!.id,
    });

    await conn.commit();
    res.status(201).json({ id: prescriptionId, prescription_code: prescriptionCode, message: '处方已提交，等待药师审核' });
  } catch (err: any) {
    await conn.rollback();
    if (err.status) {
      res.status(err.status).json({ error: err.message });
      return;
    }
    res.status(500).json({ error: '服务器错误: ' + err.message });
  } finally {
    conn.release();
  }
});

// GET /api/prescriptions — list (filtered by role)
router.get('/', async (req: Request, res: Response) => {
  try {
    const page = parseInt(req.query.page as string) || 1;
    const pageSize = parseInt(req.query.pageSize as string) || 10;
    const status = req.query.status as string;
    const prescriptionType = req.query.prescription_type as string;
    const offset = (page - 1) * pageSize;
    const user = req.user!;

    const conditions: string[] = [];
    const params: any[] = [];

    // Doctor sees their own prescriptions; pharmacist/admin sees all
    if (user.role === 'doctor') {
      conditions.push('p.doctor_id = ?');
      params.push(user.id);
    }

    if (status) {
      conditions.push('p.status = ?');
      params.push(status);
    }

    if (prescriptionType) {
      conditions.push('p.prescription_type = ?');
      params.push(prescriptionType);
    }

    const whereClause = conditions.length > 0 ? 'WHERE ' + conditions.join(' AND ') : '';

    const [countRows] = await pool.query<any[]>(
      `SELECT COUNT(*) as total FROM prescriptions p ${whereClause}`,
      params.length ? params : undefined
    );
    const total = countRows[0]?.total || 0;

    const listParams = [...params, pageSize, offset];
    const [list] = await pool.query(
      `SELECT p.*, pt.name as patient_name, u.real_name as doctor_name
       FROM prescriptions p
       LEFT JOIN patients pt ON p.patient_id = pt.id
       LEFT JOIN users u ON p.doctor_id = u.id
       ${whereClause}
       ORDER BY p.created_at DESC
       LIMIT ? OFFSET ?`,
      listParams
    );

    res.json({ total, page, pageSize, list });
  } catch (err: any) {
    res.status(500).json({ error: '服务器错误: ' + err.message });
  }
});

// GET /api/prescriptions/:id — detail with items
router.get('/:id', async (req: Request, res: Response) => {
  try {
    const id = parseInt(req.params.id);

    const [prescriptions] = await pool.query<any[]>(
      `SELECT p.*, pt.name as patient_name, pt.gender as patient_gender, pt.age as patient_age,
              u.real_name as doctor_name
       FROM prescriptions p
       LEFT JOIN patients pt ON p.patient_id = pt.id
       LEFT JOIN users u ON p.doctor_id = u.id
       WHERE p.id = ?`,
      [id]
    );

    if (prescriptions.length === 0) {
      res.status(404).json({ error: '处方不存在' });
      return;
    }

    const prescription = prescriptions[0];

    await ensurePrescriptionTraceCodesTable(pool);

    // Get items
    const [items] = await pool.query(
      `SELECT pi.*, m.name as medicine_name, m.specification, m.manufacturer, m.unit,
              tc.trace_code, tc.status AS trace_status, tc.scan1_time, tc.scan2_time, tc.scan3_time
       FROM prescription_items pi
       LEFT JOIN medicines m ON pi.medicine_id = m.id
       LEFT JOIN prescription_trace_codes ptc ON ptc.prescription_item_id = pi.id
       LEFT JOIN medicine_trace_codes tc ON tc.id = ptc.trace_code_id
       WHERE pi.prescription_id = ?`,
      [id]
    );

    res.json({ ...prescription, items });
  } catch (err: any) {
    res.status(500).json({ error: '服务器错误: ' + err.message });
  }
});

// PUT /api/prescriptions/:id/review — pharmacist review
router.put('/:id/review', requireRole('pharmacist', 'admin'), async (req: Request, res: Response) => {
  try {
    const id = parseInt(req.params.id);
    const { status, note } = req.body;

    if (!['approved', 'rejected'].includes(status)) {
      res.status(400).json({ error: '审核状态只能是 approved 或 rejected' });
      return;
    }

    // Check prescription exists and is pending
    const [checkRows] = await pool.query<any[]>(
      'SELECT status FROM prescriptions WHERE id = ?',
      [id]
    );

    if (checkRows.length === 0) {
      res.status(404).json({ error: '处方不存在' });
      return;
    }

    if (checkRows[0].status !== 'pending') {
      res.status(400).json({ error: '该处方已被审核，无法重复操作' });
      return;
    }

    await pool.query(
      'UPDATE prescriptions SET status=?, pharmacist_review_id=?, reviewed_at=NOW(), note=COALESCE(NULLIF(?, \'\'), note) WHERE id=?',
      [status, req.user!.id, note || null, id]
    );

    const msg = status === 'approved' ? '处方审核已通过' : '处方已被驳回';
    res.json({ message: msg });
  } catch (err: any) {
    res.status(500).json({ error: '服务器错误: ' + err.message });
  }
});

// PUT /api/prescriptions/:id/dispense — confirm dispensing
router.put('/:id/dispense', requireRole('pharmacist', 'admin'), async (req: Request, res: Response) => {
  try {
    const id = parseInt(req.params.id);

    const [checkRows] = await pool.query<any[]>(
      'SELECT status FROM prescriptions WHERE id = ?',
      [id]
    );

    if (checkRows.length === 0) {
      res.status(404).json({ error: '处方不存在' });
      return;
    }

    if (checkRows[0].status !== 'approved') {
      res.status(400).json({ error: '只有审核通过的处方才能发药' });
      return;
    }

    await pool.query(
      'UPDATE prescriptions SET status=\'dispensed\', pharmacist_dispense_id=?, dispensed_at=NOW() WHERE id=?',
      [req.user!.id, id]
    );

    res.json({ message: '药品已发放' });
  } catch (err: any) {
    res.status(500).json({ error: '服务器错误: ' + err.message });
  }
});

// DELETE /api/prescriptions/all — delete all prescriptions and their items
router.delete('/all', async (_req: Request, res: Response) => {
  const conn = await pool.getConnection();
  try {
    await ensurePrescriptionTraceCodesTable(conn);
    await conn.beginTransaction();

    const [traceRows] = await conn.query<any[]>(
      `SELECT DISTINCT tc.id
       FROM medicine_trace_codes tc
       LEFT JOIN prescription_trace_codes ptc ON ptc.trace_code_id = tc.id
       WHERE tc.prescription_id IS NOT NULL OR ptc.prescription_id IS NOT NULL`
    );
    const traceCodeIds = traceRows.map((row) => row.id);

    await conn.query('DELETE FROM prescription_trace_codes');
    if (traceCodeIds.length > 0) {
      await conn.query(
        `DELETE FROM medicine_trace_codes WHERE id IN (${traceCodeIds.map(() => '?').join(', ')})`,
        traceCodeIds
      );
    }
    await conn.query('DELETE FROM prescription_items');
    const [result] = await conn.query('DELETE FROM prescriptions');
    await conn.commit();

    res.json({ message: `已删除 ${(result as any).affectedRows || 0} 条处方，已删除 ${traceCodeIds.length} 个关联追溯码` });
  } catch (err: any) {
    await conn.rollback();
    res.status(500).json({ error: '服务器错误: ' + err.message });
  } finally {
    conn.release();
  }
});

// DELETE /api/prescriptions/:id — delete prescription and its items
router.delete('/:id', async (req: Request, res: Response) => {
  const conn = await pool.getConnection();
  try {
    const id = parseInt(req.params.id);

    const [checkRows] = await conn.query<any[]>(
      'SELECT id FROM prescriptions WHERE id = ?', [id]
    );

    if (checkRows.length === 0) {
      res.status(404).json({ error: '处方不存在' });
      return;
    }

    await ensurePrescriptionTraceCodesTable(conn);
    await conn.beginTransaction();

    const [traceRows] = await conn.query<any[]>(
      `SELECT DISTINCT tc.id
       FROM medicine_trace_codes tc
       LEFT JOIN prescription_trace_codes ptc ON ptc.trace_code_id = tc.id
       WHERE tc.prescription_id = ? OR ptc.prescription_id = ?`,
      [id, id]
    );
    const traceCodeIds = traceRows.map((row) => row.id);

    await conn.query('DELETE FROM prescription_trace_codes WHERE prescription_id = ?', [id]);
    if (traceCodeIds.length > 0) {
      await conn.query(
        `DELETE FROM medicine_trace_codes WHERE id IN (${traceCodeIds.map(() => '?').join(', ')})`,
        traceCodeIds
      );
    }
    await conn.query('DELETE FROM prescription_items WHERE prescription_id = ?', [id]);
    await conn.query('DELETE FROM prescriptions WHERE id = ?', [id]);
    await conn.commit();

    res.json({ message: `处方已删除，已删除 ${traceCodeIds.length} 个关联追溯码` });
  } catch (err: any) {
    await conn.rollback();
    res.status(500).json({ error: '服务器错误: ' + err.message });
  } finally {
    conn.release();
  }
});

export default router;
