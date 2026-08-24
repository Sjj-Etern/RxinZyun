import { Router, Request, Response } from 'express';
import pool from '../db';
import { authMiddleware } from '../middleware/auth';

const router = Router();
router.use(authMiddleware);

// GET /api/patients — list with pagination and search
router.get('/', async (req: Request, res: Response) => {
  try {
    const page = parseInt(req.query.page as string) || 1;
    const pageSize = parseInt(req.query.pageSize as string) || 10;
    const keyword = (req.query.keyword as string) || '';
    const offset = (page - 1) * pageSize;

    let countSql = 'SELECT COUNT(*) as total FROM patients';
    let listSql = 'SELECT * FROM patients';
    const params: any[] = [];

    if (keyword) {
      const where = ' WHERE name LIKE ? OR phone LIKE ?';
      countSql += where;
      listSql += where;
      params.push(`%${keyword}%`, `%${keyword}%`);
    }

    listSql += ' ORDER BY id DESC LIMIT ? OFFSET ?';

    const [countRows] = await pool.query<any[]>(countSql, params.length ? params : undefined);
    const total = countRows[0]?.total || 0;

    const listParams = [...params, pageSize, offset];
    const [patients] = await pool.query(listSql, listParams);

    res.json({ total, page, pageSize, list: patients });
  } catch (err: any) {
    res.status(500).json({ error: '服务器错误: ' + err.message });
  }
});

// POST /api/patients — create
router.post('/', async (req: Request, res: Response) => {
  try {
    const { name, gender, age, phone, id_card, address } = req.body;
    if (!name || !gender) {
      res.status(400).json({ error: '姓名和性别为必填项' });
      return;
    }

    const [result] = await pool.query(
      'INSERT INTO patients (name, gender, age, phone, id_card, address) VALUES (?, ?, ?, ?, ?, ?)',
      [name, gender, age || null, phone || null, id_card || null, address || null]
    );

    res.status(201).json({ id: (result as any).insertId, message: '病人信息已保存' });
  } catch (err: any) {
    res.status(500).json({ error: '服务器错误: ' + err.message });
  }
});

// GET /api/patients/:id — detail with prescription history
router.get('/:id', async (req: Request, res: Response) => {
  try {
    const id = parseInt(req.params.id);

    const [patients] = await pool.query<any[]>('SELECT * FROM patients WHERE id = ?', [id]);
    if (patients.length === 0) {
      res.status(404).json({ error: '病人不存在' });
      return;
    }

    const patient = patients[0];

    // Get prescription history
    const [prescriptions] = await pool.query(
      `SELECT p.*, u.real_name as doctor_name
       FROM prescriptions p
       LEFT JOIN users u ON p.doctor_id = u.id
       WHERE p.patient_id = ?
       ORDER BY p.created_at DESC`,
      [id]
    );

    res.json({ ...patient, prescriptions });
  } catch (err: any) {
    res.status(500).json({ error: '服务器错误: ' + err.message });
  }
});

// PUT /api/patients/:id — update
router.put('/:id', async (req: Request, res: Response) => {
  try {
    const id = parseInt(req.params.id);
    const { name, gender, age, phone, id_card, address } = req.body;

    await pool.query(
      'UPDATE patients SET name=?, gender=?, age=?, phone=?, id_card=?, address=? WHERE id=?',
      [name, gender, age || null, phone || null, id_card || null, address || null, id]
    );

    res.json({ message: '病人信息已更新' });
  } catch (err: any) {
    res.status(500).json({ error: '服务器错误: ' + err.message });
  }
});

// DELETE /api/patients/:id — delete patient and related prescriptions
router.delete('/:id', async (req: Request, res: Response) => {
  const conn = await pool.getConnection();
  try {
    const id = parseInt(req.params.id);

    const [checkRows] = await conn.query<any[]>(
      'SELECT id FROM patients WHERE id = ?', [id]
    );

    if (checkRows.length === 0) {
      res.status(404).json({ error: '病人不存在' });
      return;
    }

    await conn.beginTransaction();

    // Delete prescription items for all prescriptions of this patient
    await conn.query(
      `DELETE pi FROM prescription_items pi
       INNER JOIN prescriptions p ON pi.prescription_id = p.id
       WHERE p.patient_id = ?`, [id]
    );

    // Delete prescriptions
    await conn.query('DELETE FROM prescriptions WHERE patient_id = ?', [id]);

    // Delete patient
    await conn.query('DELETE FROM patients WHERE id = ?', [id]);

    await conn.commit();
    res.json({ message: '病人及相关处方已删除' });
  } catch (err: any) {
    await conn.rollback();
    res.status(500).json({ error: '服务器错误: ' + err.message });
  } finally {
    conn.release();
  }
});

export default router;
