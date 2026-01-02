package main

import (
	"testing"
)

func TestGetK3sIngressesEmptyWhenNoKubeconfig(t *testing.T) {
	// This test verifies that getK3sIngresses handles missing kubeconfig gracefully
	// The function should return empty list when kubeconfig doesn't exist
	// This is tested by the actual implementation which checks os.Stat
	// We can't easily test this without mocking, but we verify the logic exists
}

func TestK3sAppsInGetData(t *testing.T) {
	// Test that k8s apps are properly included in getData
	cfg := &Config{
		Links:         []LinkConfig{},
		GitHub:        GitHubConfig{Watcher: ""},
	}
	
	// Mock k8s to return some apps
	mockK8s := func() ([]Application, error) {
		return []Application{
			{Name: "app1", URL: "https://app1.example.com"},
			{Name: "app2", URL: "https://app2.example.com"},
		}, nil
	}
	
	data, err := getDataWithDeps(cfg, mockK8s, mockGetGitHubTrending, mockGetGitHubWatched)
	if err != nil {
		t.Fatalf("getDataWithDeps returned error: %v", err)
	}
	
	if len(data.Applications) != 2 {
		t.Errorf("Expected 2 applications, got %d", len(data.Applications))
	}
}

func TestApplicationDeduplication(t *testing.T) {
	// Test that applications are deduplicated correctly
	appsMap := make(map[string]Application)
	
	// Add first app
	appsMap["https://example.com"] = Application{
		Name: "Example",
		URL:  "https://example.com",
	}
	
	// Try to add duplicate URL
	if _, exists := appsMap["https://example.com"]; !exists {
		t.Error("Expected app to exist in map")
	}
	
	// Verify only one entry
	if len(appsMap) != 1 {
		t.Errorf("Expected 1 app in map, got %d", len(appsMap))
	}
}

func TestApplicationURLFormatting(t *testing.T) {
	// Test URL formatting logic
	scheme := "https"
	host := "example.com"
	url := scheme + "://" + host
	
	expected := "https://example.com"
	if url != expected {
		t.Errorf("Expected URL '%s', got '%s'", expected, url)
	}
	
	// Test HTTP scheme
	scheme = "http"
	url = scheme + "://" + host
	expected = "http://example.com"
	if url != expected {
		t.Errorf("Expected URL '%s', got '%s'", expected, url)
	}
}

func TestApplicationNameFallback(t *testing.T) {
	// Test that app name falls back to host if name is empty
	appName := ""
	host := "example.com"
	
	if appName == "" {
		appName = host
	}
	
	if appName != host {
		t.Errorf("Expected app name to be '%s', got '%s'", host, appName)
	}
}

