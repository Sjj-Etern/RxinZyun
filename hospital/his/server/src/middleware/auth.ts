import { Request, Response, NextFunction } from 'express';
import jwt from 'jsonwebtoken';
import { config } from '../config';

export interface AuthUser {
  id: number;
  username: string;
  real_name: string;
  role: 'doctor' | 'pharmacist' | 'admin';
}

type TokenPayload = AuthUser & { token_type?: 'access' | 'refresh' };

// Extend Express Request
declare global {
  namespace Express {
    interface Request {
      user?: AuthUser;
    }
  }
}

export function generateToken(user: AuthUser): string {
  return jwt.sign({ ...user, token_type: 'access' }, config.auth.jwtSecret, {
    expiresIn: config.auth.jwtExpiresIn as jwt.SignOptions['expiresIn'],
  });
}

export function generateRefreshToken(user: AuthUser): string {
  return jwt.sign({ ...user, token_type: 'refresh' }, config.auth.jwtSecret, {
    expiresIn: config.auth.jwtRefreshExpiresIn as jwt.SignOptions['expiresIn'],
  });
}

export function verifyRefreshToken(token: string): AuthUser {
  const decoded = jwt.verify(token, config.auth.jwtSecret) as TokenPayload;
  if (decoded.token_type !== 'refresh') throw new Error('Invalid refresh token');
  return { id: decoded.id, username: decoded.username, real_name: decoded.real_name, role: decoded.role };
}

export function authMiddleware(req: Request, res: Response, next: NextFunction): void {
  const authHeader = req.headers.authorization;
  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    res.status(401).json({ error: '未登录，请先登录' });
    return;
  }

  const token = authHeader.substring(7);
  try {
    const decoded = jwt.verify(token, config.auth.jwtSecret) as TokenPayload;
    if (decoded.token_type === 'refresh') throw new Error('Invalid access token');
    req.user = { id: decoded.id, username: decoded.username, real_name: decoded.real_name, role: decoded.role };
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
