package main

import (
	"flag"
	"log"
	"net/http"
	"os"

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

	// Combine applications (deduplicate by URL)
	appsMap := make(map[string]Application)
	for _, app := range k3sApps {
		appsMap[app.URL] = app
	}
	for _, app := range configApps {
		appsMap[app.URL] = app
	}

	apps := make([]Application, 0, len(appsMap))
	for _, app := range appsMap {
		apps = append(apps, app)
	}

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

