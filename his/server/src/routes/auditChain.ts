import { Router, Request, Response } from 'express';
import pool from '../db';
import { authMiddleware } from '../middleware/auth';
import { ensureAuditChainTable, verifyAuditChain } from '../services/auditChain';

const router = Router();
router.use(authMiddleware);

router.get('/', async (req: Request, res: Response) => {
  try {
    const page = parseInt(req.query.page as string) || 1;
    const pageSize = Math.min(parseInt(req.query.pageSize as string) || 20, 100);
    const offset = (page - 1) * pageSize;

    await ensureAuditChainTable(pool);
    const [countRows] = await pool.query<any[]>('SELECT COUNT(*) AS total FROM audit_chain_records');
    const [list] = await pool.query(
      `SELECT id, event_type, entity_type, entity_id, trace_code_hash, prescription_hash,
              operator_hash, flow_status, event_time, payload_hash, previous_hash, current_hash, created_at
       FROM audit_chain_records
       ORDER BY id DESC
       LIMIT ? OFFSET ?`,
      [pageSize, offset]
    );

    res.json({ total: countRows[0]?.total || 0, page, pageSize, list });
  } catch (err: any) {
    res.status(500).json({ error: 'Server error: ' + err.message });
  }
});

router.get('/verify', async (_req: Request, res: Response) => {
  const conn = await pool.getConnection();
  try {
    const result = await verifyAuditChain(conn);
    res.json(result);
  } catch (err: any) {
    res.status(500).json({ error: 'Server error: ' + err.message });
  } finally {
    conn.release();
  }
});

export default router;
