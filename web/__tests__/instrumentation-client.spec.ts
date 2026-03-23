/**
 * Tests for browser polyfills
 */

describe('at polyfill', () => {
  let originalAt: typeof Array.prototype.at

  beforeEach(() => {
    originalAt = Array.prototype.at
  })

  afterEach(() => {
    // eslint-disable-next-line no-extend-native
    Array.prototype.at = originalAt
  })

  const applyPolyfill = () => {
    // @ts-expect-error - intentionally deleting for test
    delete Array.prototype.at

    if (!Array.prototype.at) {
      // eslint-disable-next-line no-extend-native
      Array.prototype.at = function <T>(this: T[], index: number): T | undefined {
        const normalizedIndex = Math.trunc(index) || 0
        const resolvedIndex = normalizedIndex >= 0 ? normalizedIndex : this.length + normalizedIndex
        return resolvedIndex < 0 || resolvedIndex >= this.length ? undefined : this[resolvedIndex]
      }
    }
  }

  it('should add at method when not available', () => {
    applyPolyfill()
    expect(typeof Array.prototype.at).toBe('function')
  })

  it('should return the correct item for positive indices', () => {
    applyPolyfill()
    expect([1, 2, 3].at(1)).toBe(2)
  })

  it('should return the correct item for negative indices', () => {
    applyPolyfill()
    expect([1, 2, 3].at(-1)).toBe(3)
  })

  it('should return undefined for out-of-range indices', () => {
    applyPolyfill()
    expect([1, 2, 3].at(4)).toBeUndefined()
    expect([1, 2, 3].at(-4)).toBeUndefined()
  })
})

describe('toSpliced polyfill', () => {
  let originalToSpliced: typeof Array.prototype.toSpliced

  beforeEach(() => {
    // Save original method
    originalToSpliced = Array.prototype.toSpliced
  })

  afterEach(() => {
    // Restore original method
    // eslint-disable-next-line no-extend-native
    Array.prototype.toSpliced = originalToSpliced
  })

  const applyPolyfill = () => {
    // @ts-expect-error - intentionally deleting for test
    delete Array.prototype.toSpliced

    if (!Array.prototype.toSpliced) {
      // eslint-disable-next-line no-extend-native
      Array.prototype.toSpliced = function <T>(this: T[], start: number, deleteCount?: number, ...items: T[]): T[] {
        const copy = this.slice()
        copy.splice(start, deleteCount ?? copy.length - start, ...items)
        return copy
      }
    }
  }

  it('should add toSpliced method when not available', () => {
    applyPolyfill()
    expect(typeof Array.prototype.toSpliced).toBe('function')
  })

  it('should return a new array without modifying the original', () => {
    applyPolyfill()
    const arr = [1, 2, 3, 4, 5]
    const result = arr.toSpliced(1, 2)

    expect(result).toEqual([1, 4, 5])
    expect(arr).toEqual([1, 2, 3, 4, 5]) // original unchanged
  })

  it('should insert items at the specified position', () => {
    applyPolyfill()
    const arr: (number | string)[] = [1, 2, 3]
    const result = arr.toSpliced(1, 0, 'a', 'b')

    expect(result).toEqual([1, 'a', 'b', 2, 3])
  })

  it('should replace items at the specified position', () => {
    applyPolyfill()
    const arr: (number | string)[] = [1, 2, 3, 4, 5]
    const result = arr.toSpliced(1, 2, 'a', 'b')

    expect(result).toEqual([1, 'a', 'b', 4, 5])
  })

  it('should handle negative start index', () => {
    applyPolyfill()
    const arr = [1, 2, 3, 4, 5]
    const result = arr.toSpliced(-2, 1)

    expect(result).toEqual([1, 2, 3, 5])
  })

  it('should delete to end when deleteCount is omitted', () => {
    applyPolyfill()
    const arr = [1, 2, 3, 4, 5]
    const result = arr.toSpliced(2)

    expect(result).toEqual([1, 2])
  })
})
