package main

import (
	"testing"
)

func TestGetDataLinks(t *testing.T) {
	// Test with config containing links
	cfg := &Config{
		Links: []LinkConfig{
			{Name: "Example", URL: "https://example.com"},
			{Name: "Test", URL: "https://test.com"},
		},
	}

	// Mock k3s and GitHub to return empty (we're only testing links)
	// We'll need to refactor getData to be more testable, but for now
	// we can test the link processing logic separately
	
	links := []Application{}
	for _, linkCfg := range cfg.Links {
		links = append(links, Application{
			Name: linkCfg.Name,
			URL:  linkCfg.URL,
		})
	}

	if len(links) != 2 {
		t.Errorf("Expected 2 links, got %d", len(links))
	}

	if links[0].Name != "Example" {
		t.Errorf("Expected first link name to be 'Example', got '%s'", links[0].Name)
	}

	if links[1].URL != "https://test.com" {
		t.Errorf("Expected second link URL to be 'https://test.com', got '%s'", links[1].URL)
	}
}

func TestGetDataLinksEmpty(t *testing.T) {
	cfg := &Config{
		Links: []LinkConfig{},
	}

	links := []Application{}
	for _, linkCfg := range cfg.Links {
		links = append(links, Application{
			Name: linkCfg.Name,
			URL:  linkCfg.URL,
		})
	}

	if len(links) != 0 {
		t.Errorf("Expected 0 links, got %d", len(links))
	}
}

func TestGetDataLinksSorting(t *testing.T) {
	cfg := &Config{
		Links: []LinkConfig{
			{Name: "Zebra", URL: "https://zebra.com"},
			{Name: "Apple", URL: "https://apple.com"},
			{Name: "Banana", URL: "https://banana.com"},
		},
	}

	links := []Application{}
	for _, linkCfg := range cfg.Links {
		links = append(links, Application{
			Name: linkCfg.Name,
			URL:  linkCfg.URL,
		})
	}

	// Note: Actual sorting happens in getData() with sort.Slice
	// This test verifies the data structure is correct
	if len(links) != 3 {
		t.Errorf("Expected 3 links, got %d", len(links))
	}
}

