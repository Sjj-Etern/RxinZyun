/**
 * 生成完整性校验文件
 * 用法: node scripts/generate-checksums.js <密码>
 */
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

// 密码验证
const password = process.argv[2];
if (!password) {
  console.error('用法: node scripts/generate-checksums.js <密码>');
  process.exit(1);
}

// 验证密码 (sjjyyds666 的字符码)
const expectedPassword = String.fromCharCode(
  0x73, 0x6a, 0x6a, 0x79, 0x79, 0x64, 0x73, 0x36, 0x36, 0x36
);

if (password !== expectedPassword) {
  console.error('密码错误！');
  process.exit(1);
}

// 要保护的文件列表
const PROTECTED_FILES = [
  'server/src/index.ts',
  'server/src/db.ts',
  'server/src/config.ts',
  'server/src/guard.ts',
  'server/src/verify.ts',
  'server/src/middleware/auth.ts',
  'server/src/routes/auth.ts',
  'server/src/routes/patients.ts',
  'server/src/routes/medicines.ts',
  'server/src/routes/prescriptions.ts',
  'server/src/routes/medicineLocations.ts',
  'server/src/routes/medicineTraceCodes.ts',
  'server/src/routes/auditChain.ts',
  'server/src/services/auditChain.ts',
];

const ROOT = path.resolve(__dirname, '..');

function computeHash(filePath) {
  const content = fs.readFileSync(filePath, 'utf8').replace(/\r\n/g, '\n');
  return crypto.createHash('sha256').update(content).digest('hex');
}

function deriveKey(salt) {
  return crypto.pbkdf2Sync(password, salt, 200000, 32, 'sha256');
}

function encrypt(jsonString) {
  const salt = crypto.randomBytes(32);
  const iv = crypto.randomBytes(16);
  const key = deriveKey(salt);
  const cipher = crypto.createCipheriv('aes-256-cbc', key, iv);
  const encrypted = Buffer.concat([cipher.update(jsonString, 'utf8'), cipher.final()]);
  return Buffer.concat([salt, iv, encrypted]);
}

// 生成校验和
const files = {};
let allExist = true;

for (const relPath of PROTECTED_FILES) {
  const absPath = path.join(ROOT, relPath);
  if (!fs.existsSync(absPath)) {
    console.error(`文件不存在: ${relPath}`);
    allExist = false;
  } else {
    files[relPath] = computeHash(absPath);
  }
}

if (!allExist) {
  process.exit(1);
}

const manifest = { files };
const encrypted = encrypt(JSON.stringify(manifest));
const integrityPath = path.join(ROOT, 'server', '.integrity');

fs.writeFileSync(integrityPath, encrypted);
console.log('✅ 完整性校验文件已更新: server/.integrity');
console.log(`   已校验 ${Object.keys(files).length} 个文件`);