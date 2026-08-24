import { Router, Request, Response } from 'express';
import pool from '../db';
import { authMiddleware } from '../middleware/auth';

const router = Router();
router.use(authMiddleware);

// GET /api/medicines — list with pagination and search
router.get('/', async (req: Request, res: Response) => {
  try {
    const page = parseInt(req.query.page as string) || 1;
    const pageSize = parseInt(req.query.pageSize as string) || 10;
    const keyword = (req.query.keyword as string) || '';
    const offset = (page - 1) * pageSize;

    let countSql = 'SELECT COUNT(*) as total FROM medicines m';
    let listSql = 'SELECT m.*, p.prefix AS trace_code_prefix FROM medicines m LEFT JOIN medicine_trace_prefixes p ON m.id = p.medicine_id';
    const params: any[] = [];

    if (keyword) {
      const where = ' WHERE m.name LIKE ? OR m.manufacturer LIKE ?';
      countSql += where;
      listSql += where;
      params.push(`%${keyword}%`, `%${keyword}%`);
    }

    listSql += ' ORDER BY m.id DESC LIMIT ? OFFSET ?';

    const [countRows] = await pool.query<any[]>(countSql, params);
    const total = (countRows[0] as any)?.total || 0;

    const listParams = [...params, pageSize, offset];
    const [medicines] = await pool.query(listSql, listParams);

    res.json({ total, page, pageSize, list: medicines });
  } catch (err: any) {
    res.status(500).json({ error: '服务器错误: ' + err.message });
  }
});

// POST /api/medicines — create
router.post('/', async (req: Request, res: Response) => {
  try {
    const { name, generic_name, specification, drug_form, manufacturer, unit, price, stock, category, is_narcotic, image_url, trace_code_prefix } = req.body;
    if (!name) {
      res.status(400).json({ error: '药品名称为必填项' });
      return;
    }

    const [result] = await pool.query(
      'INSERT INTO medicines (name, generic_name, specification, drug_form, manufacturer, unit, price, stock, category, is_narcotic, image_url) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
      [name, generic_name || null, specification || null, drug_form || null, manufacturer || null, unit || '盒', price || 0, stock || 0, category || '处方药', is_narcotic ? 1 : 0, image_url || null]
    );

    const insertId = (result as any).insertId;

    // 如果有前缀，保存到前缀表
    if (trace_code_prefix && /^\d{7}$/.test(trace_code_prefix)) {
      await pool.query(
        'INSERT INTO medicine_trace_prefixes (medicine_id, prefix) VALUES (?, ?)',
        [insertId, trace_code_prefix]
      );
    }

    res.status(201).json({ id: insertId, message: '药品信息已保存' });
  } catch (err: any) {
    res.status(500).json({ error: '服务器错误: ' + err.message });
  }
});

// PUT /api/medicines/:id — update
router.put('/:id', async (req: Request, res: Response) => {
  try {
    const id = parseInt(req.params.id);
    const { name, generic_name, specification, drug_form, manufacturer, unit, price, stock, category, is_narcotic, image_url, trace_code_prefix } = req.body;

    await pool.query(
      'UPDATE medicines SET name=?, generic_name=?, specification=?, drug_form=?, manufacturer=?, unit=?, price=?, stock=?, category=?, is_narcotic=?, image_url=? WHERE id=?',
      [name, generic_name || null, specification || null, drug_form || null, manufacturer || null, unit || '盒', price || 0, stock || 0, category || '处方药', is_narcotic ? 1 : 0, image_url || null, id]
    );

    // 处理前缀
    if (trace_code_prefix && /^\d{7}$/.test(trace_code_prefix)) {
      await pool.query(
        'INSERT INTO medicine_trace_prefixes (medicine_id, prefix) VALUES (?, ?) ON DUPLICATE KEY UPDATE prefix = VALUES(prefix)',
        [id, trace_code_prefix]
      );
    } else if (trace_code_prefix === '') {
      // 空字符串表示删除前缀
      await pool.query('DELETE FROM medicine_trace_prefixes WHERE medicine_id = ?', [id]);
    }

    res.json({ message: '药品信息已更新' });
  } catch (err: any) {
    res.status(500).json({ error: '服务器错误: ' + err.message });
  }
});

// DELETE /api/medicines/:id — delete
router.delete('/:id', async (req: Request, res: Response) => {
  try {
    const id = parseInt(req.params.id);

    const [checkRows] = await pool.execute<any[]>(
      'SELECT id FROM medicines WHERE id = ?', [id]
    );

    if (checkRows.length === 0) {
      res.status(404).json({ error: '药品不存在' });
      return;
    }

    await pool.query('DELETE FROM medicines WHERE id = ?', [id]);
    res.json({ message: '药品已删除' });
  } catch (err: any) {
    res.status(500).json({ error: '服务器错误: ' + err.message });
  }
});

// PUT /api/medicines/:id/prefix — 设置药品追溯码前缀
router.put('/:id/prefix', async (req: Request, res: Response) => {
  try {
    const medicineId = parseInt(req.params.id);
    const { prefix } = req.body;

    if (!prefix || !/^\d{7}$/.test(prefix)) {
      res.status(400).json({ error: '前缀必须为7位数字' });
      return;
    }

    // 检查药品是否存在
    const [medRows] = await pool.query<any[]>('SELECT id FROM medicines WHERE id = ?', [medicineId]);
    if (medRows.length === 0) {
      res.status(404).json({ error: '药品不存在' });
      return;
    }

    // UPSERT 前缀
    await pool.query(
      'INSERT INTO medicine_trace_prefixes (medicine_id, prefix) VALUES (?, ?) ON DUPLICATE KEY UPDATE prefix = VALUES(prefix)',
      [medicineId, prefix]
    );

    res.json({ message: '前缀已保存', medicine_id: medicineId, prefix });
  } catch (err: any) {
    res.status(500).json({ error: '服务器错误: ' + err.message });
  }
});

// DELETE /api/medicines/:id/prefix — 删除药品追溯码前缀
router.delete('/:id/prefix', async (req: Request, res: Response) => {
  try {
    const medicineId = parseInt(req.params.id);
    await pool.query('DELETE FROM medicine_trace_prefixes WHERE medicine_id = ?', [medicineId]);
    res.json({ message: '前缀已删除' });
  } catch (err: any) {
    res.status(500).json({ error: '服务器错误: ' + err.message });
  }
});

export default router;
