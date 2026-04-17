// Global setup that runs before any test files
export default function () {
  // Mock localStorage before any modules access it
  const localStorageMock = {
    getItem: () => null,
    setItem: () => {},
    removeItem: () => {},
    clear: () => {},
    length: 0,
    key: () => null,
  };
  
  Object.defineProperty(global, 'localStorage', {
    value: localStorageMock,
    writable: true,
  });
}
