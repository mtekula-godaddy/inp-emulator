# Inputer Performance Monitor

An intelligent, automated system for discovering and analyzing Interaction to Next Paint (INP) performance issues on web pages using Playwright automation and AI-driven decision making.

## 🎯 Overview

Inputer Performance Monitor automatically:
- Discovers interactive elements on web pages during rendering
- Emulates realistic user interactions with human-like timing
- **Supports mobile emulation** (Pixel 5) with touch events
- Measures INP and other Core Web Vitals metrics
- **Detects visual outcomes** including CSS-only slide-in menus and modals
- Correlates performance issues with specific DOM elements
- Generates comprehensive reports with actionable insights
- **Network throttling support** (Fast 4G, Slow 4G, Fast 3G)

## 🏗️ Architecture

The system consists of three main components:

1. **Python Orchestrator** (`src/python/`) - Central coordination and intelligence
2. **Playwright Browser Automation** - Cross-browser automation and performance measurement
3. **LLM Agent** - AI-driven decision making for element selection (Local/AWS Bedrock)

### Key Components

- **Element Discovery Engine** - Intelligently finds interactive elements during page rendering (buttons, links, dropdowns, carousels, tabs, form elements)
  - **Smart Filtering**: Automatically excludes navigation, footer, and share/social buttons
  - **Validated Selectors**: Generates reliable CSS selectors that work with querySelector
  - **Priority Scoring**: Ranks elements by INP potential for targeted testing
- **User Interaction Engine** - Emulates realistic user behavior with mobile touch events and desktop mouse interactions
- **Performance Analyzer** - Measures and correlates INP with specific elements
- **Outcome Detection** - Advanced detection of visual changes including:
  - DOM mutations (element additions/removals)
  - CSS class changes (htmlClassName, bodyClassName)
  - Visibility changes (dialogs, overlays, drawers via getBoundingClientRect)
  - Text appearance (slide-in menus, filters, modals)
- **Data Exporter** - Generates reports in multiple formats (JSON, CSV, HTML)
- **Test Runner** - Testing capabilities without LLM dependency
- **Screenshot Capture** - Session-organized before/after screenshots for debugging

## 🚀 Quick Start

### Prerequisites

- Python 3.13+
- Chrome/Chromium browser
- Local LLM agent (e.g., Ollama with Llama2) OR AWS Bedrock access (optional for test mode)

### Installation

1. **One-command setup (recommended):**
   ```bash
   git clone <repository-url>
   cd inputer
   ./scripts/start.sh
   ```

2. **Manual setup with uv (fast Python package manager):**
   ```bash
   # Install uv if needed
   curl -LsSf https://astral.sh/uv/install.sh | sh

   # Install dependencies
   uv sync
   source .venv/bin/activate

   # Install package
   uv pip install -e .
   ```

3. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

4. **Start the LLM agent (for standard mode):**
   ```bash
   # Example with Ollama
   ollama serve
   ollama pull llama2
   ```

### Usage Examples

#### Standard Analysis (with LLM)
```bash
# Basic analysis
inputer -u https://example.com

# Multiple URLs with custom settings
inputer \
  -u https://site1.com \
  -u https://site2.com \
  --max-interactions 15 \
  --verbose
```

#### Test Mode (without LLM) 🧪

**Perfect for development and CI/CD where you don't want LLM dependencies:**

```bash
# Element scan mode - Tests all discovered elements systematically
# Default: Tests 2 elements per page, excludes nav/footer/share buttons
PYTHONPATH=/path/to/inputer/src python3 src/inputer/testing/test_runner.py https://example.com element_scan priority

# Test more elements (e.g., 5)
PYTHONPATH=/path/to/inputer/src python3 src/inputer/testing/test_runner.py https://example.com element_scan priority 5

# Include header/nav elements (default: excluded)
PYTHONPATH=/path/to/inputer/src python3 src/inputer/testing/test_runner.py https://example.com element_scan priority --include-header

# Test multiple URLs from a file
PYTHONPATH=/path/to/inputer/src python3 src/inputer/testing/test_runner.py urls.txt element_scan priority

# Different strategies
PYTHONPATH=/path/to/inputer/src python3 src/inputer/testing/test_runner.py https://example.com element_scan sequential   # Test in order
PYTHONPATH=/path/to/inputer/src python3 src/inputer/testing/test_runner.py https://example.com element_scan random       # Random selection
PYTHONPATH=/path/to/inputer/src python3 src/inputer/testing/test_runner.py https://example.com element_scan problematic  # Target known problem elements
```

