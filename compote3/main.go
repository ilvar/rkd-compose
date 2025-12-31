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

func getData(cfg *Config) (*APIResponse, error) {
	// Get applications from k3s ingresses
	k3sApps, err := getK3sIngresses()
	if err != nil {
		log.Printf("Warning: failed to get k3s ingresses: %v", err)
		k3sApps = []Application{}
	}

	// Get applications from config
	configApps := []Application{}
	for _, appCfg := range cfg.Applications {
		configApps = append(configApps, Application{
			Name: appCfg.Name,
			URL:  appCfg.URL,
		})
	}

	// Combine applications (deduplicate by app name, prefer certain domains)
	appsMap := make(map[string]Application)

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

	// Add k3s apps first
	for _, app := range k3sApps {
		name := app.Name
		if existing, exists := appsMap[name]; exists {
			// Compare domain priorities - keep the one with higher priority (lower number)
			if getDomainPriority(app.URL) < getDomainPriority(existing.URL) {
				appsMap[name] = app
			}
		} else {
			appsMap[name] = app
		}
	}

	// Add config apps (config apps take precedence if same name)
	for _, app := range configApps {
		name := app.Name
		if existing, exists := appsMap[name]; exists {
			// Config apps have priority, but still respect domain preference
			if getDomainPriority(app.URL) <= getDomainPriority(existing.URL) {
				appsMap[name] = app
			}
		} else {
			appsMap[name] = app
		}
	}

	// Convert map to slice, lowercase names, and sort by name
	apps := make([]Application, 0, len(appsMap))
	for _, app := range appsMap {
		app.Name = strings.ToLower(app.Name)
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
	githubWatched, err := getGitHubWatchedRepos(cfg.GitHub.Watcher)
	if err != nil {
		log.Printf("Warning: failed to get watched repos: %v", err)
		githubWatched = []GitHubRepo{}
	}

	return &APIResponse{
		Applications:  apps,
		GitHubDaily:   githubDaily,
		GitHubWeekly:  githubWeekly,
		GitHubWatched: githubWatched,
	}, nil
}
