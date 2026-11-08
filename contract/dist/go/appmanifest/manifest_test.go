package appmanifest

import (
	"os"
	"path/filepath"
	"testing"
)

// The official apps are valid; each broken manifest is refused with its code and a fix.
func TestOfficialAppsAreValid(t *testing.T) {
	files, _ := filepath.Glob("testdata/*.json")
	if len(files) == 0 {
		t.Fatal("no testdata")
	}
	for _, file := range files {
		raw, _ := os.ReadFile(file)
		if problems := Validate(raw); len(problems) != 0 {
			t.Errorf("%s: %+v", file, problems)
		}
	}
}

func TestRefusalsCarryCodeParamAndFix(t *testing.T) {
	base := `"$schema": "https://0x1audio.com/schema/app/v1.json", "displayName": "My App", "version": "0.1.0", "sdk": "^0.3", "entry": "app.py"`
	cases := map[string]struct{ json, code, param string }{
		"v0":     {`{"displayName": "Old", "version": "0.1.0"}`, "manifest_v0", "$schema"},
		"name":   {`{` + base + `, "name": "My App"}`, "manifest_name", "name"},
		"field":  {`{` + base + `, "name": "my-app", "worker": {}}`, "manifest_field", "worker"},
		"reason": {`{` + base + `, "name": "my-app", "permissions": {"files": "short"}}`, "permission_reason", "permissions.files"},
		"web":    {`{` + base + `, "name": "my-app", "permissions": {"network": {"why": "Download the model once.", "hosts": ["127.0.0.1"]}}}`, "network_hosts", "permissions.network.hosts"},
		"window": {`{` + base + `, "name": "my-app", "window": {"width": 90}}`, "manifest_window", "window.width"},
		"escape": {`{"$schema": "https://0x1audio.com/schema/app/v1.json", "name": "my-app", "displayName": "My App", "version": "0.1.0", "sdk": "^0.3", "entry": "../x.py"}`, "manifest_entry", "entry"},
		"no sdk": {`{"$schema": "https://0x1audio.com/schema/app/v1.json", "name": "my-app", "displayName": "My App", "version": "0.1.0", "entry": "app.py"}`, "sdk_missing", "sdk"},
	}
	for name, c := range cases {
		problems := Validate([]byte(c.json))
		if len(problems) == 0 || problems[0].Code != c.code || problems[0].Param != c.param || problems[0].Fix == "" {
			t.Errorf("%s: got %+v, want %s at %s with a fix", name, problems, c.code, c.param)
		}
	}
}
