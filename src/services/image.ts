export interface Point { x: number; y: number; }
export interface Quad { topLeft: Point; topRight: Point; bottomLeft: Point; bottomRight: Point; }

export interface QualityMetrics {
  blur: number;
  brightness: number;
  contrast: number;
  isStable: boolean;
}

export const imageService = {
  /**
   * Warps a source image to a destination quadrilateral using triangle slicing.
   */
  async warp(source: HTMLCanvasElement, quad: Quad, width: number, height: number): Promise<string> {
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d')!;

    const steps = 20;
    for (let y = 0; y < steps; y++) {
      for (let x = 0; x < steps; x++) {
        const p1 = this.getPointAt(quad, x / steps, y / steps);
        const p2 = this.getPointAt(quad, (x + 1) / steps, y / steps);
        const p3 = this.getPointAt(quad, x / steps, (y + 1) / steps);
        const p4 = this.getPointAt(quad, (x + 1) / steps, (y + 1) / steps);

        const u1 = (x / steps) * source.width;
        const v1 = (y / steps) * source.height;
        const u2 = ((x + 1) / steps) * source.width;
        const v2 = ((y + 1) / steps) * source.height;

        this.drawTriangle(ctx, source, p1, p2, p3, u1, v1, u2, v1, u1, v2);
        this.drawTriangle(ctx, source, p2, p4, p3, u2, v1, u2, v2, u1, v2);
      }
    }

    return canvas.toDataURL('image/jpeg', 0.9);
  },

  getPointAt(quad: Quad, u: number, v: number): Point {
    const topX = quad.topLeft.x + (quad.topRight.x - quad.topLeft.x) * u;
    const topY = quad.topLeft.y + (quad.topRight.y - quad.topLeft.y) * u;
    const botX = quad.bottomLeft.x + (quad.bottomRight.x - quad.bottomLeft.x) * u;
    const botY = quad.bottomLeft.y + (quad.bottomRight.y - quad.bottomLeft.y) * u;

    return {
      x: topX + (botX - topX) * v,
      y: topY + (botY - topY) * v
    };
  },

  drawTriangle(ctx: CanvasRenderingContext2D, img: any, p0: Point, p1: Point, p2: Point, u0: number, v0: number, u1: number, v1: number, u2: number, v2: number) {
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(p0.x, p0.y);
    ctx.lineTo(p1.x, p1.y);
    ctx.lineTo(p2.x, p2.y);
    ctx.closePath();
    ctx.clip();

    const det = (u1 - u0) * (v2 - v0) - (u2 - u0) * (v1 - v0);
    if (det !== 0) {
      const idet = 1 / det;
      const a = ((p1.x - p0.x) * (v2 - v0) - (p2.x - p0.x) * (v1 - v0)) * idet;
      const b = ((p2.x - p0.x) * (u1 - u0) - (p1.x - p0.x) * (u2 - u0)) * idet; 
      const c = p0.x - a * u0 - b * v0;
      const d = ((p1.y - p0.y) * (v2 - v0) - (p2.y - p0.y) * (v1 - v0)) * idet;
      const e = ((p2.y - p0.y) * (u1 - u0) - (p1.y - p0.y) * (u2 - u0)) * idet;
      const f = p0.y - d * u0 - e * v0;

      ctx.setTransform(a, d, b, e, c, f);
      ctx.drawImage(img, 0, 0);
    }
    ctx.restore();
  },

  analyzeQuality(canvas: HTMLCanvasElement): QualityMetrics {
    const ctx = canvas.getContext('2d')!;
    const w = canvas.width;
    const h = canvas.height;
    const imageData = ctx.getImageData(0, 0, w, h);
    const data = imageData.data;
    
    let totalBrightness = 0;
    let laplacianVar = 0;
    const step = 8; 
    let count = 0;
    
    for (let y = step; y < h - step; y += step) {
      for (let x = step; x < w - step; x += step) {
        const idx = (y * w + x) * 4;
        const gray = (data[idx] + data[idx+1] + data[idx+2]) / 3;
        totalBrightness += gray;
        
        const left = (data[idx - 4]) || gray;
        const right = (data[idx + 4]) || gray;
        const up = (data[idx - w*4]) || gray;
        const down = (data[idx + w*4]) || gray;

        laplacianVar += Math.abs(4 * gray - left - right - up - down);
        count++;
      }
    }

    const brightness = totalBrightness / count;
    const blurScore = laplacianVar / count;

    return {
      brightness: Math.round(brightness),
      blur: Math.round(blurScore),
      contrast: 0,
      isStable: blurScore > 1.5 && brightness > 50 && brightness < 220
    };
  },

  /**
   * Enhances an image specifically for OCR throughput.
   */
  async normalizeForOCR(canvas: HTMLCanvasElement): Promise<string> {
    const ctx = canvas.getContext('2d', { willReadFrequently: true })!;
    const { width, height } = canvas;
    const imageData = ctx.getImageData(0, 0, width, height);
    const data = imageData.data;

    let min = 255;
    let max = 0;
    for (let i = 0; i < data.length; i += 4) {
      const avg = (data[i] + data[i + 1] + data[i + 2]) / 3;
      if (avg < min) min = avg;
      if (avg > max) max = avg;
    }

    const range = max - min || 1;
    for (let i = 0; i < data.length; i += 4) {
      for (let j = 0; j < 3; j++) {
        let val = ((data[i + j] - min) / range) * 255;
        val = 127 + 1.2 * (val - 127); // Contrast boost
        data[i + j] = Math.max(0, Math.min(255, val));
      }
    }

    ctx.putImageData(imageData, 0, 0);
    return canvas.toDataURL('image/jpeg', 0.9);
  }
};
