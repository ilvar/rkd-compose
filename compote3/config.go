package main

import (
	"fmt"
	"os"

	"gopkg.in/yaml.v3"
)

type Config struct {
	Descriptions []DescriptionConfig    `yaml:"descriptions"` // List of app name -> description pairs
	GitHub       GitHubConfig           `yaml:"github"`
	Links        []LinkConfig           `yaml:"links"`
	Exclusions   []string               `yaml:"exclusions"`   // List of app names to exclude
	Overrides    []AppOverride          `yaml:"overrides"`     // List of app name/URL overrides
}

type AppOverride struct {
	Name string `yaml:"name"` // Original app name (case-insensitive match)
	NewName string `yaml:"new_name,omitempty"` // New display name (optional)
	URL   string `yaml:"url,omitempty"`      // Override URL (optional)
}

type LinkConfig struct {
	Name string `yaml:"name"`
	URL  string `yaml:"url"`
}

type DescriptionConfig struct {
	Name        string `yaml:"name"`
	Description string `yaml:"description"`
}

type GitHubConfig struct {
	Watcher string `yaml:"watcher"`
}

func loadConfig(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("failed to read config file: %w", err)
	}

	var config Config
	if err := yaml.Unmarshal(data, &config); err != nil {
		return nil, fmt.Errorf("failed to parse config file: %w", err)
	}

	return &config, nil
}

