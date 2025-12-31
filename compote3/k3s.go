package main

import (
	"context"
	"fmt"
	"os"
	"path/filepath"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/clientcmd"
)

func getK3sIngresses() ([]Application, error) {
	var config *rest.Config
	var err error

	// Try in-cluster config first (when running in k3s/k8s)
	config, err = rest.InClusterConfig()
	if err != nil {
		// Fall back to kubeconfig file (for local development)
		kubeconfigPath := os.Getenv("KUBECONFIG")
		if kubeconfigPath == "" {
			kubeconfigPath = filepath.Join(os.Getenv("HOME"), ".kube", "config")
		}
		
		// Check if kubeconfig file exists
		if _, err := os.Stat(kubeconfigPath); os.IsNotExist(err) {
			// No kubeconfig and not in cluster - return empty list (app can still run for GitHub features)
			return []Application{}, nil
		}
		
		config, err = clientcmd.BuildConfigFromFlags("", kubeconfigPath)
		if err != nil {
			// If kubeconfig exists but can't be read, return empty list instead of error
			// This allows the app to continue running with GitHub features
			return []Application{}, nil
		}
	}

	clientset, err := kubernetes.NewForConfig(config)
	if err != nil {
		return nil, fmt.Errorf("failed to create k3s client: %w", err)
	}

	ingresses, err := clientset.NetworkingV1().Ingresses("").List(context.TODO(), metav1.ListOptions{})
	if err != nil {
		return nil, fmt.Errorf("failed to list ingresses: %w", err)
	}

	var apps []Application
	appsMap := make(map[string]Application) // Deduplicate by URL
	
	for _, ingress := range ingresses.Items {
		for _, rule := range ingress.Spec.Rules {
			if rule.Host == "" {
				continue
			}
			scheme := "https"
			if len(ingress.Spec.TLS) == 0 {
				scheme = "http"
			}
			// Use the first host for each ingress (most ingresses have one host)
			url := fmt.Sprintf("%s://%s", scheme, rule.Host)
			appName := ingress.Name
			if appName == "" {
				appName = rule.Host
			}
			// Deduplicate by URL - use first name found
			if _, exists := appsMap[url]; !exists {
				appsMap[url] = Application{
					Name: appName,
					URL:  url,
				}
			}
		}
	}
	
	// Convert map to slice
	apps = make([]Application, 0, len(appsMap))
	for _, app := range appsMap {
		apps = append(apps, app)
	}

	return apps, nil
}

