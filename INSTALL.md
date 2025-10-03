# Installation Guide - Inputer Performance Monitor

## 🚀 Quick Install with uv (Recommended)

We use [uv](https://docs.astral.sh/uv/) - the fast Python package manager for optimal dependency management.

### Prerequisites

- **Python 3.13+**
- **Chrome/Chromium** browser

### One-Command Setup

```bash
# Clone and setup everything
git clone <repository-url>
cd inputer
./scripts/start.sh
```

The setup script will:
1. ✅ Install `uv` automatically if not present
2. ✅ Create virtual environment
3. ✅ Install all Python dependencies
4. ✅ Create directory structure
5. ✅ Setup configuration template

## 📦 Manual Installation with uv

### 1. Install uv (if not installed)

```bash
# Install uv (fast Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Add to PATH
export PATH="$HOME/.cargo/bin:$PATH"
```

### 2. Install Dependencies

```bash
# Install all dependencies and create virtual environment
uv sync

# Activate the virtual environment
source .venv/bin/activate
```

### 3. Optional Dependencies

```bash
# For development (testing, linting, etc.)
uv sync --extra dev

# For AWS deployment
uv sync --extra aws

# For enhanced testing
uv sync --extra testing

# For monitoring integration
uv sync --extra monitoring

# Install all extras
uv sync --all-extras
```

## 🐍 Alternative: Standard pip Installation

If you prefer traditional pip:

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install project
pip install -e .

# Or install with extras
pip install -e .[dev,aws,testing]
```

## ⚙️ Configuration

### 1. Environment Setup

```bash
# Copy environment template
cp .env.example .env

# Edit configuration
nano .env
```

### 2. Key Environment Variables

```bash
# Chrome configuration
CHROME_EXECUTABLE_PATH=/usr/bin/google-chrome
CHROME_HEADLESS=true

# LLM configuration (choose one)
# Local Ollama
LLM_AGENT_URL=http://localhost:11434
LLM_MODEL=llama2

# AWS Bedrock
LLM_PROVIDER=bedrock
LLM_MODEL=anthropic.claude-3-haiku-20240307-v1:0
```

### 3. Directory Structure

```bash
# Create necessary directories
mkdir -p data/results data/screenshots data/traces logs
```

## 🧪 Verify Installation

### Test Without LLM (Fastest)

```bash
# Test mode - no LLM required
inputer -u https://httpbin.org/html --test-mode mock --max-interactions 3

# Element scan mode
inputer -u https://httpbin.org/html --test-mode element_scan --max-interactions 2
```

### Test With LLM

```bash
# Start Ollama (in separate terminal)
ollama serve
ollama pull llama2

# Run full analysis
inputer -u https://httpbin.org/html --max-interactions 3
```

### Test AWS Bedrock

```bash
# Configure AWS credentials
aws configure

# Test with Bedrock
export LLM_PROVIDER=bedrock
inputer -u https://httpbin.org/html -c config/aws.yaml
```

## 🔧 Development Setup

### Install Development Dependencies

```bash
# Install all development tools
uv sync --extra dev

# Setup pre-commit hooks
pre-commit install
```

### Development Commands

```bash
# Code formatting
black src/inputer/
isort src/inputer/

# Type checking
mypy src/inputer/

# Linting
flake8 src/inputer/
ruff check src/inputer/

# Testing
pytest
pytest --cov=src/inputer/

# Run all quality checks
pre-commit run --all-files
```

## 🌩️ AWS Deployment

### Prerequisites

- AWS CLI configured
- Docker installed
- VPC with public subnets

### Deploy

```bash
# One-command AWS deployment
./scripts/deploy-aws.sh

# Manual configuration
export ENVIRONMENT=prod
export AWS_REGION=us-east-1
./scripts/deploy-aws.sh
```

## 📋 Dependency Management with uv

### Adding Dependencies

```bash
# Add runtime dependency
uv add pandas

# Add development dependency
uv add --dev pytest

# Add optional dependency
uv add --optional aws boto3
```

### Updating Dependencies

```bash
# Update all dependencies
uv sync --upgrade

# Update specific package
uv add pandas@latest
```

### Lock File

The `uv.lock` file ensures reproducible installs:

```bash
# Generate/update lock file
uv lock

# Install from lock file
uv sync --frozen
```

## 🔍 Troubleshooting

### Common Issues

#### 1. uv Not Found

```bash
# Install uv manually
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.cargo/bin:$PATH"

# Restart shell or source profile
source ~/.bashrc  # or ~/.zshrc
```

#### 2. Python Version Issues

```bash
# Check Python version
python --version

# Install specific Python version with uv
uv python install 3.13
uv python pin 3.13
```

#### 3. Virtual Environment Issues

```bash
# Remove and recreate environment
rm -rf .venv
uv sync

# Or specify Python version
uv venv --python 3.13
```

#### 4. Permission Issues

```bash
# Fix permissions on macOS/Linux
sudo chown -R $USER:$USER ~/.local/share/uv
```

#### 5. Network/Proxy Issues

```bash
# Configure proxy for uv
export UV_HTTP_PROXY=http://proxy.example.com:8080
export UV_HTTPS_PROXY=http://proxy.example.com:8080
```

### Performance Issues

If installation is slow:

```bash
# Use closest PyPI mirror
uv sync --index-url https://pypi.org/simple/

# Skip dependency resolution
uv sync --frozen
```

## 📊 Benefits of uv

### Speed Comparison

| Task | pip | uv | Speedup |
|------|-----|-----|---------|
| Install from scratch | 45s | 8s | 5.6x faster |
| Install from cache | 12s | 1s | 12x faster |
| Dependency resolution | 30s | 3s | 10x faster |

### Key Features

- ⚡ **Fast**: 10-100x faster than pip
- 🔒 **Reliable**: Reproducible installs with lock files
- 🛠️ **Modern**: Built-in virtual environment management
- 🎯 **Simple**: Drop-in replacement for pip/pip-tools
- 📦 **Complete**: Handles entire Python project lifecycle

## 📋 Scripts Reference

### Available Scripts

```bash
# From pyproject.toml [project.scripts]
inputer                    # Main CLI command
inputer-test              # Test runner CLI

# Usage examples
inputer -u https://example.com --test-mode mock
inputer-test https://example.com priority
```

### Development Scripts

```bash
# Formatting and linting
uv run black src/inputer/
uv run ruff check src/inputer/

# Testing
uv run pytest
uv run pytest --cov=src/inputer/

# Type checking
uv run mypy src/inputer/
```

## 🎯 Next Steps

1. **Verify Installation**: Run test commands above
2. **Configure Environment**: Edit `.env` file
3. **Run First Analysis**: Try test mode first
4. **Explore Features**: Read [complete documentation](docs.md)
5. **Deploy to AWS**: Use deployment guide

For comprehensive usage instructions, see [README.md](README.md) and [docs.md](docs.md).