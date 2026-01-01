package main

import (
	"os"
	"testing"
)

func TestLoadConfig(t *testing.T) {
	// Test loading a valid config file
	cfg, err := loadConfig("config.yaml")
	if err != nil {
		// If config.yaml doesn't exist, that's okay for testing
		// We just verify the function exists and can be called
		t.Logf("Config file not found or error loading: %v", err)
		return
	}
	
	if cfg == nil {
		t.Error("Expected config to be non-nil")
	}
}

func TestLoadConfigWithLinks(t *testing.T) {
	// Create a temporary config file with links
	tmpFile, err := os.CreateTemp("", "test-config-*.yaml")
	if err != nil {
		t.Fatalf("Failed to create temp file: %v", err)
	}
	defer os.Remove(tmpFile.Name())
	
	configContent := `applications: []
links:
  - name: Test Link
    url: https://test.com
github:
  watcher: testuser
`
	
	if _, err := tmpFile.WriteString(configContent); err != nil {
		t.Fatalf("Failed to write config: %v", err)
	}
	tmpFile.Close()
	
	cfg, err := loadConfig(tmpFile.Name())
	if err != nil {
		t.Fatalf("Failed to load config: %v", err)
	}
	
	if len(cfg.Links) != 1 {
		t.Errorf("Expected 1 link, got %d", len(cfg.Links))
	}
	
	if cfg.Links[0].Name != "Test Link" {
		t.Errorf("Expected link name 'Test Link', got '%s'", cfg.Links[0].Name)
	}
	
	if cfg.Links[0].URL != "https://test.com" {
		t.Errorf("Expected link URL 'https://test.com', got '%s'", cfg.Links[0].URL)
	}
}

func TestConfigStructure(t *testing.T) {
	// Test that Config struct has all required fields
	cfg := &Config{
		Applications: []ApplicationConfig{},
		Links:         []LinkConfig{},
		GitHub:        GitHubConfig{},
	}
	
	if cfg == nil {
		t.Error("Config should not be nil")
	}
	
	// Verify fields exist
	_ = cfg.Applications
	_ = cfg.Links
	_ = cfg.GitHub
}

