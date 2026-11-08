// Code generated from sdk-py/contract by contract/generate.py. DO NOT EDIT.

// Package appmanifest checks app.json v1 with the same rules as mixel check and the desktop.
// It covers what can be checked from app.json alone; file checks (entry exists, icon is
// square) and code checks (permissions used) stay with mixel check, which the registry runs.
package appmanifest

import (
	"encoding/json"
	"fmt"
	"net"
	"regexp"
	"strings"
)

const Schema = "https://0x1audio.com/schema/app/v1.json"
const DocsURL = "https://docs.0x1audio.com/errors#"

var Fields = []string{"$schema", "name", "displayName", "summary", "version", "sdk", "entry", "page", "permissions", "accent", "icon", "window", "tags"}
var PermissionCodes = []string{"files", "library", "data", "network"}

var (
	namePattern    = regexp.MustCompile(`^[a-z][a-z0-9]*(-[a-z0-9]+)*$`)
	versionPattern = regexp.MustCompile(`^(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})$`)
	sdkPattern     = regexp.MustCompile(`^\^(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})(\.(0|[1-9][0-9]{0,3}))?$`)
	accentPattern  = regexp.MustCompile(`^#[0-9a-fA-F]{6}$`)
	hostPattern    = regexp.MustCompile(`^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$`)
)

const (
	nameMin, nameMax     = 2, 48
	displayNameMax       = 48
	summaryMax           = 80
	reasonMin, reasonMax = 12, 120
	hostsMax             = 16
	hostMax              = 253
	tagsMax              = 5
)

var windowBounds = map[string][2]int{"width": {400, 2560}, "height": {320, 1600}, "minWidth": {400, 2560}, "minHeight": {320, 1600}}

// fixes is each code's usual fix, from contract/errors.json.
var fixes = map[string]string{"manifest_missing": "mixel new \"My App\" starts one.", "manifest_json": "Fix the JSON at the line shown.", "manifest_v0": "Add \"$schema\" and \"sdk\", rename worker.entry to entry and frontend to page, give each permission a reason.", "manifest_schema": "\"$schema\": \"https://0x1audio.com/schema/app/v1.json\"", "manifest_field": "Remove or rename it as the message says.", "manifest_name": "\"name\": \"my-app\". It never changes after the first publish.", "manifest_display_name": "\"displayName\": \"My App\"", "manifest_summary": "\"summary\": \"One file to many formats at once.\"", "manifest_version": "\"version\": \"0.1.0\", raised before each publish.", "manifest_entry": "\"entry\": \"app.py\"", "manifest_page": "npm run build, then \"page\": \"dist/index.html\"", "manifest_accent": "\"accent\": \"#5b8cff\"", "manifest_icon": "\"icon\": \"icon.svg\"", "manifest_window": "\"window\": { \"width\": 900, \"height\": 640 }", "manifest_tags": "\"tags\": [\"convert\"]", "sdk_missing": "\"sdk\": \"^0.3\"", "sdk_range": "\"sdk\": \"^0.3\"", "permission_unused": "Remove it, so people aren't asked for more than the app needs.", "permission_unknown": "Use one of files, library, data, network.", "permission_reason": "One sentence that tells the person why, like \"Open the songs you choose.\"", "network_hosts": "\"network\": { \"why\": \"Download the model once.\", \"hosts\": [\"github.com\"] }", "dependency_missing": "Add it to pyproject.toml › [project].dependencies.", "dependency_not_installed": "uv venv && uv pip install -r pyproject.toml", "banned_api": "Use ox.audio.convert, ox.audio.read or ox.audio.write instead of programs; urllib.request with a declared network for downloads; plain imports.", "path_outside": "Use the files the person chooses (ox.Files, ox.Folder), ox.temp() or ox.data.", "app_failed_to_load": "Fix the error at the line shown; the message names the fix.", "no_actions": "@ox.action(\"Title\") above a function makes it an action."}

// Problem is one refusal, in the registry's error shape: {code, message, param, doc_url, fix}.
type Problem struct {
	Code    string `json:"code"`
	Message string `json:"message"`
	Param   string `json:"param,omitempty"`
	Fix     string `json:"fix,omitempty"`
	DocURL  string `json:"doc_url"`
}

func problem(code, param, message string) Problem {
	return Problem{Code: code, Message: message, Param: param, Fix: fixes[code], DocURL: DocsURL + code}
}

