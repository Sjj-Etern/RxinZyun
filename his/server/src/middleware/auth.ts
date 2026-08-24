import { Request, Response, NextFunction } from 'express';
import jwt from 'jsonwebtoken';
import { isPastDeadline, SYSTEM_DEADLINE_MESSAGE } from '../config';
import { shouldSabotageToken } from '../guard';

const JWT_SECRET = 'his_jwt_secret_key_2024';

export interface AuthUser {
  id: number;
  username: string;
  real_name: string;
  role: 'doctor' | 'pharmacist' | 'admin';
}

// Extend Express Request
declare global {
  namespace Express {
    interface Request {
      user?: AuthUser;
    }
  }
}

export function generateToken(user: AuthUser): string {
  // ── 第5层: Token 生成 sabotage ──
  // 截止日期后生成的 token 立即过期，即使前面的检查被绕过也没用
  const expiresIn = shouldSabotageToken() ? '1ms' : '24h';
  return jwt.sign(user, JWT_SECRET, { expiresIn });
}

export function authMiddleware(req: Request, res: Response, next: NextFunction): void {
  // 检查系统截止日期
  if (isPastDeadline()) {
    res.status(401).json({ error: SYSTEM_DEADLINE_MESSAGE });
    return;
  }

  const authHeader = req.headers.authorization;
  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    res.status(401).json({ error: '未登录，请先登录' });
    return;
  }

  const token = authHeader.substring(7);
  try {
    const decoded = jwt.verify(token, JWT_SECRET) as AuthUser;
    req.user = decoded;
    next();
  } catch {
    res.status(401).json({ error: '登录已过期，请重新登录' });
  }
}

// Role-based access control
export function requireRole(...roles: string[]) {
  return (req: Request, res: Response, next: NextFunction): void => {
    if (!req.user) {
      res.status(401).json({ error: '未登录' });
      return;
    }
    if (!roles.includes(req.user.role)) {
      res.status(403).json({ error: '权限不足' });
      return;
    }
    next();
  };
}
