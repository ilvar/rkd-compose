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
	for _, ingress := range ingresses.Items {
		for _, rule := range ingress.Spec.Rules {
			for _, path := range rule.HTTP.Paths {
				scheme := "https"
				if len(ingress.Spec.TLS) == 0 {
					scheme = "http"
				}
				url := fmt.Sprintf("%s://%s%s", scheme, rule.Host, path.Path)
				if path.Path == "/" {
					url = fmt.Sprintf("%s://%s", scheme, rule.Host)
				}
				appName := ingress.Name
				if appName == "" {
					appName = rule.Host
				}
				apps = append(apps, Application{
					Name: appName,
					URL:  url,
				})
			}
		}
	}

	return apps, nil
}

