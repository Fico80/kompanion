# Static frontend structure

The frontend is intentionally framework-free. Keep feature behavior in small ES
modules and keep styling split by responsibility.

## Entry points

- `index.html` defines the app shell and stable mount points.
- `style.css` imports all CSS modules in the required order.
- `js/main.js` initializes the feature modules after `DOMContentLoaded`.

## CSS

- `css/foundation/` contains tokens, reset/base rules, app layout, responsive
  rules and animations.
- `css/components/` contains styles for one UI area or component family.
- Add new CSS by creating a focused module and importing it from `style.css`.

## JavaScript

- `js/api.js` contains backend calls.
- `js/templates.js` contains render-only HTML helpers.
- `js/data/` contains editable static content such as quick commands.
- `js/lib/` contains generic helpers with no product-specific behavior.
- Feature modules such as `commands.js`, `logs.js` and `tabs.js` wire behavior.
