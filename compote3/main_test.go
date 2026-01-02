package main

import (
	"testing"
)

// Mock functions for testing
func mockGetK3sIngresses() ([]Application, error) {
	return []Application{
		{Name: "test-app", URL: "https://test-app.example.com"},
	}, nil
}

func mockGetK3sIngressesError() ([]Application, error) {
	return nil, nil // Return empty on error (matching real behavior)
}

func mockGetGitHubTrending(period string) ([]GitHubRepo, error) {
	return []GitHubRepo{
		{
			Name:        "test-repo",
			FullName:    "user/test-repo",
			Description: "Test repository",
			HTMLURL:     "https://github.com/user/test-repo",
			StarCount:   100,
			Language:    "Go",
		},
	}, nil
}

func mockGetGitHubWatched(username string) ([]GitHubRepo, error) {
	if username == "" {
		return []GitHubRepo{}, nil
	}
	return []GitHubRepo{
		{
			Name:        "watched-repo",
			FullName:    "user/watched-repo",
			Description: "Watched repository",
			HTMLURL:     "https://github.com/user/watched-repo",
			StarCount:   50,
			Language:    "Python",
		},
	}, nil
}

func TestGetDataLinksIntegration(t *testing.T) {
	// Test that getData includes links from config
	cfg := &Config{
		Links: []LinkConfig{
			{Name: "Test Link", URL: "https://test.com"},
		},
		GitHub:        GitHubConfig{Watcher: "testuser"},
	}
	
	// Use mocked functions to avoid k8s/github timeouts
	data, err := getDataWithDeps(cfg, mockGetK3sIngresses, mockGetGitHubTrending, mockGetGitHubWatched)
	if err != nil {
		t.Fatalf("getDataWithDeps returned error: %v", err)
	}
	
	// Verify links are included
	if len(data.Links) != 1 {
		t.Errorf("Expected 1 link, got %d", len(data.Links))
	}
	
	if data.Links[0].Name != "Test Link" {
		t.Errorf("Expected link name 'Test Link', got '%s'", data.Links[0].Name)
	}
	
	if data.Links[0].URL != "https://test.com" {
		t.Errorf("Expected link URL 'https://test.com', got '%s'", data.Links[0].URL)
	}
	
	// Verify k8s apps are included
	if len(data.Applications) == 0 {
		t.Error("Expected at least one application from mock")
	}
	
	// Verify GitHub data is included
	if len(data.GitHubDaily) == 0 {
		t.Error("Expected GitHub daily trending data")
	}
	
	if len(data.GitHubWatched) == 0 {
		t.Error("Expected GitHub watched repos")
	}
}

func TestGetDataWithEmptyConfig(t *testing.T) {
	// Test getData with empty config
	cfg := &Config{
		Links:         []LinkConfig{},
		GitHub:        GitHubConfig{Watcher: ""},
	}
	
	// Use mocked functions
	data, err := getDataWithDeps(cfg, mockGetK3sIngresses, mockGetGitHubTrending, mockGetGitHubWatched)
	if err != nil {
		t.Fatalf("getDataWithDeps returned error: %v", err)
	}
	
	// Should still work with empty config
	if data == nil {
		t.Fatal("Expected non-nil data")
	}
	
	// Links should be empty
	if len(data.Links) != 0 {
		t.Errorf("Expected 0 links, got %d", len(data.Links))
	}
}

func TestGetDataWithK8sError(t *testing.T) {
	// Test that k8s errors are handled gracefully
	cfg := &Config{
		Links: []LinkConfig{
			{Name: "Test Link", URL: "https://test.com"},
		},
		GitHub:        GitHubConfig{Watcher: ""},
	}
	
	// Use mock that returns empty (simulating error handling)
	data, err := getDataWithDeps(cfg, mockGetK3sIngressesError, mockGetGitHubTrending, mockGetGitHubWatched)
	if err != nil {
		t.Fatalf("getDataWithDeps returned error: %v", err)
	}
	
	// Should still return data even if k8s fails
	if data == nil {
		t.Fatal("Expected non-nil data even with k8s error")
	}
	
	// Links should still be present
	if len(data.Links) != 1 {
		t.Errorf("Expected 1 link, got %d", len(data.Links))
	}
}

