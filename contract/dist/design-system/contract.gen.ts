// Generated from sdk-py/contract by contract/generate.py. Do not edit.
// The action, error and Library item shapes that sdk-py (_protocol.py), the desktop host
// (electron/apps/protocol.ts) and the page SDK (@0x1audio/sdk/page) share. Design system copy: ActionForm's types.

export const protocolVersion = 1
export const manifestSchema = "https://0x1audio.com/schema/app/v1.json"

export type ErrorCode = "bad_input" | "problem" | "cancelled" | "crashed" | "timeout" | "permission_denied" | "permission_undeclared" | "unavailable"
export const errorCodes: readonly ErrorCode[] = ["bad_input", "problem", "cancelled", "crashed", "timeout", "permission_denied", "permission_undeclared", "unavailable"]

export type PermissionCode = "files" | "library" | "library-read" | "data" | "gpu" | "network"
export const permissionCodes: readonly PermissionCode[] = ["files", "library", "library-read", "data", "gpu", "network"]
export const permissionText: Record<PermissionCode, string> = {"files": "Read and write files you pick", "library": "Add to your Library", "library-read": "Read your Library", "data": "Keep its own files", "gpu": "Use the graphics chip", "network": "Use the network"}

export type Control = "files" | "folder" | "choice" | "text" | "number" | "slider" | "toggle"

// The "x-ox" hint on each input property: how Mixel draws the control.
export interface ControlHint {
  control: Control
  accept?: "audio" | "midi" | "any"
  multiple?: boolean
  label?: string
  placeholder?: string
  step?: number
  // Shown after the value, like "dB", "Hz" or "%".
  unit?: string
  // A slider's "no change" value when it isn't the minimum (0 on a -12…12 slider):
  // the track fills from here to the value, with a mark at the origin.
  origin?: number
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
  maxItems?: number
  // Files and choices are strings; a range (control "slider", 2 items) is numbers.
  items?: { type: "string" | "number" | "integer"; enum?: string[]; minimum?: number; maximum?: number }
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
