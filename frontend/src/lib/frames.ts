export interface CapturedFrame { id: string; base64: string; dataUrl: string; at: number }

/** Grab ONE frame from a live <video>, downscaled to maxDim and JPEG-compressed. Not continuous streaming. */
export function captureFrame(video: HTMLVideoElement, maxDim = 1024, quality = 0.8): CapturedFrame {
  if (!video.videoWidth || !video.videoHeight) throw new Error("Camera isn't showing video yet.");
  const scale = Math.min(1, maxDim / Math.max(video.videoWidth, video.videoHeight));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(video.videoWidth * scale);
  canvas.height = Math.round(video.videoHeight * scale);
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Could not capture a frame in this browser.");
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  const dataUrl = canvas.toDataURL("image/jpeg", quality);
  return { id: crypto.randomUUID(), base64: dataUrl.split(",")[1], dataUrl, at: Date.now() };
}

/** Convert an uploaded or picked image file into a downscaled, compressed CapturedFrame */
export async function fileToCapturedFrame(file: File, maxDim = 1024, quality = 0.8): Promise<CapturedFrame> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const img = new Image();
      img.onload = () => {
        const scale = Math.min(1, maxDim / Math.max(img.width, img.height));
        const canvas = document.createElement("canvas");
        canvas.width = Math.round(img.width * scale);
        canvas.height = Math.round(img.height * scale);
        const ctx = canvas.getContext("2d");
        if (!ctx) return reject(new Error("Canvas context unavailable."));
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        const dataUrl = canvas.toDataURL("image/jpeg", quality);
        resolve({
          id: crypto.randomUUID(),
          base64: dataUrl.split(",")[1],
          dataUrl,
          at: Date.now(),
        });
      };
      img.onerror = () => reject(new Error("Unable to load the selected image file."));
      img.src = reader.result as string;
    };
    reader.onerror = () => reject(new Error("Could not read the selected image file."));
    reader.readAsDataURL(file);
  });
}

