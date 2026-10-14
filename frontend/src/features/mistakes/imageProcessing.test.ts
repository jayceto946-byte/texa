import { describe, expect, it } from 'vitest';

import { applySharpen, clamp } from './imageProcessing';

describe('mistake image processing', () => {
  it('clamps values to the supplied range', () => {
    expect(clamp(-1, 0, 255)).toBe(0);
    expect(clamp(300, 0, 255)).toBe(255);
    expect(clamp(42, 0, 255)).toBe(42);
  });

  it('does not mutate pixels when sharpening is disabled', () => {
    const data = new Uint8ClampedArray(3 * 3 * 4).fill(80);
    const imageData = { data, width: 3, height: 3 } as ImageData;
    const before = Array.from(data);

    expect(applySharpen(imageData, 0)).toBe(imageData);
    expect(Array.from(data)).toEqual(before);
  });

  it('applies the same five-point kernel used by the capture workflow', () => {
    const data = new Uint8ClampedArray(3 * 3 * 4);
    for (let pixel = 0; pixel < 9; pixel += 1) {
      data[pixel * 4 + 3] = 255;
    }
    const center = (1 * 3 + 1) * 4;
    data[center] = 100;
    data[center + 1] = 100;
    data[center + 2] = 100;
    const imageData = { data, width: 3, height: 3 } as ImageData;

    applySharpen(imageData, 50);

    expect(Array.from(data.slice(center, center + 4))).toEqual([255, 255, 255, 255]);
  });
});

import { imageUploadError } from './imageProcessing';

describe('photo upload guidance', () => {
  it('accepts Android JPEG filenames even when MIME is omitted', () => {
    expect(imageUploadError({ name: 'IMG_001.JPG', size: 1000 })).toBe('');
  });
  it('gives an actionable HEIC conversion message and rejects invalid uploads', () => {
    expect(imageUploadError({ name: 'photo.heic', size: 1000 })).toContain('JPEG');
    expect(imageUploadError({ name: 'question.pdf', size: 1000 })).not.toBe('');
    expect(imageUploadError({ name: 'photo.jpg', size: 0 })).toContain('为空');
    expect(imageUploadError({ name: 'photo.jpg', size: 21 * 1024 * 1024 })).toContain('20MB');
  });
});

import { vi } from 'vitest';
import { compressPhotoForUpload } from './imageProcessing';

it('compresses the whole camera frame, bounds dimensions, and retains efficient files', async () => {
  const drawImage = vi.fn();
  const context = { fillStyle: '', fillRect: vi.fn(), drawImage };
  const qualities: number[] = [];
  const canvas = { width: 0, height: 0, getContext: () => context, toBlob: (callback: (blob: Blob) => void, _type: string, quality: number) => {
    qualities.push(quality);
    callback(new Blob([new Uint8Array(qualities.length === 1 ? 1500 * 1024 : 900 * 1024)], { type: 'image/jpeg' }));
  } };
  class CameraImage {
    naturalWidth = 4000; naturalHeight = 3000; decoding = '';
    onload: null | (() => void) = null;
    set src(_value: string) { queueMicrotask(() => this.onload?.()); }
  }
  vi.stubGlobal('Image', CameraImage);
  vi.stubGlobal('document', { createElement: () => canvas });
  try {
    const efficient = new File(['small'], 'small.jpg', { type: 'image/jpeg' });
    expect(await compressPhotoForUpload(efficient)).toBe(efficient);
    const camera = new File([new Uint8Array(5 * 1024 * 1024)], 'camera.JPG', { type: 'image/jpeg' });
    const result = await compressPhotoForUpload(camera);
    expect(result.size).toBe(900 * 1024);
    expect(result.name).toBe('camera_full.jpg');
    expect(result.type).toBe('image/jpeg');
    expect([canvas.width, canvas.height]).toEqual([2560, 1920]);
    expect(qualities).toEqual([0.82, 0.72]);
    expect(drawImage).toHaveBeenCalledWith(expect.any(CameraImage), 0, 0, 2560, 1920);
  } finally { vi.unstubAllGlobals(); }
});
