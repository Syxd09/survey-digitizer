/**
 * Tiered Buffer Management Service
 * Optimized for mobile browser memory constraints.
 */

const TIERS = {
  MP2:  { w: 1920, h: 1080, size: 1920 * 1080 },
  MP5:  { w: 2560, h: 1920, size: 2560 * 1920 },
  MP12: { w: 4032, h: 3024, size: 4032 * 3024 },
};

class BufferManager {
  private grayscaleBuffer: Uint8Array | null = null;
  private integralBuffer: Uint32Array | null = null;
  private currentCapacity = 0;

  /**
   * Gets or allocates a buffer set fitting the required pixel count.
   * Uses tiered allocation to minimize reallocations.
   */
  prepareBuffers(pixelCount: number) {
    let target = TIERS.MP2;
    if (pixelCount > TIERS.MP5.size) target = TIERS.MP12;
    else if (pixelCount > TIERS.MP2.size) target = TIERS.MP5;

    if (this.grayscaleBuffer && this.currentCapacity >= target.size) {
      return { grayscale: this.grayscaleBuffer, integral: this.integralBuffer! };
    }

    console.log(`BufferManager: Allocating ${target.size} pixels tier...`);
    this.grayscaleBuffer = new Uint8Array(target.size);
    this.integralBuffer = new Uint32Array(target.size);
    this.currentCapacity = target.size;

    return { grayscale: this.grayscaleBuffer, integral: this.integralBuffer };
  }

  /**
   * Resets buffers if needed (e.g., between different survey batches).
   */
  clear() {
    this.grayscaleBuffer = null;
    this.integralBuffer = null;
    this.currentCapacity = 0;
  }
}

export const bufferManager = new BufferManager();
