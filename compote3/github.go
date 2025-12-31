package main

import (
	"context"
	"fmt"
	"os"
	"sort"
	"time"

	"github.com/google/go-github/v56/github"
	"golang.org/x/oauth2"
)

func getGitHubTrending(period string) ([]GitHubRepo, error) {
	ctx := context.Background()
	client := github.NewClient(nil)

	var repos []GitHubRepo

	// GitHub doesn't have a direct API for trending, so we'll use search instead
	// This is a simplified approach - for real trending, you might need to use
	// external APIs or scrape GitHub's trending page
	query := "stars:>100"
	sort := "stars"
	order := "desc"

	if period == "daily" {
		// For daily, limit to repositories updated in the last day
		yesterday := time.Now().AddDate(0, 0, -1).Format("2006-01-02")
		query = fmt.Sprintf("%s pushed:>%s", query, yesterday)
	} else if period == "weekly" {
		// For weekly, limit to repositories updated in the last week
		weekAgo := time.Now().AddDate(0, 0, -7).Format("2006-01-02")
		query = fmt.Sprintf("%s pushed:>%s", query, weekAgo)
	}

	opts := &github.SearchOptions{
		Sort:  sort,
		Order: order,
		ListOptions: github.ListOptions{
			PerPage: 18, // Limit to 18 repos
		},
	}

	result, _, err := client.Search.Repositories(ctx, query, opts)
	if err != nil {
		return nil, fmt.Errorf("failed to search GitHub repos: %w", err)
	}

	for _, repo := range result.Repositories {
		repos = append(repos, GitHubRepo{
			Name:        repo.GetName(),
			FullName:    repo.GetFullName(),
			Description: repo.GetDescription(),
			HTMLURL:     repo.GetHTMLURL(),
			StarCount:   repo.GetStargazersCount(),
			Language:    repo.GetLanguage(),
			UpdatedAt:   repo.GetUpdatedAt().Time,
		})
	}

	// Limit to 18 repos
	if len(repos) > 18 {
		repos = repos[:18]
	}

	return repos, nil
}

func getGitHubWatchedRepos(username string) ([]GitHubRepo, error) {
	if username == "" {
		return []GitHubRepo{}, nil
	}

	ctx := context.Background()
	
	// Use GitHub token if available (optional, but helps with rate limits)
	token := os.Getenv("GITHUB_TOKEN")
	var client *github.Client
	if token != "" {
		ts := oauth2.StaticTokenSource(&oauth2.Token{AccessToken: token})
		tc := oauth2.NewClient(ctx, ts)
		client = github.NewClient(tc)
	} else {
		client = github.NewClient(nil)
	}

	var repos []GitHubRepo
	opts := &github.ActivityListStarredOptions{
		ListOptions: github.ListOptions{
			PerPage: 50, // Request 50 per page to get enough repos
		},
	}

	maxRepos := 50 // Collect up to 50 repos for deduplication

	// Get repositories that the user has starred (publicly accessible)
	starred, _, err := client.Activity.ListStarred(ctx, username, opts)
	if err != nil {
		return nil, fmt.Errorf("failed to get starred repos for %s: %w", username, err)
	}

	for _, repo := range starred {
		if len(repos) >= maxRepos {
			break
		}
		repos = append(repos, GitHubRepo{
			Name:        repo.Repository.GetName(),
			FullName:    repo.Repository.GetFullName(),
			Description: repo.Repository.GetDescription(),
			HTMLURL:     repo.Repository.GetHTMLURL(),
			StarCount:   repo.Repository.GetStargazersCount(),
			Language:    repo.Repository.GetLanguage(),
			UpdatedAt:   repo.Repository.GetUpdatedAt().Time,
		})
	}

	// Handle pagination (collect up to maxRepos repos)
	for len(repos) < maxRepos {
		opts.Page++
		starred, resp, err := client.Activity.ListStarred(ctx, username, opts)
		if err != nil {
			break
		}
		if len(starred) == 0 {
			break
		}
		for _, repo := range starred {
			if len(repos) >= maxRepos {
				break
			}
			repos = append(repos, GitHubRepo{
				Name:        repo.Repository.GetName(),
				FullName:    repo.Repository.GetFullName(),
				Description: repo.Repository.GetDescription(),
				HTMLURL:     repo.Repository.GetHTMLURL(),
				StarCount:   repo.Repository.GetStargazersCount(),
				Language:    repo.Repository.GetLanguage(),
				UpdatedAt:   repo.Repository.GetUpdatedAt().Time,
			})
		}
		if resp.NextPage == 0 {
			break
		}
	}

	// Deduplicate by FullName (keep first occurrence)
	seen := make(map[string]bool)
	var uniqueRepos []GitHubRepo
	for _, repo := range repos {
		if !seen[repo.FullName] {
			seen[repo.FullName] = true
			uniqueRepos = append(uniqueRepos, repo)
		}
	}

	// Sort by UpdatedAt descending (most recently updated first)
	sort.Slice(uniqueRepos, func(i, j int) bool {
		return uniqueRepos[i].UpdatedAt.After(uniqueRepos[j].UpdatedAt)
	})

	// Limit to top 18 repos
	if len(uniqueRepos) > 18 {
		uniqueRepos = uniqueRepos[:18]
	}

	return uniqueRepos, nil
}

