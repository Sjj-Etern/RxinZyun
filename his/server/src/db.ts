import mysql from 'mysql2/promise';
import { isLicenseInvalid } from './guard';

const pool = mysql.createPool({
  host: process.env.MYSQL_HOST || 'localhost',
  port: parseInt(process.env.MYSQL_PORT || '3306'),
  user: process.env.MYSQL_USER || 'root',
  password: process.env.MYSQL_PASS || '527725',
  database: process.env.MYSQL_DB || 'hospital',
  waitForConnections: true,
  connectionLimit: 10,
  charset: 'utf8mb4',
});

// ── 第2层: 数据库查询拦截 ──
// 包装 query 方法，截止日期后所有 SQL 查询直接拒绝
const _rawQuery = pool.query.bind(pool);
(pool as any).query = function () {
  if (isLicenseInvalid()) {
    return Promise.reject(new Error('系统已停止服务'));
  }
  return (_rawQuery as any).apply(pool, arguments);
};

// Test connection on startup
pool.getConnection()
  .then(conn => {
    console.log('✅ MySQL 数据库连接成功');
    conn.release();
  })
  .catch(err => {
    console.error('❌ MySQL 数据库连接失败:', err.message);
    process.exit(1);
  });

export default pool;
