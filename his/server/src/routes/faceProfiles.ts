import { Router, Request, Response } from 'express';
import pool from '../db';
import { authMiddleware } from '../middleware/auth';
import { ensureDeliverySchema } from '../services/deliverySchema';
import { validateFaceImage } from '../services/faceCompare';

const router = Router();
router.use(authMiddleware);

const validImage = (value: unknown) => typeof value === 'string'
  && /^data:image\/(jpeg|jpg|png|webp);base64,/i.test(value)
  && value.length <= 5 * 1024 * 1024;

router.get('/', async (req: Request, res: Response) => {
  try {
    await ensureDeliverySchema(pool);
    const [rows] = await pool.query<any[]>('SELECT id, created_at, updated_at FROM face_profiles WHERE user_id = ?', [req.user!.id]);
    res.json({ enrolled: rows.length > 0, profile: rows[0] || null });
  } catch (err: any) { res.status(500).json({ error: '获取人脸认证状态失败: ' + err.message }); }
});

router.put('/', async (req: Request, res: Response) => {
  try {
    const { face_image } = req.body;
    if (!validImage(face_image)) {
      res.status(400).json({ error: '请使用摄像头拍摄清晰的人脸照片（JPG、PNG 或 WEBP，5MB 以内）' });
      return;
    }
    try {
      await validateFaceImage(face_image);
    } catch (err: any) {
      res.status(400).json({ error: err.message || '未检测到清晰人脸' });
      return;
    }
    await ensureDeliverySchema(pool);
    await pool.query(`INSERT INTO face_profiles (user_id, face_image) VALUES (?, ?)
      ON DUPLICATE KEY UPDATE face_image = VALUES(face_image), updated_at = NOW()`, [req.user!.id, face_image]);
    res.json({ message: '人脸信息已录入，可用于配送核验', enrolled: true });
  } catch (err: any) { res.status(500).json({ error: '保存人脸信息失败: ' + err.message }); }
});

export default router;
