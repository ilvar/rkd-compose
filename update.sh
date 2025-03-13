#!/bin/bash

if [ $# -ne 1 ]; then
    echo "Usage: $0 SERVER_NAME"
    exit 1
fi

SERVER_NAME=$1
CURRENT_MD5=$(md5sum docker-compose.yaml 2>/dev/null | awk '{print $1}' || echo "none")
TEMP_FILE=$(mktemp)

# Download the new compose file
if curl -sSf "https://gitea.h.rkd.pw/ilvar/rkd-compose/raw/branch/main/docker-compose-${SERVER_NAME}.yaml" -o "$TEMP_FILE"; then
    NEW_MD5=$(md5sum "$TEMP_FILE" | awk '{print $1}')
    
    if [ "$CURRENT_MD5" != "$NEW_MD5" ]; then
        echo "New configuration detected, updating..."
        cp "$TEMP_FILE" docker-compose.yaml
        docker compose up -d --remove-orphans
        echo "Update completed"
    else
        echo "Configuration is up to date"
    fi
else
    echo "Failed to download configuration for $SERVER_NAME"
    exit 1
fi

rm -f "$TEMP_FILE"

echo "Updating the updater..."
curl -sSf "https://gitea.h.rkd.pw/ilvar/rkd-compose/raw/branch/main/update.sh" -o "update.sh"

echo "Done"