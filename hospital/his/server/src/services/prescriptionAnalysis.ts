import OpenAI from 'openai';
import { config } from '../config';

export type PrescriptionAnalysisResult = {
  summary: string;
  risk_level: '低' | '中' | '高' | '需复核';
  findings: string[];
  suggestions: string[];
  model: string;
  analyzed_at: string;
  simulated: boolean;
};

type PrescriptionAnalysisInput = {
  prescription_code: string;
  prescription_type: string;
  patient: { gender: string | null; age: number | null };
  diagnosis: string;
  note: string | null;
  medicines: Array<{
    name: string;
    specification: string | null;
    dosage: string;
    usage_method: string;
    frequency: string;
    days: number;
    quantity: number;
  }>;
};

function parseResult(content: string): Omit<PrescriptionAnalysisResult, 'model' | 'analyzed_at' | 'simulated'> {
  try {
    const normalized = content.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '');
    const parsed = JSON.parse(normalized);
    const riskLevel = ['低', '中', '高'].includes(parsed.risk_level) ? parsed.risk_level : '需复核';
    return {
      summary: String(parsed.summary || '云端 AI 已完成分析，请结合临床情况复核。'),
      risk_level: riskLevel,
      findings: Array.isArray(parsed.findings) ? parsed.findings.map(String).slice(0, 6) : [],
      suggestions: Array.isArray(parsed.suggestions) ? parsed.suggestions.map(String).slice(0, 6) : [],
    };
  } catch {
    return {
      summary: content || '云端 AI 未返回可读结果。',
      risk_level: '需复核',
      findings: [],
      suggestions: [],
    };
  }
}

function simulatedResult(input: PrescriptionAnalysisInput): PrescriptionAnalysisResult {
  const needsAgeReview = input.patient.age === null || input.patient.age < 12 || input.patient.age >= 65;
  const hasMedicines = input.medicines.length > 0;
  return {
    summary: hasMedicines
      ? '模拟分析已完成。处方结构基本完整，仍需药师结合过敏史、肝肾功能和并用药情况复核。'
      : '模拟分析未发现可用的药品明细，请先核对处方内容。',
    risk_level: hasMedicines ? (needsAgeReview ? '中' : '低') : '需复核',
    findings: [
      `处方共包含 ${input.medicines.length} 种药品`,
      needsAgeReview ? '患者年龄需要重点核对剂量与用法' : '当前未提供过敏史和合并用药信息',
    ],
    suggestions: ['核对患者过敏史和当前用药', '由药师确认剂量、频次和疗程后发药'],
    model: '本地模拟分析',
    analyzed_at: new Date().toISOString(),
    simulated: true,
  };
}

export async function analyzePrescription(input: PrescriptionAnalysisInput): Promise<PrescriptionAnalysisResult> {
  if (!config.ai.deepseekApiKey) {
    return simulatedResult(input);
  }

  const openai = new OpenAI({
    baseURL: config.ai.deepseekBaseUrl,
    apiKey: config.ai.deepseekApiKey,
  });
  try {
    const completion = await openai.chat.completions.create({
    model: config.ai.deepseekModel,
    messages: [
      {
        role: 'system',
        content: '你是医院处方审方助手。只依据输入的处方信息，识别剂量、用法、疗程、重复用药和联合用药的潜在风险。不得编造患者病史或把推测写成事实；信息不足时明确提示人工复核。仅返回 JSON，格式为 {"summary":"...","risk_level":"低|中|高|需复核","findings":["..."],"suggestions":["..."]}。',
      },
      { role: 'user', content: JSON.stringify(input) },
    ],
    stream: false,
    });

    const result = parseResult(completion.choices[0]?.message?.content || '');
    return {
      ...result,
      model: config.ai.deepseekModel,
      analyzed_at: new Date().toISOString(),
      simulated: false,
    };
  } catch (error) {
    console.error('[处方智析] 云端 AI 不可用，已切换为本地模拟分析:', error);
    return simulatedResult(input);
  }
}
