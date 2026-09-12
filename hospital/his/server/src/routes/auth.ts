import { Router, Request, Response } from 'express';
import bcrypt from 'bcryptjs';
import pool from '../db';
import { generateRefreshToken, generateToken, verifyRefreshToken, authMiddleware, AuthUser } from '../middleware/auth';

const router = Router();

// POST /api/auth/login
router.post('/login', async (req: Request, res: Response) => {
  try {
    const { username, password } = req.body;
    if (!username || typeof password !== 'string') {
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

    const authUser: AuthUser = {
      id: user.id,
      username: user.username,
      real_name: user.real_name,
      role: user.role,
    };
    const token = generateToken(authUser);
    const refreshToken = generateRefreshToken(authUser);

    res.json({
      token,
      refresh_token: refreshToken,
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

// POST /api/auth/refresh
router.post('/refresh', async (req: Request, res: Response) => {
  try {
    const refreshToken = String(req.body.refresh_token || '');
    if (!refreshToken) {
      res.status(401).json({ error: '登录已过期，请重新登录' });
      return;
    }

    const decoded = verifyRefreshToken(refreshToken);
    const [rows] = await pool.query<any[]>(
      'SELECT id, username, real_name, role FROM users WHERE id = ?',
      [decoded.id]
    );
    if (rows.length === 0) {
      res.status(401).json({ error: '登录已过期，请重新登录' });
      return;
    }

    const user: AuthUser = rows[0];
    res.json({
      token: generateToken(user),
      refresh_token: generateRefreshToken(user),
      user,
    });
  } catch {
    res.status(401).json({ error: '登录已过期，请重新登录' });
  }
});

// GET /api/auth/me
router.get('/me', authMiddleware, (req: Request, res: Response) => {
  res.json({ user: req.user });
});

export default router;
