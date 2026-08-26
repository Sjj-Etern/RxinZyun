import fs from 'fs';
import path from 'path';

const envFilePath = path.resolve(__dirname, '../../.env');
if (fs.existsSync(envFilePath)) {
  for (const line of fs.readFileSync(envFilePath, 'utf8').split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;

    const separator = trimmed.indexOf('=');
    if (separator === -1) continue;

    const name = trimmed.slice(0, separator).trim();
    let value = trimmed.slice(separator + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    if (process.env[name] === undefined) process.env[name] = value;
  }
}

const required = (name: string): string => {
  const value = process.env[name];
  if (!value) {
    throw new Error(`缺少环境变量 ${name}，请检查 his/.env`);
  }
  return value;
};

const numberValue = (name: string): number => {
  const value = Number(required(name));
  if (!Number.isFinite(value)) {
    throw new Error(`环境变量 ${name} 必须是数字`);
  }
  return value;
};

export const config = {
  server: {
    host: required('HIS_BACKEND_HOST'),
    port: numberValue('HIS_BACKEND_PORT'),
    corsOrigin: required('CORS_ORIGIN'),
    jsonBodyLimit: required('JSON_BODY_LIMIT'),
  },
  database: {
    host: required('MYSQL_HOST'),
    port: numberValue('MYSQL_PORT'),
    user: required('MYSQL_USER'),
    password: required('MYSQL_PASS'),
    database: required('MYSQL_DB'),
    connectionLimit: numberValue('MYSQL_CONNECTION_LIMIT'),
    charset: required('MYSQL_CHARSET'),
  },
  auth: {
    jwtSecret: required('JWT_SECRET'),
    jwtExpiresIn: required('JWT_EXPIRES_IN'),
    auditHashSalt: required('AUDIT_HASH_SALT'),
  },
  services: {
    faceCompareUrl: required('FACE_COMPARE_URL'),
    faceCompareTimeoutMs: numberValue('FACE_COMPARE_TIMEOUT_MS'),
    hospitalBackendUrl: required('HOSPITAL_BACKEND_URL'),
    hospitalBackendTimeoutMs: numberValue('HOSPITAL_BACKEND_TIMEOUT_MS'),
  },
};
