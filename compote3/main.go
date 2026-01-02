package main

import (
	"flag"
	"log"
	"net/http"
	"os"
	"sort"
	"strings"

	"github.com/gin-gonic/gin"
)

var configPath = flag.String("config", "config.yaml", "Path to configuration file")

func main() {
	flag.Parse()

	// Load configuration
	cfg, err := loadConfig(*configPath)
	if err != nil {
		log.Printf("Warning: failed to load config file: %v. Using defaults.", err)
		cfg = &Config{}
	}

	// Setup router
	r := gin.Default()
	r.LoadHTMLGlob("templates/*")

	// API endpoint
	r.GET("/api/data", func(c *gin.Context) {
		data, err := getData(cfg)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		c.JSON(http.StatusOK, data)
	})

	// Frontend page (data loaded via JavaScript)
	r.GET("/", func(c *gin.Context) {
		c.HTML(http.StatusOK, "index.html", nil)
	})

	// Static files (if needed)
	r.Static("/static", "./static")

	port := os.Getenv("PORT")
	if port == "" {
		port = "9000"
	}

	log.Printf("Starting server on port %s", port)
	if err := r.Run(":" + port); err != nil {
		log.Fatal(err)
	}
}

// Function types for dependency injection (for testing)
type k8sIngressGetter func() ([]Application, error)
type githubTrendingGetter func(period string) ([]GitHubRepo, error)
type githubWatchedGetter func(username string) ([]GitHubRepo, error)

func getData(cfg *Config) (*APIResponse, error) {
	return getDataWithDeps(cfg, getK3sIngresses, getGitHubTrending, getGitHubWatchedRepos)
}

func getDataWithDeps(cfg *Config, getK8sIngresses k8sIngressGetter, getGitHubTrending githubTrendingGetter, getGitHubWatched githubWatchedGetter) (*APIResponse, error) {
	// Get applications from k3s ingresses
	k3sApps, err := getK8sIngresses()
	if err != nil {
		log.Printf("Warning: failed to get k3s ingresses: %v", err)
		k3sApps = []Application{}
	}

	// Process k3s apps: lowercase names, add descriptions, and sort
	apps := make([]Application, 0, len(k3sApps))
	for _, app := range k3sApps {
		app.Name = strings.ToLower(app.Name)
		// Look up description from config (case-insensitive)
		if cfg.Descriptions != nil {
			if desc, exists := cfg.Descriptions[app.Name]; exists {
				app.Description = desc
			}
		}
		apps = append(apps, app)
	}

	// Sort by app name (already lowercased)
	sort.Slice(apps, func(i, j int) bool {
		return apps[i].Name < apps[j].Name
	})

	// Get GitHub trending daily
	githubDaily, err := getGitHubTrending("daily")
	if err != nil {
		log.Printf("Warning: failed to get GitHub daily trending: %v", err)
		githubDaily = []GitHubRepo{}
	}

	// Get GitHub trending weekly
	githubWeekly, err := getGitHubTrending("weekly")
	if err != nil {
		log.Printf("Warning: failed to get GitHub weekly trending: %v", err)
		githubWeekly = []GitHubRepo{}
	}

	// Get watched repos
	githubWatched, err := getGitHubWatched(cfg.GitHub.Watcher)
	if err != nil {
		log.Printf("Warning: failed to get watched repos: %v", err)
		githubWatched = []GitHubRepo{}
	}

	// Build links list from config
	links := []Application{}
	for _, linkCfg := range cfg.Links {
		links = append(links, Application{
			Name: linkCfg.Name,
			URL:  linkCfg.URL,
		})
	}

	// Sort links by name
	sort.Slice(links, func(i, j int) bool {
		return strings.ToLower(links[i].Name) < strings.ToLower(links[j].Name)
	})

	return &APIResponse{
		Applications:  apps,
		Links:         links,
		GitHubDaily:   githubDaily,
		GitHubWeekly:  githubWeekly,
		GitHubWatched: githubWatched,
	}, nil
}