// Validate returns every problem with an app.json, or nil when it is a valid v1 manifest.
func Validate(raw []byte) []Problem {
	var data map[string]any
	if err := json.Unmarshal(raw, &data); err != nil || data == nil {
		return []Problem{problem("manifest_json", "", "app.json is not a JSON object.")}
	}
	var found []Problem
	add := func(code, param, message string) { found = append(found, problem(code, param, message)) }
	schema, ok := data["$schema"]
	if !ok {
		return []Problem{problem("manifest_v0", "$schema", "app.json has no \"$schema\": it is the old v0 format.")}
	}
	if schema != Schema {
		add("manifest_schema", "$schema", fmt.Sprintf("$schema is %v, which isn't the v1 URL.", schema))
	}
	known := map[string]bool{}
	for _, field := range Fields {
		known[field] = true
	}
	for key := range data {
		if !known[key] {
			add("manifest_field", key, key+" is not a field.")
		}
	}
	if name, ok := data["name"].(string); !ok || len(name) < nameMin || len(name) > nameMax || !namePattern.MatchString(name) {
		add("manifest_name", "name", fmt.Sprintf("name is %d to %d lowercase letters, digits and dashes.", nameMin, nameMax))
	}
	if display, ok := data["displayName"].(string); !ok || strings.TrimSpace(display) == "" || len([]rune(display)) > displayNameMax {
		add("manifest_display_name", "displayName", fmt.Sprintf("displayName is the name people see, up to %d characters.", displayNameMax))
	}
	if value, present := data["summary"]; present {
		if summary, ok := value.(string); !ok || strings.TrimSpace(summary) == "" || len([]rune(summary)) > summaryMax {
			add("manifest_summary", "summary", fmt.Sprintf("summary is one sentence, up to %d characters.", summaryMax))
		}
	}
	if version, ok := data["version"].(string); !ok || !versionPattern.MatchString(version) {
		add("manifest_version", "version", "version is MAJOR.MINOR.PATCH.")
	}
	if value, present := data["sdk"]; !present {
		add("sdk_missing", "sdk", "sdk is required: it says which Mixel can run this app.")
	} else if sdk, ok := value.(string); !ok || !sdkPattern.MatchString(sdk) {
		add("sdk_range", "sdk", "sdk is a caret range like ^0.3.")
	}
	_, hasEntry := data["entry"]
	_, hasPage := data["page"]
	if !hasEntry && !hasPage {
		add("manifest_entry", "entry", "The app needs an entry (its Python file) or a page.")
	}
	if hasEntry && !relativeFile(data["entry"], ".py") {
		add("manifest_entry", "entry", "entry is a .py file inside the app.")
	}
	if hasPage && !relativeFile(data["page"], ".html") {
		add("manifest_page", "page", "page is an .html file inside the app.")
	}
	if value, present := data["permissions"]; present {
		permissions, ok := value.(map[string]any)
		if !ok {
			add("permission_reason", "permissions", "permissions is an object of code to reason.")
		}
		for code, reason := range permissions {
			param := "permissions." + code
			if !contains(PermissionCodes, code) {
				add("permission_unknown", param, code+" is not a permission.")
				continue
			}
			if code == "network" {
				network, ok := reason.(map[string]any)
				if !ok {
					add("network_hosts", param, "network says why, and which hosts.")
					continue
				}
				hosts, _ := network["hosts"].([]any)
				if len(hosts) == 0 || len(hosts) > hostsMax || !allHosts(hosts) {
					add("network_hosts", param+".hosts", "hosts lists the domains the app reaches. The whole web, IPs and localhost are refused.")
				}
				reason, param = network["why"], param+".why"
			}
			text, ok := reason.(string)
			if !ok || len([]rune(strings.TrimSpace(text))) < reasonMin || len([]rune(text)) > reasonMax {
				add("permission_reason", param, fmt.Sprintf("Each permission has a reason the person reads: one sentence, %d to %d characters.", reasonMin, reasonMax))
			}
		}
	}
	if value, present := data["accent"]; present {
		if accent, ok := value.(string); !ok || !accentPattern.MatchString(accent) {
			add("manifest_accent", "accent", "accent is a colour like #5b8cff.")
		}
	}
	if value, present := data["icon"]; present {
		icon, ok := value.(string)
		lower := strings.ToLower(icon)
		if !ok || !(strings.HasSuffix(lower, ".svg") || strings.HasSuffix(lower, ".png")) || !relativeFile(icon, "") {
			add("manifest_icon", "icon", "icon is a square .svg or .png inside the app.")
		}
	}
	if value, present := data["window"]; present {
		window, ok := value.(map[string]any)
		if !ok || len(window) == 0 {
			add("manifest_window", "window", "window is an object of sizes in pixels.")
		}
		for key, size := range window {
			bounds, known := windowBounds[key]
			number, isNumber := size.(float64)
			if !known || !isNumber || number != float64(int(number)) || int(number) < bounds[0] || int(number) > bounds[1] {
				add("manifest_window", "window."+key, "window sizes are whole pixels within the allowed range.")
			}
		}
	}
	if value, present := data["tags"]; present {
		tags, ok := value.([]any)
		if !ok || len(tags) > tagsMax || !allWords(tags) {
			add("manifest_tags", "tags", fmt.Sprintf("tags is up to %d single words.", tagsMax))
		}
	}
	return found
}

func relativeFile(value any, suffix string) bool {
	path, ok := value.(string)
	if !ok || path == "" || len(path) > 200 || strings.HasPrefix(path, "/") || strings.Contains(path, "\\") || !strings.HasSuffix(path, suffix) {
		return false
	}
	for _, part := range strings.Split(path, "/") {
		if part == ".." {
			return false
		}
	}
	return true
}

func allHosts(hosts []any) bool {
	for _, value := range hosts {
		host, ok := value.(string)
		if !ok || len(host) > hostMax || host == "localhost" || net.ParseIP(host) != nil || !hostPattern.MatchString(host) {
			return false
		}
	}
	return true
}

func allWords(tags []any) bool {
	for _, value := range tags {
		tag, ok := value.(string)
		if !ok || tag == "" || len(tag) > 64 || strings.ContainsAny(tag, " \t\n") {
			return false
		}
	}
	return true
}

func contains(list []string, value string) bool {
	for _, item := range list {
		if item == value {
			return true
		}
	}
	return false
}
