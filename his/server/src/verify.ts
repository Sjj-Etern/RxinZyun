/**
 * ═══════════════════════════════════════════════════════════════
 * 完整性验证模块 — 自包含，不依赖项目其他模块
 *
 * 启动时解密 server/.integrity 校验清单，逐文件核验 SHA-256。
 * 运行时每60秒复查一次。任何文件被删除/篡改 → 服务器关停。
 *
 * 要修改受保护文件：运行 scripts/generate-checksums.js <密码>
 * ═══════════════════════════════════════════════════════════════
 */

import crypto from 'crypto';
import fs from 'fs';
import path from 'path';

// ── 密钥（字符码重建，防 grep）──
const _K = String.fromCharCode(
  0x73, 0x6a, 0x6a, 0x79, 0x79, 0x64, 0x73, 0x36, 0x36, 0x36
);

const ROOT = process.cwd();
const INTEGRITY_PATH = path.join(process.cwd(), '.integrity');

function deriveKey(salt: Buffer): Buffer {
  return crypto.pbkdf2Sync(_K, salt, 200000, 32, 'sha256');
}

function decrypt(encrypted: Buffer): string {
  const salt = encrypted.subarray(0, 32);
  const iv = encrypted.subarray(32, 48);
  const data = encrypted.subarray(48);
  const key = deriveKey(salt);
  const decipher = crypto.createDecipheriv('aes-256-cbc', key, iv);
  const decrypted = Buffer.concat([decipher.update(data), decipher.final()]);
  return decrypted.toString('utf8');
}

function computeHash(filePath: string): string {
  // 归一化换行符 (CRLF → LF)，确保跨平台哈希一致
  const content = fs.readFileSync(filePath, 'utf8').replace(/\r\n/g, '\n');
  return crypto.createHash('sha256').update(content).digest('hex');
}

let shutdownHook: (() => void) | null = null;

/**
 * 执行一次完整性校验
 * @returns true=通过, false=失败
 */
export function verifyIntegrity(): boolean {
  // 1. 校验清单文件是否存在
  if (!fs.existsSync(INTEGRITY_PATH)) {
    console.error('❌ [完整性保护] 校验清单 server/.integrity 不存在！');
    console.error('   系统已被篡改，拒绝继续运行。');
    return false;
  }

  // 2. 解密校验清单
  let manifest: { files: Record<string, string> };
  try {
    const encrypted = fs.readFileSync(INTEGRITY_PATH);
    const json = decrypt(encrypted);
    manifest = JSON.parse(json);
  } catch {
    console.error('❌ [完整性保护] 校验清单解密失败，可能已被篡改！');
    console.error('   系统拒绝继续运行。');
    return false;
  }

  // 3. 逐文件核验
  const entries = Object.entries(manifest.files);
  let passed = true;

  for (const [relPath, expectedHash] of entries) {
    const absPath = path.join(ROOT, relPath);

    if (!fs.existsSync(absPath)) {
      console.error(`❌ [完整性保护] 受保护文件缺失: ${relPath}`);
      passed = false;
      continue;
    }

    const actualHash = computeHash(absPath);
    if (actualHash !== expectedHash) {
      console.error(`❌ [完整性保护] 文件被篡改: ${relPath}`);
      console.error(`   期望: ${expectedHash.substring(0, 24)}...`);
      console.error(`   实际: ${actualHash.substring(0, 24)}...`);
      passed = false;
    }
  }

  if (passed) {
    console.log('✅ 完整性校验通过');
  } else {
    console.error('❌ 系统完整性校验失败，拒绝继续运行！');
  }

  return passed;
}

/**
 * 注册关停回调（供 index.ts 使用）
 */
export function onIntegrityFailure(cb: () => void): void {
  shutdownHook = cb;
}

/**
 * 启动运行时监控（每60秒复查一次）
 */
export function startIntegrityMonitor(): void {
  setInterval(() => {
    if (!verifyIntegrity()) {
      console.error('⚠️ 运行时检测到文件篡改，正在终止服务...');
      if (shutdownHook) {
        shutdownHook();
      } else {
        process.exit(1);
      }
    }
  }, 60000);
}
