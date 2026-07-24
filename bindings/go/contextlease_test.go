package contextlease

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

type runtimeFixture struct {
	Cases []struct {
		Name       string          `json:"name"`
		Definition json.RawMessage `json:"definition"`
		Request    json.RawMessage `json:"request"`
		Assert     struct {
			MaxPromptTokens int      `json:"max_prompt_tokens"`
			MustContain     []string `json:"must_contain"`
			LeaseBorrower   string   `json:"lease_borrower"`
		} `json:"assert"`
	} `json:"cases"`
}

func TestSharedRuntimeCases(t *testing.T) {
	path := filepath.Join("..", "..", "spec", "conformance", "runtime-cases.json")
	content, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var fixture runtimeFixture
	if err := json.Unmarshal(content, &fixture); err != nil {
		t.Fatal(err)
	}
	if len(fixture.Cases) < 8 {
		t.Fatalf("expected at least 8 shared cases, got %d", len(fixture.Cases))
	}
	for _, item := range fixture.Cases {
		t.Run(item.Name, func(t *testing.T) {
			arena, err := NewArena(item.Definition)
			if err != nil {
				t.Fatal(err)
			}
			defer arena.Close()
			output, err := arena.Prepare(item.Request)
			if err != nil {
				t.Fatal(err)
			}
			var prepared struct {
				PromptTokens int    `json:"prompt_tokens"`
				Rendered     string `json:"rendered"`
				Leases       []struct {
					Borrower string `json:"borrower_module_id"`
				} `json:"leases"`
			}
			if err := json.Unmarshal(output, &prepared); err != nil {
				t.Fatal(err)
			}
			if prepared.PromptTokens > item.Assert.MaxPromptTokens {
				t.Fatalf(
					"prompt tokens %d exceed %d",
					prepared.PromptTokens,
					item.Assert.MaxPromptTokens,
				)
			}
			for _, term := range item.Assert.MustContain {
				if !strings.Contains(prepared.Rendered, term) {
					t.Fatalf("rendered output lost %q", term)
				}
			}
			if item.Assert.LeaseBorrower != "" {
				found := false
				for _, lease := range prepared.Leases {
					found = found || lease.Borrower == item.Assert.LeaseBorrower
				}
				if !found {
					t.Fatalf("missing lease for %q", item.Assert.LeaseBorrower)
				}
			}
		})
	}
}

func TestClosedArenaRejectsPrepare(t *testing.T) {
	arena, err := NewArena([]byte(
		`{"arena_id":"closed","modules":[]}`,
	))
	if err != nil {
		t.Fatal(err)
	}
	arena.Close()
	if _, err := arena.Prepare([]byte(`{"model":{"model_profile_id":"m","context_limit_tokens":1,"reserved_output_tokens":0}}`)); err == nil {
		t.Fatal("closed arena accepted prepare")
	}
}
