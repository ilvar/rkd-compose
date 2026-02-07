package main

import (
	"reflect"
	"testing"
)

func TestExtractTemplateVariables(t *testing.T) {
	tests := []struct {
		name     string
		template string
		want     []string
	}{
		{
			name:     "single variable",
			template: "Hello {{ Имя }}!",
			want:     []string{"Имя"},
		},
		{
			name:     "two variables",
			template: "{{ Фамилия }} {{ Имя }}",
			want:     []string{"Фамилия", "Имя"},
		},
		{
			name:     "three consecutive variables",
			template: "{{ Фамилия }}{{ Имя }}{{ Маршрут }}",
			want:     []string{"Фамилия", "Имя", "Маршрут"},
		},
		{
			name:     "three variables with spaces between",
			template: "{{ Фамилия }} {{ Имя }} {{ Маршрут }}",
			want:     []string{"Фамилия", "Имя", "Маршрут"},
		},
		{
			name:     "no variables",
			template: "plain text without variables",
			want:     nil,
		},
		{
			name:     "empty template",
			template: "",
			want:     nil,
		},
		{
			name:     "duplicate variables",
			template: "{{ Name }} and {{ Name }} again",
			want:     []string{"Name"},
		},
		{
			name:     "variable with extra inner spaces",
			template: "{{  Имя  }}",
			want:     []string{"Имя"},
		},
		{
			name:     "mixed text and variables",
			template: "Привет, {{ Фамилия }} {{ Имя }}! Ваш маршрут: {{ Маршрут }}.",
			want:     []string{"Фамилия", "Имя", "Маршрут"},
		},
		{
			name:     "empty braces",
			template: "{{  }}",
			want:     nil,
		},
		{
			name:     "single braces are not variables",
			template: "{ not a variable }",
			want:     nil,
		},
		{
			name:     "four consecutive variables",
			template: "{{ A }}{{ B }}{{ C }}{{ D }}",
			want:     []string{"A", "B", "C", "D"},
		},
		{
			name:     "multi-word variable names",
			template: "{{ Full Name }}{{ Home Address }}",
			want:     []string{"Full Name", "Home Address"},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := ExtractTemplateVariables(tt.template)
			if !reflect.DeepEqual(got, tt.want) {
				t.Errorf("ExtractTemplateVariables(%q) = %v, want %v", tt.template, got, tt.want)
			}
		})
	}
}
