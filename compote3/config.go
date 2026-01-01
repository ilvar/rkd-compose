package main

import (
	"fmt"
	"os"

	"gopkg.in/yaml.v3"
)

type Config struct {
	Applications []ApplicationConfig `yaml:"applications"`
	GitHub       GitHubConfig        `yaml:"github"`
	Links        []LinkConfig        `yaml:"links"`
}

type ApplicationConfig struct {
	Name string `yaml:"name"`
	URL  string `yaml:"url"`
}

type LinkConfig struct {
	Name string `yaml:"name"`
	URL  string `yaml:"url"`
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

