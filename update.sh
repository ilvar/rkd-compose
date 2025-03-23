#!/bin/bash

if [ $# -ne 1 ]; then
    echo "Usage: $0 SERVER_NAME"
    exit 1
fi

SERVER_NAME=$1
CURRENT_MD5_COMPOSE=$(md5sum docker-compose.yaml 2>/dev/null | awk '{print $1}' || echo "none")
TEMP_FILE_COMPOSE=$(mktemp)

# Download the new compose file
if curl -sSf "https://gitea.h.rkd.pw/ilvar/rkd-compose/raw/branch/main/docker-compose-${SERVER_NAME}.yaml" -o "$TEMP_FILE_COMPOSE"; then
    NEW_MD5=$(md5sum "$TEMP_FILE_COMPOSE" | awk '{print $1}')

    if [ "$CURRENT_MD5_COMPOSE" != "$NEW_MD5" ]; then
        echo "New configuration detected, updating..."
        cp "$TEMP_FILE_COMPOSE" docker-compose.yaml
        docker compose up -d --remove-orphans
        echo "Update completed"
    else
        echo "Configuration is up to date"
    fi
else
    echo "Failed to download configuration for $SERVER_NAME"
    exit 1
fi

rm -f "$TEMP_FILE_COMPOSE"

CURRENT_MD5_BLOCKY=$(md5sum ./.docker/blocky/config.yaml 2>/dev/null | awk '{print $1}' || echo "none")
TEMP_FILE_BLOCKY=$(mktemp)

# Download the new compose file
if curl -sSf "https://gitea.h.rkd.pw/ilvar/rkd-compose/raw/branch/main/blocky.yaml" -o "$TEMP_FILE_BLOCKY"; then
    NEW_MD5=$(md5sum "$TEMP_FILE_BLOCKY" | awk '{print $1}')

    if [ "$CURRENT_MD5_BLOCKY" != "$NEW_MD5" ]; then
        echo "New Blocky configuration detected, updating..."
        cp "$TEMP_FILE_BLOCKY" ./.docker/blocky/config.yaml
        docker compose restart blocky
        echo "Update completed"
    else
        echo "Blocky configuration is up to date"
    fi
else
    echo "Failed to download configuration for Blocky"
    exit 1
fi

rm -f "$TEMP_FILE_BLOCKY"

echo "Updating the updater..."
curl -sSf "https://gitea.h.rkd.pw/ilvar/rkd-compose/raw/branch/main/update.sh" -o "update.sh"

echo "Done"
