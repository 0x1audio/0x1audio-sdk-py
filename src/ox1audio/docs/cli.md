# The mixel command

Install or update it with `uv tool install ox1audio`. It runs on macOS, Linux and Windows.

## Start

| Command | Does | Options |
| --- | --- | --- |
| `mixel new "My App"` | start an app in ./my-app |  |
| `mixel dev` | open this app in Mixel, reload it on save |  |

## Check

| Command | Does | Options |
| --- | --- | --- |
| `mixel check` | the rules Mixel and its reviewers apply | `--fix --strict --json` |
| `mixel test` | run the tests in tests/ | `-k NAME --json` |
| `mixel run ACTION` | run one action here | `--file PATH --set NAME=VALUE --out FOLDER --json` |

## Publish

| Command | Does | Options |
| --- | --- | --- |
| `mixel login` | sign in with your Mixel account |  |
| `mixel publish` | send this version for review | `--dry-run --json` |
| `mixel status` | review state and reviewer notes | `--json` |

## More

| Command | Does | Options |
| --- | --- | --- |
| `mixel docs [TOPIC]` | the docs, offline | `--list` |
| `mixel doctor` | is this computer ready | `--json` |
| `mixel mcp` | the MCP server for coding agents (stdio) |  |

Exit codes: 0 ok, 1 a check or test failed, 2 usage, 3 sign-in, 4 network or registry. `--json` prints one JSON object for tools.
