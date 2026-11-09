# Protocol

Protocol 1 between the desktop and an app's Python worker: NDJSON on stdin and stdout, one object per line, at most 1 MiB. Host call ids (id) and worker request ids (rid) are separate spaces. Generates docs/protocol.md and the TypeScript message types.

## Worker to Mixel

| type | Fields | Notes |
| --- | --- | --- |
| `ready` | `{protocol, sdk, actions: [ActionSpec], permissions: [code]}` | First line. The host refuses the worker if it uses a permission app.json doesn't declare. |
| `fatal` | `{error: Error}` | The app could not load. The worker exits. |
| `progress` | `{id, fraction: number | null, label}` | From ox.progress. Coalesced to 20 a second. |
| `event` | `{id, name, body}` | From ox.emit. The host forwards it to the page that made call id. |
| `result` | `{id, body}` | What the action returned, as JSON. Exports become {items: [Item]}. |
| `error` | `{id, error: Error}` | Codes: bad_input, problem, cancelled (with kept), crashed. |
| `library` | `{rid, op: "add", kind, path, title, metadata}` | Add a file to the Library. Answered by library-result. |
| `cloud` | `{rid, method, path, body}` | An allow-listed cloud call. The token never reaches the worker. |

## Mixel to worker

| type | Fields | Notes |
| --- | --- | --- |
| `call` | `{id, action, input, handed?: [path]}` | Run an action. The host has already checked input against its schema. handed lists the input files the person gave with Open with: the app may read them, not write next to them (ox.beside is None). |
| `cancel` | `{id}` | Stop: the action's next ox.progress raises ox.Cancelled. |
| `library-result` | `{rid, status, body}` | The answer to a library request. |
| `cloud-result` | `{rid, status, body}` | The answer to a cloud request. |
| `shutdown` | `{}` | Finish, then exit. The host kills the worker after 3 s. |

## Types

- `ActionSpec` = `{name, title, input: JSON Schema object whose properties carry "x-ox": {control, accept?, multiple?, label?, placeholder?, step?, unit?, origin?}, timeout: seconds}. A slider on an array of 2 numbers is a range: [start, end]. origin is a slider's no-change value when it isn't the minimum: the track fills from it.`
- `Error` = `{code, message, hint?, detail?, kept?: [Item]}`
- `Item` = `{id, kind: sound | midi | other, title, path}`

Limits: a line or a result is at most 1 MiB, an event body 256 KiB; progress is coalesced to 20 a second.