#### AWS Bedrock Mode (Production)
```bash
# Configure for AWS Bedrock
export LLM_PROVIDER=bedrock
export LLM_MODEL=anthropic.claude-3-haiku-20240307-v1:0
inputer -u https://example.com -c config/aws.yaml
```

## 🧪 Testing Modes

### When to Use Each Mode

| Mode | Use Case | LLM Required | Best For |
|------|----------|--------------|----------|
| **Standard** | Production analysis | ✅ | Deep insights, intelligent element selection |
| **Mock** | Development/CI | ❌ | Quick testing, debugging element discovery |
| **Element Scan** | Comprehensive testing | ❌ | Testing all elements, baseline analysis |
| **Deterministic** | Regression testing | ❌ | Consistent, repeatable test runs |

### Testing Strategies

- **Priority**: Targets elements with highest INP potential scores
- **Sequential**: Tests elements in discovery order
- **Random**: Random element selection for coverage
- **Problematic**: Focuses on known problematic element types (dropdowns, modals, etc.)

### Test Mode Benefits

- **No LLM Dependencies**: Run without Ollama or AWS Bedrock
- **Faster Execution**: No API calls or model loading delays
- **Deterministic Results**: Predictable for CI/CD pipelines
- **Development Friendly**: Debug element discovery and interaction logic
- **Cost Effective**: No LLM API costs for testing

## 📊 Understanding Results

### Report Formats

1. **JSON Report** - Complete data for programmatic analysis
2. **CSV Report** - Tabular data for spreadsheet analysis
3. **HTML Report** - Visual report for human review
4. **Summary Text** - Key insights and recommendations

### Key Metrics

- **INP Score** - Interaction to Next Paint measurement
- **Element Classification** - Good (< 200ms), Needs Improvement (200-500ms), Poor (> 500ms)
- **Layout Shifts** - Cumulative Layout Shift (CLS) measurements
- **JavaScript Blocking** - Assessment of script execution impact

### Example Output
```
🧪 Test Results Summary
Test Mode: mock
Strategy: priority
URLs Tested: 1/1
Total Interactions: 8
Worst INP: 847ms on https://example.com

📄 Report saved to: ./test_results/test_report_priority_1699123456.json
```

## 🔧 Configuration

### Environment Variables

Key environment variables (see `.env.example`):

```bash
# Browser Configuration
CHROME_HEADLESS=false  # Default headed mode to avoid bot detection
CHROME_DISABLE_GPU=true
MOBILE_EMULATION=true  # Enable Pixel 5 mobile emulation
NETWORK_THROTTLING=None  # Options: None, "Fast 4G", "Slow 4G", "Fast 3G"

# Performance Settings
MAX_INTERACTIONS_PER_PAGE=10
INTERACTION_DELAY_MIN=500
INTERACTION_DELAY_MAX=2000
SCREENSHOT_CAPTURE=true  # Capture before/after screenshots
VIDEO_CAPTURE=false  # Record session videos

# LLM Configuration (Local)
LLM_AGENT_URL=http://localhost:11434
LLM_MODEL=llama2

# LLM Configuration (AWS Bedrock)
LLM_PROVIDER=bedrock
LLM_MODEL=anthropic.claude-3-haiku-20240307-v1:0
```

### Configuration Files

- `config/config.yaml` - Local development
- `config/aws.yaml` - AWS Bedrock production

## 🌩️ AWS Deployment

### One-Command AWS Deployment

```bash
# Deploy entire infrastructure to AWS
./scripts/deploy-aws.sh

# Prompts for VPC ID and Subnet IDs
# Creates: ECS Fargate + Bedrock + S3 + Lambda + CloudWatch
```

### AWS Features

- **ECS Fargate**: Serverless container deployment
- **AWS Bedrock**: Managed Claude LLM service
- **S3**: Results storage with lifecycle policies
- **Lambda**: Scheduled analysis triggers
- **CloudWatch**: Comprehensive monitoring and alerting

### AWS Usage

```bash
# Manual analysis via Lambda
aws lambda invoke --function-name inputer-scheduled-prod \
  --payload '{"urls":["https://example.com"],"subnets":["subnet-xxx"]}' \
  response.json

# View results
aws s3 sync s3://inputer-results-prod-123456789012/results/ ./results/
```

## 🔍 Development and Testing

### Running Tests

