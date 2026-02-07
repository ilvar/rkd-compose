package main

import "time"

// Application represents a single application with its URL
type Application struct {
	Name        string `json:"name"`
	URL         string `json:"url"`
	Description string `json:"description,omitempty"`
}

// GitHubRepo represents a GitHub repository
type GitHubRepo struct {
	Name        string    `json:"name"`
	FullName    string    `json:"full_name"`
	Description string    `json:"description"`
	HTMLURL     string    `json:"html_url"`
	StarCount   int       `json:"stargazers_count"`
	Language    string    `json:"language"`
	UpdatedAt   time.Time `json:"updated_at"`
}

// APIResponse contains all data for the frontend
type APIResponse struct {
	Applications   []Application `json:"applications"`
	Links          []Application `json:"links"`
	GitHubDaily    []GitHubRepo  `json:"github_daily"`
	GitHubWeekly   []GitHubRepo  `json:"github_weekly"`
	GitHubWatched  []GitHubRepo  `json:"github_watched"`
}

// TemplateParseRequest is the request body for template variable extraction
type TemplateParseRequest struct {
	Template string `json:"template"`
}

// TemplateParseResponse is the response for template variable extraction
type TemplateParseResponse struct {
	Variables []string `json:"variables"`
}

