import "@testing-library/jest-dom/vitest";

// jsdom doesn't ship ResizeObserver / matchMedia / scrollIntoView; Radix UI
// components need them. Provide minimal mocks here so component tests don't
// crash on layout-effect APIs.
class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver =
  globalThis.ResizeObserver ?? (ResizeObserverMock as unknown as typeof ResizeObserver);

if (typeof window !== "undefined") {
  if (!window.matchMedia) {
    window.matchMedia = (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    });
  }
  // @ts-expect-error: not in jsdom; Radix uses it on focus.
  window.HTMLElement.prototype.scrollIntoView =
    window.HTMLElement.prototype.scrollIntoView ?? (() => {});
  // @ts-expect-error: not in jsdom; Radix Select uses it.
  window.HTMLElement.prototype.hasPointerCapture =
    window.HTMLElement.prototype.hasPointerCapture ?? (() => false);
  // @ts-expect-error: not in jsdom; Radix Select uses it.
  window.HTMLElement.prototype.releasePointerCapture =
    window.HTMLElement.prototype.releasePointerCapture ?? (() => {});
}
