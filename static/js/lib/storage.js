// LocalStorage helpers isolate parsing and fallback behavior.

export function readJson(key, fallback) {
    try {
        return JSON.parse(localStorage.getItem(key)) ?? fallback;
    } catch (_) {
        localStorage.removeItem(key);
        return fallback;
    }
}

export function writeJson(key, value) {
    localStorage.setItem(key, JSON.stringify(value));
}
