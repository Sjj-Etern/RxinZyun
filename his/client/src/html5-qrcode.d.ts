declare module 'html5-qrcode' {
  interface CameraDevice {
    id: string;
    label: string;
  }

  interface ScanConfig {
    fps?: number;
    qrbox?: { width: number; height: number };
    aspectRatio?: number;
    videoConstraints?: MediaTrackConstraints;
  }

  class Html5Qrcode {
    constructor(elementId: string);
    start(
      cameraIdOrConfig: string | MediaTrackConstraints,
      config: ScanConfig,
      onScanSuccess: (decodedText: string, decodedResult?: any) => void,
      onScanError?: (errorMessage: string) => void
    ): Promise<void>;
    stop(): Promise<void>;
    static getCameras(): Promise<CameraDevice[]>;
  }

  export { Html5Qrcode, CameraDevice, ScanConfig };
}