```bash
# With uv (recommended)
uv run pytest tests/unit/
uv run pytest tests/integration/
uv run pytest --cov=src/python/

# Traditional method
pytest tests/unit/
pytest tests/integration/
pytest --cov=src/python/
```

### Development Tools

```bash
# With uv (recommended)
uv run black src/python/
uv run ruff check src/python/
uv run mypy src/python/

# Traditional method
black src/python/
flake8 src/python/
mypy src/python/
```

### Quick Development Testing

```bash
# Test element discovery without LLM
python src/python/main.py -u https://example.com --test-mode element_scan --max-interactions 3

# Debug mode with screenshots
python src/python/main.py -u https://example.com --test-mode mock --verbose
```

## 🔍 Troubleshooting

### Common Issues

1. **Chrome fails to start:**
   ```bash
   # Check Chrome installation
   google-chrome --version
   export CHROME_EXECUTABLE_PATH=/usr/bin/chromium-browser
   ```

2. **LLM agent connection fails:**
   ```bash
   # Test LLM endpoint
   curl http://localhost:11434/v1/models
   ollama list  # For Ollama
   ```

3. **Test mode not working:**
   ```bash
   # Verify test mode is active
   python src/python/main.py -u https://example.com --test-mode mock --verbose
   ```

### Debug Mode

Enable verbose logging:
```bash
python src/python/main.py --verbose -u https://example.com --test-mode mock
```

## 📈 Performance Optimization

### For Different Use Cases

**Development/Testing:**
- Use `--test-mode mock` for fast iteration
- Reduce `--max-interactions` for quick tests
- Enable `--verbose` for debugging

**Production Analysis:**
- Use AWS Bedrock for reliability
- Configure appropriate `max_interactions_per_page`
- Set up monitoring and alerting

**CI/CD Integration:**
- Use `--test-mode element_scan` for comprehensive testing
- Set deterministic settings for consistent results
- Store results in artifact storage

## 🎯 Use Cases

### Development Teams
```bash
# Pre-deployment performance testing
python src/python/main.py -u https://staging.myapp.com --test-mode element_scan
```

### QA Automation
```bash
# CI/CD integration without LLM dependencies
python src/python/main.py -u https://app.example.com --test-mode mock --test-strategy priority
```

### Performance Monitoring
```bash
# Production monitoring with AWS
aws lambda invoke --function-name inputer-scheduled-prod --payload '{"urls":["https://production.app"]}'
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make changes and add tests
4. Run tests: `uv run pytest` and `uv run black src/python/`
5. Commit changes: `git commit -m 'Add amazing feature'`
6. Push to branch: `git push origin feature/amazing-feature`
7. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙋 Support

- **Issues:** [GitHub Issues](https://github.com/your-org/inputer/issues)
- **Documentation:** [Complete Documentation](docs.md)
- **AWS Deployment:** [AWS Deployment Guide](docs/AWS-DEPLOYMENT.md)

## 🎯 Key Features Summary

✅ **Intelligent Element Discovery** - Finds 16+ types of interactive elements during page rendering
✅ **Smart Content Filtering** - Automatically excludes nav/footer/share buttons, focuses on content interactions
✅ **Validated Selectors** - Generates reliable CSS selectors using class-based and nth-of-type patterns
✅ **Mobile Emulation** - Pixel 5 device emulation with touch events (tap vs click)
✅ **Advanced Outcome Detection** - 11 detection methods including CSS visibility, text appearance, DOM mutations
✅ **Network Throttling** - Fast 4G, Slow 4G, Fast 3G simulation for realistic testing
✅ **AI-Driven Testing** - LLM-powered element selection
✅ **Test Modes** - Run without LLM dependencies
✅ **Realistic User Simulation** - Human-like interaction timing with mobile/desktop differentiation
✅ **Real-Time Performance Measurement** - True INP from tap to visual outcome (not just first paint)
✅ **Session Screenshots** - Organized before/after captures in `data/screenshots/{session_id}/`
✅ **Multi-Format Reporting** - JSON, CSV, HTML outputs
✅ **AWS Production Ready** - ECS Fargate + Bedrock deployment
✅ **Development Friendly** - Test modes for debugging and CI/CD
✅ **Bot Detection Avoidance** - navigator.webdriver override, headed mode default
✅ **Enterprise Monitoring** - CloudWatch dashboards and alerting

Perfect for development teams who need both intelligent analysis and fast testing capabilities with real mobile device accuracy!