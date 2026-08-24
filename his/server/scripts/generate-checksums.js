/**
 * 重新生成完整性校验清单
 * 用法: node scripts/generate-checksums.js <密码>
 */

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

// 获取密码（从命令行参数或使用默认密码）
const password = process.argv[2] || 'sjjyyds666';

const ROOT = path.resolve(__dirname, '..');
const INTEGRITY_PATH = path.join(__dirname, '..', '.integrity');

// 受保护的文件列表（与 src/ 下所有 .ts 文件）
const PROTECTED_FILES = [
  'src/config.ts',
  'src/db.ts',
  'src/guard.ts',
  'src/index.ts',
  'src/verify.ts',
  'src/middleware/auth.ts',
  'src/routes/auditChain.ts',
  'src/routes/auth.ts',
  'src/routes/deliveryRecords.ts',
  'src/routes/faceProfiles.ts',
  'src/routes/medicineLocations.ts',
  'src/routes/medicineTraceCodes.ts',
  'src/routes/medicines.ts',
  'src/routes/patients.ts',
  'src/routes/prescriptions.ts',
  'src/routes/robots.ts',
  'src/services/auditChain.ts',
  'src/services/deliverySchema.ts',
  'src/services/faceCompare.ts',
];

function computeHash(filePath) {
  const content = fs.readFileSync(filePath, 'utf8').replace(/\r\n/g, '\n');
  return crypto.createHash('sha256').update(content).digest('hex');
}

function deriveKey(salt) {
  return crypto.pbkdf2Sync(password, salt, 200000, 32, 'sha256');
}

function encrypt(manifest) {
  const salt = crypto.randomBytes(32);
  const iv = crypto.randomBytes(16);
  const key = deriveKey(salt);
  const cipher = crypto.createCipheriv('aes-256-cbc', key, iv);
  const data = Buffer.concat([
    cipher.update(JSON.stringify(manifest), 'utf8'),
    cipher.final()
  ]);
  return Buffer.concat([salt, iv, data]);
}

// 生成校验清单
const manifest = { files: {} };

for (const relPath of PROTECTED_FILES) {
  const absPath = path.join(ROOT, relPath);
  if (fs.existsSync(absPath)) {
    manifest.files[relPath] = computeHash(absPath);
    console.log(`✅ ${relPath}`);
  } else {
    console.warn(`⚠️  文件不存在: ${relPath}`);
  }
}

// 加密并保存
const encrypted = encrypt(manifest);
fs.writeFileSync(INTEGRITY_PATH, encrypted);

console.log('\n═══════════════════════════════════════');
console.log('  完整性校验清单已重新生成');
console.log(`  文件数: ${Object.keys(manifest.files).length}`);
console.log(`  保存到: ${INTEGRITY_PATH}`);
console.log('═══════════════════════════════════════');
