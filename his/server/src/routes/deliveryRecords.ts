import { Router, Request, Response } from 'express';
import pool from '../db';
import { authMiddleware, requireRole } from '../middleware/auth';
import { ensureDeliverySchema } from '../services/deliverySchema';
import { compareFaceImages } from '../services/faceCompare';

const router = Router();
router.use(authMiddleware);

const selectRecords = `SELECT dr.*, p.prescription_code, p.doctor_id, pt.name AS patient_name,
  pi.quantity, pi.dosage, pi.usage_method, m.name AS medicine_name, m.unit,
  r.code AS robot_code, r.name AS robot_name, dispatcher.real_name AS dispatched_by_name,
  verifier.real_name AS verified_by_name
  FROM delivery_records dr
  JOIN prescriptions p ON p.id = dr.prescription_id
  JOIN prescription_items pi ON pi.id = dr.prescription_item_id
  JOIN medicines m ON m.id = pi.medicine_id
  JOIN patients pt ON pt.id = p.patient_id
  JOIN robots r ON r.id = dr.robot_id
  JOIN users dispatcher ON dispatcher.id = dr.dispatched_by
  LEFT JOIN users verifier ON verifier.id = dr.verified_by`;

router.get('/', async (req: Request, res: Response) => {
  try {
    await ensureDeliverySchema(pool);
    const conditions: string[] = [];
    const params: any[] = [];
    if (req.user!.role === 'doctor') { conditions.push('p.doctor_id = ?'); params.push(req.user!.id); }
    if (req.query.status) { conditions.push('dr.status = ?'); params.push(req.query.status); }
    const where = conditions.length ? ` WHERE ${conditions.join(' AND ')}` : '';
    const [rows] = await pool.query<any[]>(`${selectRecords}${where} ORDER BY FIELD(dr.status, 'arrived', 'delivering', 'unlocked'), dr.dispatched_at DESC`, params);
    res.json(rows);
  } catch (err: any) { res.status(500).json({ error: '获取配送记录失败: ' + err.message }); }
});

router.post('/:id/simulate-arrival', requireRole('pharmacist', 'admin'), async (req: Request, res: Response) => {
  try {
    await ensureDeliverySchema(pool);
    const [result] = await pool.query<any>(`UPDATE delivery_records SET status = 'arrived', arrived_at = NOW()
      WHERE id = ? AND status = 'delivering'`, [Number(req.params.id)]);
    if (!result.affectedRows) { res.status(400).json({ error: '该配送记录不是配送中状态，不能模拟到达' }); return; }
    res.json({ message: '机器人已到达，已向医生端发送“药物已送到，请医生核验”信号' });
  } catch (err: any) { res.status(500).json({ error: '模拟机器人到达失败: ' + err.message }); }
});

router.post('/:id/verify-and-unlock', requireRole('doctor', 'admin'), async (req: Request, res: Response) => {
  const conn = await pool.getConnection();
  try {
    const faceImage = req.body.face_image;
    if (typeof faceImage !== 'string' || !/^data:image\/(jpeg|jpg|png|webp);base64,/i.test(faceImage)) {
      res.status(400).json({ error: '请使用本地摄像头拍摄当前人脸后再核验' }); return;
    }
    await ensureDeliverySchema(conn);
    const [profiles] = await conn.query<any[]>('SELECT id, face_image FROM face_profiles WHERE user_id = ?', [req.user!.id]);
    if (!profiles.length) { res.status(400).json({ error: '请先在身份认证中录入人脸' }); return; }
    const comparison = await compareFaceImages(profiles[0].face_image, faceImage);
    if (!comparison.matched) {
      res.status(403).json({ error: comparison.message + '（相似度 ' + comparison.score.toFixed(2) + '，要求 ' + comparison.threshold.toFixed(2) + '）' });
      return;
    }
    await conn.beginTransaction();
    const [records] = await conn.query<any[]>(`SELECT dr.id, dr.robot_id FROM delivery_records dr
      JOIN prescriptions p ON p.id = dr.prescription_id
      WHERE dr.id = ? AND dr.status = 'arrived' AND p.doctor_id = ? FOR UPDATE`, [Number(req.params.id), req.user!.id]);
    if (!records.length) { await conn.rollback(); res.status(400).json({ error: '该药品尚未到达、已核验，或不属于您的处方' }); return; }
    const record = records[0];
    await conn.query(`UPDATE delivery_records SET status = 'unlocked', verified_by = ?, unlocked_at = NOW() WHERE id = ?`, [req.user!.id, record.id]);
    const [pending] = await conn.query<any[]>(`SELECT COUNT(*) AS total FROM delivery_records
      WHERE robot_id = ? AND status IN ('delivering', 'arrived')`, [record.robot_id]);
    if (!Number(pending[0].total)) await conn.query(`UPDATE robots SET status = 'available' WHERE id = ? AND status = 'busy'`, [record.robot_id]);
    await conn.commit();
    res.json({ message: '人脸比对成功（相似度 ' + comparison.score.toFixed(2) + '），机器人药箱已开锁（模拟）', verified: true, score: comparison.score });
  } catch (err: any) {
    await conn.rollback();
    res.status(500).json({ error: '核验开锁失败: ' + err.message });
  } finally { conn.release(); }
});

export default router;
