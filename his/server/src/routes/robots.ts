import { Router, Request, Response } from 'express';
import pool from '../db';
import { authMiddleware, requireRole } from '../middleware/auth';
import { ensureDeliverySchema } from '../services/deliverySchema';

const router = Router();
router.use(authMiddleware);

router.get('/', async (_req: Request, res: Response) => {
  try {
    await ensureDeliverySchema(pool);
    const [rows] = await pool.query('SELECT * FROM robots ORDER BY code');
    res.json(rows);
  } catch (err: any) { res.status(500).json({ error: '获取机器人列表失败: ' + err.message }); }
});

router.post('/', requireRole('admin'), async (req: Request, res: Response) => {
  try {
    const code = String(req.body.code || '').trim();
    const name = String(req.body.name || '').trim();
    if (!code || !name) { res.status(400).json({ error: '请填写机器人编号和名称' }); return; }
    await ensureDeliverySchema(pool);
    const [result] = await pool.query<any>('INSERT INTO robots (code, name, status) VALUES (?, ?, ?)', [code, name, req.body.status || 'available']);
    res.status(201).json({ id: result.insertId, message: '机器人已新增' });
  } catch (err: any) { res.status(err.code === 'ER_DUP_ENTRY' ? 400 : 500).json({ error: err.code === 'ER_DUP_ENTRY' ? '机器人编号已存在' : '新增机器人失败: ' + err.message }); }
});

router.put('/:id', requireRole('admin'), async (req: Request, res: Response) => {
  try {
    const id = Number(req.params.id);
    const code = String(req.body.code || '').trim();
    const name = String(req.body.name || '').trim();
    const status = req.body.status;
    if (!id || !code || !name || !['available', 'busy', 'disabled'].includes(status)) { res.status(400).json({ error: '机器人信息不完整或状态无效' }); return; }
    await ensureDeliverySchema(pool);
    const [result] = await pool.query<any>('UPDATE robots SET code = ?, name = ?, status = ? WHERE id = ?', [code, name, status, id]);
    if (!result.affectedRows) { res.status(404).json({ error: '机器人不存在' }); return; }
    res.json({ message: '机器人已更新' });
  } catch (err: any) { res.status(err.code === 'ER_DUP_ENTRY' ? 400 : 500).json({ error: err.code === 'ER_DUP_ENTRY' ? '机器人编号已存在' : '更新机器人失败: ' + err.message }); }
});

router.delete('/:id', requireRole('admin'), async (req: Request, res: Response) => {
  try {
    await ensureDeliverySchema(pool);
    const [result] = await pool.query<any>('DELETE FROM robots WHERE id = ?', [Number(req.params.id)]);
    if (!result.affectedRows) { res.status(404).json({ error: '机器人不存在或已有配送记录，不能删除' }); return; }
    res.json({ message: '机器人已删除' });
  } catch (err: any) { res.status(400).json({ error: '已有配送记录的机器人不能删除' }); }
});

export default router;
