#!/bin/bash

# Inputer Performance Monitor Startup Script

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Inputer Performance Monitor${NC}"
echo -e "${BLUE}================================${NC}"

# Check if Python is available
if ! command -v python &> /dev/null; then
    echo -e "${RED}❌ Python is not installed${NC}"
    exit 1
fi

# Check if uv is available
if ! command -v uv &> /dev/null; then
    echo -e "${YELLOW}📦 Installing uv (fast Python package manager)...${NC}"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
    if ! command -v uv &> /dev/null; then
        echo -e "${RED}❌ Failed to install uv${NC}"
        echo -e "${YELLOW}   Falling back to pip...${NC}"
        USE_PIP=true
    fi
fi

# Check if Chrome is available
if ! command -v google-chrome &> /dev/null && ! command -v chromium-browser &> /dev/null; then
    echo -e "${YELLOW}⚠️  Chrome/Chromium not found in PATH${NC}"
    echo -e "${YELLOW}   Make sure Chrome is installed or set CHROME_EXECUTABLE_PATH${NC}"
fi

# Setup Python environment and install dependencies
if [ "$USE_PIP" = true ]; then
    # Fallback to pip method
    if [ ! -d "venv" ]; then
        echo -e "${YELLOW}📦 Creating Python virtual environment...${NC}"
        python -m venv venv
    fi

    echo -e "${YELLOW}🔌 Activating virtual environment...${NC}"
    source venv/bin/activate

    echo -e "${YELLOW}📦 Installing Python dependencies with pip...${NC}"
    pip install -e .
else
    # Use uv for faster installation
    echo -e "${YELLOW}📦 Installing Python dependencies with uv...${NC}"
    uv sync

    # Create virtual environment and install project
    if [ ! -d ".venv" ]; then
        echo -e "${YELLOW}🔌 Creating uv virtual environment...${NC}"
        uv venv
    fi

    echo -e "${YELLOW}🔌 Activating uv virtual environment...${NC}"
    source .venv/bin/activate
fi


# Create necessary directories
echo -e "${YELLOW}📁 Creating directories...${NC}"
mkdir -p data/results data/screenshots data/traces logs

# Copy environment file if it doesn't exist
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚙️  Creating .env file from template...${NC}"
    cp .env.example .env
    echo -e "${YELLOW}   Please edit .env with your configuration${NC}"
fi

# Check if LLM agent is running
echo -e "${YELLOW}🤖 Checking LLM agent...${NC}"
LLM_URL=${LLM_AGENT_URL:-"http://localhost:11434"}
if curl -s "$LLM_URL/v1/models" &> /dev/null; then
    echo -e "${GREEN}✅ LLM agent is running${NC}"
else
    echo -e "${YELLOW}⚠️  LLM agent not reachable at $LLM_URL${NC}"
    echo -e "${YELLOW}   Make sure Ollama or your LLM agent is running${NC}"
    echo -e "${YELLOW}   Example: ollama serve${NC}"
fi

echo -e "${GREEN}✅ Setup complete!${NC}"
echo ""
echo -e "${BLUE}Usage Examples:${NC}"
echo -e "${YELLOW}  Basic analysis:${NC}"
echo -e "    inputer -u https://example.com"
echo ""
echo -e "${YELLOW}  Multiple URLs:${NC}"
echo -e "    inputer -u https://site1.com -u https://site2.com"
echo ""
echo -e "${YELLOW}  With configuration:${NC}"
echo -e "    inputer -u https://example.com -c config/config.yaml -v"
echo ""
echo -e "${YELLOW}  Test mode (no LLM required):${NC}"
echo -e "    inputer -u https://example.com --test-mode mock"
echo ""
echo -e "${YELLOW}  AWS deployment:${NC}"
echo -e "    ./scripts/deploy-aws.sh"
echo ""
echo -e "${BLUE}For more information, see README.md${NC}"