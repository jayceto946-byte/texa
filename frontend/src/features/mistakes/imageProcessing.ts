export function imageUploadError(file: Pick<File, 'name' | 'size'>): string {
  if (/\.(heic|heif)$/i.test(file.name)) return '暂不支持 HEIC/HEIF，请在相机或相册中导出为 JPEG 后上传。';
  if (!/\.(png|jpe?g|webp|bmp)$/i.test(file.name)) return '请选择 JPEG、PNG、WebP 或 BMP 图片。';
  if (file.size === 0) return '图片为空，请重新选择。';
  if (file.size > 20 * 1024 * 1024) return '图片不能超过 20MB，请降低拍照分辨率后重试。';
  return '';
}

export type CropState = { x: number; y: number; w: number; h: number };

export type ImageAdjust = {
  brightness: number;
  contrast: number;
  sharpen: number;
  grayscale: boolean;
};

export function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

export function applySharpen(imageData: ImageData, amount: number) {
  if (amount <= 0) return imageData;
  const strength = amount / 100;
  const { data, width, height } = imageData;
  const copy = new Uint8ClampedArray(data);
  const center = 1 + 4 * strength;
  const side = -strength;
  for (let y = 1; y < height - 1; y += 1) {
    for (let x = 1; x < width - 1; x += 1) {
      const idx = (y * width + x) * 4;
      for (let channel = 0; channel < 3; channel += 1) {
        const value =
          copy[idx + channel] * center +
          copy[idx - 4 + channel] * side +
          copy[idx + 4 + channel] * side +
          copy[idx - width * 4 + channel] * side +
          copy[idx + width * 4 + channel] * side;
        data[idx + channel] = clamp(value, 0, 255);
      }
    }
  }
  return imageData;
}

async function fileToImage(file: File): Promise<HTMLImageElement> {
  const url = URL.createObjectURL(file);
  try {
    const image = new Image();
    image.decoding = 'async';
    await new Promise<void>((resolve, reject) => {
      image.onload = () => image.naturalWidth * image.naturalHeight > 40_000_000 ? reject(new Error('图片超过 4000 万像素，请降低分辨率后重试')) : resolve();
      image.onerror = () => reject(new Error('图片加载失败'));
      image.src = url;
    });
    return image;
  } finally {
    URL.revokeObjectURL(url);
  }
}

export async function renderProcessedImage(
  file: File,
  crop: CropState,
  adjust: ImageAdjust,
  rotation = 0,
): Promise<{ file: File; preview: string }> {
  let image = await fileToImage(file);
  if (rotation) {
    const rotated = document.createElement('canvas');
    rotated.width = image.naturalHeight;
    rotated.height = image.naturalWidth;
    const ctx = rotated.getContext('2d');
    if (!ctx) throw new Error('无法旋转图片');
    ctx.translate(rotated.width / 2, rotated.height / 2);
    ctx.rotate(Math.PI / 2);
    ctx.drawImage(image, -image.naturalWidth / 2, -image.naturalHeight / 2);
    const blob = await new Promise<Blob>((resolve, reject) => rotated.toBlob(next => next ? resolve(next) : reject(new Error('图片旋转失败')), 'image/jpeg', 0.95));
    image = await fileToImage(new File([blob], 'rotated.jpg', { type: 'image/jpeg' }));
  }
  const sx = Math.round((crop.x / 100) * image.naturalWidth);
  const sy = Math.round((crop.y / 100) * image.naturalHeight);
  const sw = Math.round((crop.w / 100) * image.naturalWidth);
  const sh = Math.round((crop.h / 100) * image.naturalHeight);
  const maxSide = 1800;
  const scale = Math.min(1, maxSide / Math.max(sw, sh));
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(1, Math.round(sw * scale));
  canvas.height = Math.max(1, Math.round(sh * scale));
  const context = canvas.getContext('2d');
  if (!context) throw new Error('无法处理图片');
  context.filter = `brightness(${adjust.brightness}%) contrast(${adjust.contrast}%)${adjust.grayscale ? ' grayscale(100%)' : ''}`;
  context.drawImage(image, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height);
  const imageData = context.getImageData(0, 0, canvas.width, canvas.height);
  context.putImageData(applySharpen(imageData, adjust.sharpen), 0, 0);
  const blob = await new Promise<Blob>((resolve, reject) => {
    canvas.toBlob(
      (next) => (next ? resolve(next) : reject(new Error('图片导出失败'))),
      'image/jpeg',
      0.9,
    );
  });
  const processed = new File(
    [blob],
    file.name.replace(/\.[^.]+$/, '') + '_scan.jpg',
    { type: 'image/jpeg' },
  );
  return { file: processed, preview: URL.createObjectURL(blob) };
}


/** Keep the whole frame, but avoid uploading multi-megabyte camera originals. */
export async function compressPhotoForUpload(
  file: File,
  maxSide = 2560,
  targetBytes = 1250 * 1024,
): Promise<File> {
  if (file.size <= targetBytes) return file;
  const image = await fileToImage(file);
  const canvas = document.createElement('canvas');
  const context = canvas.getContext('2d');
  if (!context) throw new Error('无法压缩照片，请重新选择图片');
  const encode = async (side: number, quality: number) => {
    const scale = Math.min(1, side / Math.max(image.naturalWidth, image.naturalHeight));
    canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
    canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
    context.fillStyle = '#ffffff';
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    return new Promise<Blob>((resolve, reject) => canvas.toBlob(
      next => next ? resolve(next) : reject(new Error('照片压缩失败，请重新选择图片')),
      'image/jpeg', quality,
    ));
  };
  let blob = await encode(maxSide, 0.82);
  if (blob.size > targetBytes) blob = await encode(maxSide, 0.72);
  if (blob.size > targetBytes) blob = await encode(Math.min(maxSide, 2048), 0.72);
  // Preserve small/efficient originals instead of making their upload larger.
  if (blob.size >= file.size) return file;
  return new File([blob], file.name.replace(/\.[^.]+$/, '') + '_full.jpg', { type: 'image/jpeg' });
}
