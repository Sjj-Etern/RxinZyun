import mysql from 'mysql2/promise';

const pool = mysql.createPool({
  host: process.env.MYSQL_HOST || '192.168.51.13',
  port: parseInt(process.env.MYSQL_PORT || '3306'),
  user: process.env.MYSQL_USER || 'ros',
  password: process.env.MYSQL_PASS || '123456',
  database: process.env.MYSQL_DB || 'test',
  waitForConnections: true,
  connectionLimit: 10,
  charset: 'utf8mb4',
});

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
