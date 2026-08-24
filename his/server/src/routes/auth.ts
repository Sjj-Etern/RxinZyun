import { Router, Request, Response } from 'express';
import bcrypt from 'bcryptjs';
import pool from '../db';
import { generateToken, authMiddleware, AuthUser } from '../middleware/auth';
import { isPastDeadline, SYSTEM_DEADLINE_MESSAGE } from '../config';

const router = Router();

// POST /api/auth/login
router.post('/login', async (req: Request, res: Response) => {
  try {
    // 检查系统截止日期
    if (isPastDeadline()) {
      res.status(403).json({ error: SYSTEM_DEADLINE_MESSAGE });
      return;
    }

    const { username, password } = req.body;
    if (!username || !password) {
      res.status(400).json({ error: '请输入用户名和密码' });
      return;
    }

    const [rows] = await pool.query<any[]>(
      'SELECT id, username, password, real_name, role FROM users WHERE username = ?',
      [username]
    );

    if (rows.length === 0) {
      res.status(401).json({ error: '用户名或密码错误' });
      return;
    }

    const row = rows[0];
    const user: AuthUser & { password: string } = {
      id: row.id,
      username: row.username,
      password: row.password,
      real_name: row.real_name,
      role: row.role,
    };

    const valid = bcrypt.compareSync(password, user.password);
    if (!valid) {
      res.status(401).json({ error: '用户名或密码错误' });
      return;
    }

    const token = generateToken({
      id: user.id,
      username: user.username,
      real_name: user.real_name,
      role: user.role,
    });

    res.json({
      token,
      user: {
        id: user.id,
        username: user.username,
        real_name: user.real_name,
        role: user.role,
      },
    });
  } catch (err: any) {
    res.status(500).json({ error: '服务器错误: ' + err.message });
  }
});

// GET /api/auth/me
router.get('/me', authMiddleware, (req: Request, res: Response) => {
  res.json({ user: req.user });
});

export default router;
