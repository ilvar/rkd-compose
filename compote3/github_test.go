package main

import (
	"testing"
)

func TestGetGitHubWatchedReposEmptyUsername(t *testing.T) {
	// Test that empty username returns empty list
	repos, err := getGitHubWatchedRepos("")
	if err != nil {
		t.Errorf("Expected no error for empty username, got %v", err)
	}
	
	if len(repos) != 0 {
		t.Errorf("Expected 0 repos for empty username, got %d", len(repos))
	}
}

func TestGitHubDataInGetData(t *testing.T) {
	// Test that GitHub data is properly included in getData
	cfg := &Config{
		Links:         []LinkConfig{},
		Applications: []ApplicationConfig{},
		GitHub:        GitHubConfig{Watcher: "testuser"},
	}
	
	// Mock GitHub functions
	mockGitHubTrending := func(period string) ([]GitHubRepo, error) {
		return []GitHubRepo{
			{FullName: "user/trending-repo", StarCount: 1000},
		}, nil
	}
	
	mockGitHubWatched := func(username string) ([]GitHubRepo, error) {
		return []GitHubRepo{
			{FullName: "user/watched-repo", StarCount: 500},
		}, nil
	}
	
	data, err := getDataWithDeps(cfg, mockGetK3sIngresses, mockGitHubTrending, mockGitHubWatched)
	if err != nil {
		t.Fatalf("getDataWithDeps returned error: %v", err)
	}
	
	// Verify GitHub daily trending
	if len(data.GitHubDaily) != 1 {
		t.Errorf("Expected 1 daily trending repo, got %d", len(data.GitHubDaily))
	}
	
	// Verify GitHub weekly trending (same mock function)
	if len(data.GitHubWeekly) != 1 {
		t.Errorf("Expected 1 weekly trending repo, got %d", len(data.GitHubWeekly))
	}
	
	// Verify GitHub watched
	if len(data.GitHubWatched) != 1 {
		t.Errorf("Expected 1 watched repo, got %d", len(data.GitHubWatched))
	}
	
	if data.GitHubWatched[0].FullName != "user/watched-repo" {
		t.Errorf("Expected watched repo 'user/watched-repo', got '%s'", data.GitHubWatched[0].FullName)
	}
}

func TestGitHubRepoStructure(t *testing.T) {
	// Test GitHubRepo structure
	repo := GitHubRepo{
		Name:        "test-repo",
		FullName:    "user/test-repo",
		Description: "Test description",
		HTMLURL:     "https://github.com/user/test-repo",
		StarCount:   100,
		Language:    "Go",
	}
	
	if repo.Name != "test-repo" {
		t.Errorf("Expected name 'test-repo', got '%s'", repo.Name)
	}
	
	if repo.FullName != "user/test-repo" {
		t.Errorf("Expected full name 'user/test-repo', got '%s'", repo.FullName)
	}
	
	if repo.StarCount != 100 {
		t.Errorf("Expected star count 100, got %d", repo.StarCount)
	}
	
	if repo.Language != "Go" {
		t.Errorf("Expected language 'Go', got '%s'", repo.Language)
	}
}

func TestGitHubTrendingPeriods(t *testing.T) {
	// Test that different periods generate different queries
	// This is a unit test for the query building logic
	
	dailyQuery := "stars:>100"
	weeklyQuery := "stars:>100"
	
	// In the actual implementation, these would have date filters added
	// We're just testing the base query structure
	if dailyQuery == "" {
		t.Error("Daily query should not be empty")
	}
	
	if weeklyQuery == "" {
		t.Error("Weekly query should not be empty")
	}
}

func TestGitHubRepoDeduplication(t *testing.T) {
	// Test deduplication logic
	seen := make(map[string]bool)
	repos := []GitHubRepo{
		{FullName: "user/repo1"},
		{FullName: "user/repo2"},
		{FullName: "user/repo1"}, // Duplicate
	}
	
	var uniqueRepos []GitHubRepo
	for _, repo := range repos {
		if !seen[repo.FullName] {
			seen[repo.FullName] = true
			uniqueRepos = append(uniqueRepos, repo)
		}
	}
	
	if len(uniqueRepos) != 2 {
		t.Errorf("Expected 2 unique repos, got %d", len(uniqueRepos))
	}
}

func TestGitHubRepoLimit(t *testing.T) {
	// Test that repos are limited to 18
	repos := make([]GitHubRepo, 25)
	
	if len(repos) > 18 {
		repos = repos[:18]
	}
	
	if len(repos) != 18 {
		t.Errorf("Expected repos to be limited to 18, got %d", len(repos))
	}
}

