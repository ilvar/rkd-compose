//! Extraction of `{{ variable }}` placeholders from a user-supplied template.
//!
//! The frontend implements the same rule in JavaScript so the tag list updates
//! as you type; this endpoint is the authoritative copy.

use regex::Regex;
use std::sync::OnceLock;

/// Matches `{{ name }}` with exactly two braces a side. The lazy `(.+?)` is
/// what makes consecutive placeholders — `{{ a }}{{ b }}` — parse as two
/// variables instead of one spanning both.
fn variable_pattern() -> Option<&'static Regex> {
    static PATTERN: OnceLock<Option<Regex>> = OnceLock::new();
    PATTERN
        .get_or_init(|| Regex::new(r"\{\{\s*(.+?)\s*\}\}").ok())
        .as_ref()
}

/// Variable names in order of first appearance, without duplicates.
pub fn extract_variables(template: &str) -> Vec<String> {
    let Some(pattern) = variable_pattern() else {
        return Vec::new();
    };

    let mut names: Vec<String> = Vec::new();
    for captures in pattern.captures_iter(template) {
        let Some(name) = captures.get(1) else {
            continue;
        };
        let name = name.as_str().trim();
        if name.is_empty() {
            continue;
        }
        if !names.iter().any(|seen| seen == name) {
            names.push(name.to_owned());
        }
    }
    names
}

#[cfg(test)]
mod tests {
    use super::extract_variables;

    fn owned(names: &[&str]) -> Vec<String> {
        names.iter().map(|name| (*name).to_owned()).collect()
    }

    #[test]
    fn matches_the_go_implementations_table() {
        let cases: Vec<(&str, Vec<String>)> = vec![
            ("Hello {{ Имя }}!", owned(&["Имя"])),
            ("{{ Фамилия }} {{ Имя }}", owned(&["Фамилия", "Имя"])),
            (
                "{{ Фамилия }}{{ Имя }}{{ Маршрут }}",
                owned(&["Фамилия", "Имя", "Маршрут"]),
            ),
            (
                "{{ Фамилия }} {{ Имя }} {{ Маршрут }}",
                owned(&["Фамилия", "Имя", "Маршрут"]),
            ),
            ("plain text without variables", Vec::new()),
            ("", Vec::new()),
            ("{{ Name }} and {{ Name }} again", owned(&["Name"])),
            ("{{  Имя  }}", owned(&["Имя"])),
            (
                "Привет, {{ Фамилия }} {{ Имя }}! Ваш маршрут: {{ Маршрут }}.",
                owned(&["Фамилия", "Имя", "Маршрут"]),
            ),
            ("{{  }}", Vec::new()),
            ("{ not a variable }", Vec::new()),
            ("{{ A }}{{ B }}{{ C }}{{ D }}", owned(&["A", "B", "C", "D"])),
            (
                "{{ Full Name }}{{ Home Address }}",
                owned(&["Full Name", "Home Address"]),
            ),
        ];

        for (template, expected) in cases {
            assert_eq!(
                extract_variables(template),
                expected,
                "template: {template}"
            );
        }
    }

    #[test]
    fn a_placeholder_does_not_span_a_line_break() {
        assert_eq!(extract_variables("{{ a\nb }}"), Vec::<String>::new());
    }
}
