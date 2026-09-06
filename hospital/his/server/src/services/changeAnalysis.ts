import OpenAI from 'openai';
import { config } from '../config';

type ChangeInput = {
  prescriptionCode: string;
  actorName: string | null;
  actorSource: string;
  changes: Array<{ field: string; before: unknown; after: unknown }>;
};

const fallbackAnalysis = ({ actorName, actorSource, changes }: ChangeInput) => {
  const deletion = changes.find((item) => item.field === 'prescription' && item.after === null);
  const quantityChange = changes.find((item) => item.field.endsWith('.quantity'));
  const medicineChange = changes.find((item) => item.field.endsWith('.medicine_id') || item.field.endsWith('.medicine_name'));
  const actor = actorName
    ? `${actorName}（来源：${actorSource}）`
    : `无法可靠识别具体人员（仅确认来源：${actorSource}）`;
  let intent = '可能是业务纠错，也可能是绕过正常处方流程的异常改写，需要人工复核。';
  if (deletion) intent = '处方记录被删除，可能是正常撤销，也可能意图消除处方与发药痕迹；需核对删除权限、业务状态和操作日志。';
  if (quantityChange) intent = `药品数量由 ${String(quantityChange.before)} 改为 ${String(quantityChange.after)}，可能意图增加或减少实际发药量，存在剂量与库存风险。`;
  if (medicineChange) intent = '处方药品身份发生变化，可能意图替换药品；追溯码与药品可能不再匹配，风险较高。';
  return `疑似操作人：${actor}\n更改意图判断：${intent}\n处置建议：先冻结该处方配送，核对医嘱、操作日志与账号登录记录后，再决定是否接受新链。`;
};

export async function analyzePrescriptionChange(input: ChangeInput): Promise<{ text: string; source: 'deepseek' | 'rules' }> {
  if (!config.ai.deepseekApiKey) return { text: fallbackAnalysis(input), source: 'rules' };

  const openai = new OpenAI({
    baseURL: config.ai.deepseekBaseUrl,
    apiKey: config.ai.deepseekApiKey,
  });
  const completion = await openai.chat.completions.create({
    messages: [
      {
        role: 'system',
        content: '你是医院处方审计助手。只依据给出的证据分析，不得把推测写成事实。用简洁中文输出：疑似操作人、更改内容、可能意图、风险等级、处置建议。',
      },
      { role: 'user', content: JSON.stringify(input) },
    ],
    model: config.ai.deepseekModel,
    thinking: { type: 'enabled' },
    reasoning_effort: 'high',
    stream: false,
  } as any);
  return { text: completion.choices[0]?.message?.content || fallbackAnalysis(input), source: 'deepseek' };
}
