import http from 'http';

type FaceServiceResponse = {
  matched?: boolean;
  score?: number;
  threshold?: number;
  face_detected?: boolean;
  message?: string;
  detail?: string;
};

const baseUrl = process.env.FACE_COMPARE_URL || 'http://127.0.0.1:8000/api/v1/face';

function post(path: string, payload: Record<string, string>): Promise<FaceServiceResponse> {
  const target = new URL(`${baseUrl}${path}`);
  const body = JSON.stringify(payload);
  return new Promise((resolve, reject) => {
    const request = http.request({
      hostname: target.hostname,
      port: target.port || 80,
      path: target.pathname,
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) },
      timeout: 15000,
    }, (response) => {
      let raw = '';
      response.setEncoding('utf8');
      response.on('data', (chunk) => { raw += chunk; });
      response.on('end', () => {
        try {
          const data = JSON.parse(raw) as FaceServiceResponse;
          if ((response.statusCode || 500) >= 400) reject(new Error(data.detail || 'OpenCV 人脸服务处理失败'));
          else resolve(data);
        } catch { reject(new Error('OpenCV 人脸服务返回无效数据')); }
      });
    });
    request.on('timeout', () => request.destroy(new Error('OpenCV 人脸服务响应超时')));
    request.on('error', () => reject(new Error('OpenCV 人脸服务不可用，请确认 hospital_back 已启动')));
    request.write(body);
    request.end();
  });
}

export async function validateFaceImage(faceImage: string): Promise<void> {
  const result = await post('/validate', { face_image: faceImage });
  if (!result.face_detected) throw new Error(result.message || '未检测到人脸');
}

export async function compareFaceImages(referenceImage: string, candidateImage: string): Promise<{ matched: boolean; score: number; threshold: number; message: string }> {
  const result = await post('/compare', { reference_image: referenceImage, candidate_image: candidateImage });
  return {
    matched: Boolean(result.matched), score: Number(result.score || 0),
    threshold: Number(result.threshold || 0), message: result.message || '人脸比对未通过',
  };
}
