#!/bin/bash

# Port MCP Token Refresh Script
# Fetches a fresh Port access token and writes it to .devin/port_mcp_token.txt
# The .devin/mcp_config.json references this file via ${file:.devin/port_mcp_token.txt}
# so the token is never committed to version control.

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Resolve project root (parent of scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$PROJECT_DIR/.env"
TOKEN_FILE="$PROJECT_DIR/.devin/port_mcp_token.txt"

# Check if .env file exists
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}Error: .env file not found at $ENV_FILE${NC}"
    exit 1
fi

# Load environment variables
export $(grep -v '^#' "$ENV_FILE" | xargs)

# Check if required variables are set
if [ -z "$PORT_CLIENT_ID" ] || [ -z "$PORT_CLIENT_SECRET" ]; then
    echo -e "${RED}Error: PORT_CLIENT_ID or PORT_CLIENT_SECRET not found in .env file${NC}"
    exit 1
fi

echo -e "${YELLOW}Refreshing Port access token...${NC}"

# Request new access token
TOKEN_RESPONSE=$(curl -s -X POST "https://mcp.port.io/v1/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "grant_type=client_credentials" \
    -d "client_id=$PORT_CLIENT_ID" \
    -d "client_secret=$PORT_CLIENT_SECRET")

# Check if token request was successful
if echo "$TOKEN_RESPONSE" | grep -q "error"; then
    echo -e "${RED}Error: Failed to get access token${NC}"
    echo "$TOKEN_RESPONSE"
    exit 1
fi

# Extract access token
ACCESS_TOKEN=$(echo "$TOKEN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

if [ -z "$ACCESS_TOKEN" ]; then
    echo -e "${RED}Error: Could not extract access token from response${NC}"
    echo "$TOKEN_RESPONSE"
    exit 1
fi

echo -e "${GREEN}✓ Access token obtained successfully${NC}"

# Ensure .devin directory exists
mkdir -p "$(dirname "$TOKEN_FILE")"

# Write token to file (gitignored)
echo "$ACCESS_TOKEN" > "$TOKEN_FILE"
chmod 600 "$TOKEN_FILE"

echo -e "${GREEN}✓ Token written to: $TOKEN_FILE${NC}"
echo ""
echo "Port MCP token refreshed successfully."
echo "The token will expire in approximately 2 hours."
echo "Restart your Devin session (or run 'devin mcp reload') to pick up the new token."
