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

	// Helper function to get domain priority (lower number = higher priority)
	getDomainPriority := func(url string) int {
		// Check more specific domains first
		if strings.Contains(url, ".k.rkd.pw") {
			return 2 // *.k.rkd.pw has second priority
		}
		if strings.Contains(url, ".h.rkd.pw") {
			return 3 // *.h.rkd.pw has third priority
		}
		if strings.Contains(url, ".rkd.pw") {
			return 1 // *.rkd.pw has highest priority (but not .k or .h)
		}
		return 4 // Other domains have lowest priority
	}

	// Deduplicate by app name (lowercase), prefer higher priority domains
	appsMap := make(map[string]Application)
	for _, app := range k3sApps {
		name := strings.ToLower(app.Name)
		if existing, exists := appsMap[name]; exists {
			// Compare domain priorities - keep the one with higher priority (lower number)
			if getDomainPriority(app.URL) < getDomainPriority(existing.URL) {
				appsMap[name] = app
			}
		} else {
			appsMap[name] = app
		}
	}

	// Convert map to slice, add descriptions, and sort
	apps := make([]Application, 0, len(appsMap))
	for name, app := range appsMap {
		// Create new app with lowercased name
		newApp := Application{
			Name: name, // Already lowercased
			URL:  app.URL,
		}
		// Look up description from config (case-insensitive)
		if cfg.Descriptions != nil {
			if desc, exists := cfg.Descriptions[name]; exists {
				newApp.Description = desc
			}
		}
		apps = append(apps, newApp)
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
