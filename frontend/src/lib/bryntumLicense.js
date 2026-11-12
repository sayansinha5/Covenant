const key = import.meta.env.VITE_BRYNTUM_LICENSE_KEY;
if (key) {
  globalThis.bryntum ??= {};
  globalThis.bryntum.licenseKey = key;
}
