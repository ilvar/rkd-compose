package main

import (
	"regexp"
	"strings"
)

// templateVarRegex matches {{ variable_name }} with exactly two braces on each side.
// Uses non-greedy matching to correctly handle consecutive variables like
// {{ Фамилия }}{{ Имя }}{{ Маршрут }}.
var templateVarRegex = regexp.MustCompile(`\{\{\s*(.+?)\s*\}\}`)

// ExtractTemplateVariables extracts variable names from a template string.
// Variables are denoted by {{ variable_name }} syntax.
// Returns unique variable names in order of first appearance.
func ExtractTemplateVariables(template string) []string {
	matches := templateVarRegex.FindAllStringSubmatch(template, -1)
	seen := make(map[string]bool)
	var vars []string
	for _, match := range matches {
		name := strings.TrimSpace(match[1])
		if name == "" {
			continue
		}
		if !seen[name] {
			seen[name] = true
			vars = append(vars, name)
		}
	}
	return vars
}
