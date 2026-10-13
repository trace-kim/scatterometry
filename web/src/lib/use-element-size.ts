import { type RefObject, useEffect, useState } from "react";

/** Content-box size of an element, updated on resize. */
export function useElementSize(ref: RefObject<HTMLElement | null>): { width: number; height: number } {
  const [size, setSize] = useState({ width: 0, height: 0 });
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) =>
      setSize({ width: entry.contentRect.width, height: entry.contentRect.height }),
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref]);
  return size;
}

/** Grid placement giving a square plot area centred in a box with the given margins. */
export function squareGrid(
  size: { width: number; height: number },
  margin: { left: number; right: number; top: number; bottom: number },
) {
  const availW = Math.max(size.width - margin.left - margin.right, 10);
  const availH = Math.max(size.height - margin.top - margin.bottom, 10);
  const side = Math.min(availW, availH);
  return {
    left: margin.left + (availW - side) / 2,
    top: margin.top + (availH - side) / 2,
    width: side,
    height: side,
  };
}
