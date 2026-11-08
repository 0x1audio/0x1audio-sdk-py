# app.json

Every app has an `app.json` at the top of its folder. `$schema` is `https://0x1audio.com/schema/app/v1.json`; editors use it for autocomplete. Unknown fields are errors. `mixel check` applies these rules, and so do Mixel and the registry.

| Field | | Rule |
| --- | --- | --- |
| `$schema` | required | Always this URL. It says the file is app.json v1. |
| `name` | required | The app's id: lowercase letters, digits and dashes. Never changes. |
| `displayName` | required | The name people see. |
| `summary` | optional | One sentence about what the app does, for the catalog. |
| `version` | required | MAJOR.MINOR.PATCH. Raise it before each release. |
| `sdk` | required | The Mixel versions the app runs on, as a caret range like ^0.3. |
| `entry` | entry or page | The Python file with the app's @ox.action functions. |
| `page` | entry or page | An optional page, built by Vite. |
| `permissions` | optional | What the app may use, each with the reason the person reads. Binding: anything else is refused. |
| `accent` | optional | The app's colour, like #5b8cff. |
| `icon` | optional | A square .svg or .png inside the app. |
| `window` | optional | The size the app's window opens at, in pixels. |
| `tags` | optional | Up to 5 words for the catalog, like "convert". |
| `license` | optional | The app's licence, an SPDX identifier like "Apache-2.0". mixel new writes Apache-2.0; change it if you choose another. |

Window sizes in pixels: `width` 400–2560, `height` 320–1600, `minWidth` 400–2560, `minHeight` 320–1600. Reasons are 12 to 120 characters.
