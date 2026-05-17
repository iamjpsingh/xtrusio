import "@testing-library/jest-dom/vitest";

// jsdom doesn't ship ResizeObserver / matchMedia / scrollIntoView / scrollTo;
// Radix UI and TanStack Router need them. Provide minimal mocks here so
// component tests don't crash on layout-effect APIs.
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
  // jsdom's window.scrollTo is present-but-throwing (not absent like the
  // stubs above), so it must be overwritten unconditionally — TanStack
  // Router calls scrollTo on every navigation in the real-router tests.
  window.scrollTo = () => {};
  window.HTMLElement.prototype.scrollIntoView =
    window.HTMLElement.prototype.scrollIntoView ?? (() => {});
  window.HTMLElement.prototype.hasPointerCapture =
    window.HTMLElement.prototype.hasPointerCapture ?? (() => false);
  window.HTMLElement.prototype.releasePointerCapture =
    window.HTMLElement.prototype.releasePointerCapture ?? (() => {});
}
