#!/bin/bash
# Helm lint validation script

set -e

CHART_DIR="apps-chart"

if [ ! -d "$CHART_DIR" ]; then
  echo "❌ Chart directory not found: $CHART_DIR"
  exit 1
fi

echo "🔍 Running helm lint on $CHART_DIR..."

if helm lint "$CHART_DIR" --strict; then
  echo "✅ Helm lint passed!"
  exit 0
else
  echo "❌ Helm lint failed!"
  exit 1
fi
