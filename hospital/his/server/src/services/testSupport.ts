import bcrypt from 'bcryptjs';

let testSupportSchemaReady = false;

export async function ensureTestSupport(conn: any): Promise<void> {
  if (testSupportSchemaReady) return;

  const [columns] = await conn.query(
    `SELECT COUNT(*) AS total FROM information_schema.COLUMNS
     WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'prescriptions' AND COLUMN_NAME = 'settled_at'`
  );
  if (!Number(columns[0]?.total || 0)) {
    await conn.query('ALTER TABLE prescriptions ADD COLUMN settled_at DATETIME NULL AFTER dispensed_at');
  }

  const [users] = await conn.query('SELECT id FROM users WHERE username = ? LIMIT 1', ['test']);
  if (!users.length) {
    // 测试账号使用空密码的 bcrypt 哈希；仅用于本地测试，不影响其他账号登录规则。
    await conn.query(
      'INSERT INTO users (username, password, real_name, role) VALUES (?, ?, ?, ?)',
      ['test', bcrypt.hashSync('', 10), 'test', 'doctor']
    );
  }

  testSupportSchemaReady = true;
}
