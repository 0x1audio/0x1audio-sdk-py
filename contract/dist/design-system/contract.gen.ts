// Generated from sdk-py/contract by contract/generate.py. Do not edit.
// The action, error and Library item shapes that sdk-py (_protocol.py), the desktop host
// (electron/apps/protocol.ts) and the page SDK (@0x1audio/sdk/page) share. Design system copy: ActionForm's types.

export const protocolVersion = 1
export const manifestSchema = "https://0x1audio.com/schema/app/v1.json"

export type ErrorCode = "bad_input" | "problem" | "cancelled" | "crashed" | "timeout" | "permission_denied" | "permission_undeclared" | "unavailable"
export const errorCodes: readonly ErrorCode[] = ["bad_input", "problem", "cancelled", "crashed", "timeout", "permission_denied", "permission_undeclared", "unavailable"]

export type PermissionCode = "files" | "library" | "data" | "network"
export const permissionCodes: readonly PermissionCode[] = ["files", "library", "data", "network"]
export const permissionText: Record<PermissionCode, string> = {"files": "Read and write files you pick", "library": "Add to your Library", "data": "Keep its own files", "network": "Use the network"}

export type Control = "files" | "folder" | "choice" | "text" | "number" | "slider" | "toggle"

// The "x-ox" hint on each input property: how Mixel draws the control.
export interface ControlHint {
  control: Control
  accept?: "audio" | "midi" | "any"
  multiple?: boolean
  label?: string
  placeholder?: string
  step?: number
}

export interface PropertySchema {
  type?: "string" | "number" | "integer" | "boolean" | "array"
  title?: string
  default?: unknown
  enum?: string[]
  minimum?: number
  maximum?: number
  minLength?: number
  maxLength?: number
  minItems?: number
  items?: { type: "string"; enum?: string[] }
  uniqueItems?: boolean
  anyOf?: PropertySchema[]
  "x-ox"?: ControlHint
}

export interface InputSchema {
  type: "object"
  properties: Record<string, PropertySchema>
  required: string[]
  additionalProperties: false
}

// One @ox.action, as the worker declares it in its ready line.
export interface ActionSpec {
  name: string
  title: string
  input: InputSchema
  timeout: number
}

// A Library item an action made (results, and what Stop kept).
export interface Item {
  id?: string
  kind?: string
  title?: string
  path?: string
}

export interface ErrorBody {
  code: ErrorCode
  message: string
  hint?: string
  detail?: string
  // On "cancelled": what the action finished before Stop. Already in the Library.
  kept?: Item[]
}
