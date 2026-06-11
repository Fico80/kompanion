// Small DOM helpers keep feature modules focused on behavior.

export const qs = (selector, root = document) => root.querySelector(selector);
export const qsa = (selector, root = document) => [...root.querySelectorAll(selector)];

export function on(target, event, handler) {
    target?.addEventListener(event, handler);
}

export function setHtml(target, html) {
    if (target) target.innerHTML = html;
}

export function setVisible(target, isVisible) {
    target?.classList.toggle("hidden", !isVisible);
}
