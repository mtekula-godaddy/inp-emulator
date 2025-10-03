# Inputer Performance Monitor - Complete Documentation

## 📋 Table of Contents

- [Project Overview](#-project-overview)
- [Architecture](#-architecture)
- [Core Components](#-core-components)
- [Deployment Options](#-deployment-options)
- [Configuration](#-configuration)
- [Usage Examples](#-usage-examples)
- [API Reference](#-api-reference)
- [Monitoring & Observability](#-monitoring--observability)
- [Troubleshooting](#-troubleshooting)
- [Development Guide](#-development-guide)

## 🎯 Project Overview

**Inputer Performance Monitor** is an intelligent, automated system for discovering and analyzing Interaction to Next Paint (INP) performance issues on web pages. It combines Chrome DevTools automation, AI-driven decision making, and realistic user interaction simulation to identify DOM elements causing poor Core Web Vitals performance.

### Key Features

- **Intelligent Element Discovery**: Finds interactive elements during page rendering
- **AI-Driven Testing**: Uses LLM to select elements most likely to cause INP issues
- **Realistic User Simulation**: Human-like interaction patterns and timing
- **Real-Time Performance Measurement**: Correlates INP scores with specific DOM elements
- **Multi-Format Reporting**: JSON, CSV, HTML reports with actionable insights
- **Production-Ready Deployment**: Docker Compose and AWS infrastructure

### Use Cases

- **Development Teams**: Pre-deployment performance testing
- **QA Automation**: Continuous performance monitoring in CI/CD
- **Performance Engineers**: Detailed INP analysis and optimization
- **Product Teams**: User experience impact assessment

## 🏗️ Architecture

### High-Level Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  Python         │    │  Chrome DevTools │    │  LLM Agent      │
│  Orchestrator   │◄──►│  MCP Server      │    │ (Local/Bedrock) │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Core Components                              │
├─────────────────┬─────────────────┬─────────────────┬───────────┤
│ Element         │ Interaction     │ Performance     │ Data      │
│ Discovery       │ Engine          │ Analyzer        │ Exporter  │
│ Engine          │                 │                 │           │
└─────────────────┴─────────────────┴─────────────────┴───────────┘
```

### Component Interaction Flow

1. **Observe**: Element Discovery Engine finds interactive elements
2. **Reason**: LLM Agent selects optimal element for testing
3. **Act**: Interaction Engine performs realistic user interactions
4. **Measure**: Performance Analyzer captures INP and correlates with elements
5. **Report**: Data Exporter generates comprehensive reports

### Deployment Architectures

#### Local Development
```
Docker Compose → [App + Ollama + Prometheus + Grafana]
```

#### AWS Production
```
ECS Fargate → [App Container] → AWS Bedrock (Claude)
     ↓              ↓               ↓
Lambda Scheduler   S3 Results   CloudWatch Monitoring
```

## 🔧 Core Components

### 1. Element Discovery Engine (`src/python/core/element_discovery.py`)

**Purpose**: Intelligently discovers interactive elements during page rendering.

#### Key Features

- **Multi-Stage Discovery**:
  - Immediate elements (visible on load)
  - Dynamic elements (appear after load)
  - Lazy-loaded elements (triggered by scrolling)

- **INP Potential Scoring**: Prioritizes elements likely to cause performance issues
- **Smart Filtering**: Avoids disabled, hidden, or non-meaningful elements
- **Complex Element Detection**: Targets dropdowns, accordions, modals, carousels

#### Example Usage

```python
from core.element_discovery import ElementDiscoveryEngine

engine = ElementDiscoveryEngine(mcp_client, settings)
elements = await engine.discover_interactive_elements()

# Elements are returned with INP potential scores
for element in elements:
    print(f"Element: {element['selector']}")
    print(f"INP Potential: {element['inp_potential_score']}")
    print(f"Type: {element['type']}")
```

#### INP Potential Scoring Algorithm

```python
def _calculate_inp_potential(self, element: Dict[str, Any]) -> float:
    """
    Scoring factors:
    - Element type (button: 3.0, dropdown: 4.0, etc.)
    - Complex class names (+1.5 each)
    - Data attributes (+1.0)
    - JavaScript indicators (+1.0)
    - Discovery stage bonus (dynamic: +2.0, lazy: +1.5)
    """
    # Implementation details in source code
```

### 2. User Interaction Engine (`src/python/core/interaction_engine.py`)

**Purpose**: Executes realistic user interactions with human-like timing patterns.

#### Key Features

- **Human-Like Timing**: Variable delays based on interaction type and history
- **Progressive Interactions**: Hover before click, realistic typing speed
- **Context-Aware Delays**: Adjusts based on previous interactions
- **Page Stability Detection**: Waits for dynamic content to settle

#### Interaction Types

```python
# Click with realistic hover
await engine.execute_interaction({
    "action": "click",
    "selector": ".dropdown-toggle"
})

# Type with keystroke delays
await engine.execute_interaction({
    "action": "type",
    "selector": "#search-input",
    "text": "performance testing"
})

# Scroll with chunked movement
await engine.execute_interaction({
    "action": "scroll",
    "direction": "down",
    "amount": 1000
})
```

#### Timing Patterns

```python
interaction_timings = {
    "click": {
        "pre_delay": (100, 300),    # Before click
        "post_delay": (200, 500),   # After click
        "hover_time": (50, 150)     # Hover duration
    },
    "type": {
        "keystroke_delay": (50, 150)  # Between keystrokes
    }
    # ... more patterns
}
```

### 3. Performance Analyzer (`src/python/core/performance_analyzer.py`)

**Purpose**: Measures INP and correlates performance issues with specific elements.

#### Key Features

- **Real-Time INP Measurement**: Uses Performance Observer API
- **Element Correlation**: Links performance data to DOM elements
- **Core Web Vitals**: INP, CLS, LCP measurement and classification
- **JavaScript Blocking Assessment**: Identifies script execution bottlenecks

#### Measurement Process

```python
# Start performance tracing
await analyzer.start_trace()

# Execute interaction
interaction_result = await interaction_engine.execute_interaction(action)

# Stop tracing and analyze
trace_data = await analyzer.stop_trace()
performance_metrics = await analyzer.analyze_trace(trace_data)

# Results include:
# - inp_score: Interaction to Next Paint in milliseconds
# - classification: "good", "needs_improvement", "poor"
# - element_correlation: Links to specific DOM elements
```

#### Performance Thresholds

```python
thresholds = {
    "inp": {
        "good": 200,                    # < 200ms is good
        "needs_improvement": 500,       # 200-500ms needs improvement
        # > 500ms is poor
    },
    "cls": {
        "good": 0.1,                   # < 0.1 is good
        "needs_improvement": 0.25,     # 0.1-0.25 needs improvement
    }
}
```

### 4. LLM Integration

#### Local LLM Client (`src/python/interfaces/llm_client.py`)

**Purpose**: Interfaces with local LLM agents (Ollama, Llama2) for development.

```python
# Configuration
llm_config = {
    "url": "http://localhost:11434",
    "model": "llama2",
    "temperature": 0.3,
    "max_tokens": 1000
}

# Usage
action = await llm_client.get_next_action({
    "available_elements": elements,
    "page_info": page_info,
    "previous_interactions": history,
    "goal": "Find elements causing high INP scores"
})
```

#### AWS Bedrock Client (`src/python/interfaces/bedrock_client.py`)

**Purpose**: Production LLM interface using AWS Bedrock Claude models.

##### Model Options

| Model | Cost | Speed | Accuracy | Use Case |
|-------|------|-------|----------|----------|
| Claude 3 Haiku | Lowest | Fast | Good | Production, frequent analysis |
| Claude 3 Sonnet | Medium | Medium | High | Complex sites, detailed analysis |
| Claude Instant | Lowest | Fastest | Basic | High-volume, basic analysis |

##### Configuration

```python
# AWS Bedrock configuration
bedrock_config = {
    "provider": "bedrock",
    "model": "anthropic.claude-3-haiku-20240307-v1:0",
    "region": "us-east-1",
    "temperature": 0.3
}

# Usage (same interface as local LLM)
action = await bedrock_client.get_next_action(context)
```

##### Prompt Engineering

```python
def _build_action_prompt(self, context):
    """
    Builds comprehensive prompt including:
    - Current page context
    - Available elements with INP potential scores
    - Previous interaction history
    - Performance optimization goals
    - Structured JSON response format
    """
    # Implementation optimized for Claude models
```

### 5. Main Orchestrator (`src/python/core/orchestrator.py`)

**Purpose**: Coordinates all components in the Observe-Reason-Act cycle.

#### Main Analysis Loop

```python
async def analyze_page(self, url: str, max_interactions: int = 10):
    """
    1. Initial page load and baseline measurement
    2. Observe-Reason-Act cycle:
       - Discover interactive elements
       - Use LLM to select next action
       - Execute realistic interaction
       - Measure performance impact
    3. Generate comprehensive results
    """
    # Detailed implementation in source code
```

#### Session Management

```python
# Each analysis creates a unique session
session_id = f"session_{int(time.time())}"

results = {
    "url": url,
    "session_id": session_id,
    "interactions": [],
    "performance_data": [],
    "worst_inp": None,
    "worst_element": None
}
```

### 6. Chrome DevTools MCP Client (`src/python/interfaces/mcp_client.py`)

**Purpose**: Interfaces with Chrome DevTools MCP server for browser automation.

#### Key Operations

```python
# Navigation
await mcp_client.navigate_page("https://example.com")

# Element interactions
await mcp_client.click_element(".button")
await mcp_client.hover_element(".dropdown")
await mcp_client.type_text("#input", "text")

# Performance measurement
await mcp_client.start_performance_trace()
trace_data = await mcp_client.stop_performance_trace()

# Page analysis
screenshot = await mcp_client.take_screenshot()
console_logs = await mcp_client.get_console_messages()
```

#### Server Management

```python
# Automatic server lifecycle management
await mcp_client.initialize()  # Starts MCP server process
# ... use client ...
await mcp_client.cleanup()     # Stops server process
```

### 7. Data Export System (`src/python/utils/data_export.py`)

**Purpose**: Generates comprehensive reports in multiple formats.

#### Supported Formats

- **JSON**: Complete data for programmatic analysis
- **CSV**: Tabular data for spreadsheet analysis
- **HTML**: Visual reports with color-coded metrics
- **Summary**: Key insights and actionable recommendations

#### Example Report Structure

```json
{
    "metadata": {
        "export_timestamp": 1699123456,
        "tool_version": "1.0.0"
    },
    "results": {
        "https://example.com": {
            "total_interactions": 8,
            "worst_inp": 847,
            "worst_element": ".dropdown-toggle:nth-of-type(1)",
            "interactions": [
                {
                    "interaction_num": 1,
                    "action": {
                        "action": "click",
                        "selector": ".dropdown-toggle"
                    },
                    "performance": {
                        "inp_score": 847,
                        "classification": "poor"
                    }
                }
            ]
        }
    }
}
```

## 🚀 Deployment Options

### Option 1: Local Development

#### Quick Start

```bash
# Setup and start all services
./scripts/start.sh

# Run analysis
inputer -u https://example.com
```

#### Docker Compose

```bash
# Multi-service deployment
docker-compose up --build

# Services included:
# - Inputer Performance Monitor
# - Ollama LLM Agent
# - Prometheus Monitoring
# - Grafana Dashboards
```

#### Services Overview

```yaml
# docker-compose.yml excerpt
services:
  inputer-monitor:
    build: .
    ports: ["8000:8000", "3001:3001"]
    depends_on: [ollama]

  ollama:
    image: ollama/ollama:latest
    ports: ["11434:11434"]

  prometheus:
    image: prom/prometheus:latest
    ports: ["9091:9090"]

  grafana:
    image: grafana/grafana:latest
    ports: ["3000:3000"]
```

### Option 2: AWS Production Deployment

#### One-Command Deployment

```bash
# Deploy entire infrastructure to AWS
./scripts/deploy-aws.sh

# Prompts for:
# - VPC ID
# - Subnet IDs
# - Environment (dev/staging/prod)
```

#### AWS Architecture Components

```yaml
# CloudFormation resources
Resources:
  - ECS Cluster (Fargate + Spot pricing)
  - Application Load Balancer
  - ECS Service with auto-scaling
  - Lambda function for scheduled analysis
  - S3 bucket for results storage
  - CloudWatch dashboards and alarms
  - IAM roles with least privilege
  - ECR repository for container images
```

#### Cost Optimization Features

1. **Fargate Spot**: 80% spot instances for 70% cost reduction
2. **Claude Haiku**: Most cost-effective Bedrock model
3. **S3 Lifecycle**: Automatic data deletion after 30 days
4. **Auto-scaling**: Scale down during low usage periods

#### Monitoring Integration

- **CloudWatch Metrics**: Custom INP performance metrics
- **Log Aggregation**: Structured JSON logs
- **Alerting**: INP score thresholds and error rates
- **Dashboards**: Real-time performance visualization

## ⚙️ Configuration

### Environment Variables

```bash
# Application
APP_NAME=inputer-performance-monitor
ENVIRONMENT=prod
HOST=0.0.0.0
PORT=8000

# Chrome Configuration
CHROME_HEADLESS=true
CHROME_DISABLE_GPU=true
CHROME_NO_SANDBOX=true
CHROME_EXECUTABLE_PATH=/usr/bin/chromium

# Performance Settings
MAX_INTERACTIONS_PER_PAGE=10
INTERACTION_DELAY_MIN=500
INTERACTION_DELAY_MAX=2000
PAGE_LOAD_TIMEOUT=30000

# LLM Configuration (Local)
LLM_AGENT_URL=http://localhost:11434
LLM_MODEL=llama2
LLM_TEMPERATURE=0.3

# LLM Configuration (AWS Bedrock)
LLM_PROVIDER=bedrock
LLM_MODEL=anthropic.claude-3-haiku-20240307-v1:0

# Storage
DATA_OUTPUT_DIR=./data
REPORT_FORMAT=json,csv,html
RESULTS_BUCKET=inputer-results-prod-123456789012

# Monitoring
LOG_LEVEL=INFO
LOG_FORMAT=json
ENABLE_METRICS=true
METRICS_PORT=9090
```

### Configuration Files

#### Local Configuration (`config/config.yaml`)

```yaml
app:
  name: "inputer-performance-monitor"
  version: "1.0.0"
  host: "localhost"
  port: 8000

mcp_server:
  port: 3001
  headless: true
  disable_gpu: true

llm_agent:
  url: "http://localhost:11434"
  model: "llama2"
  temperature: 0.3

performance:
  max_interactions_per_page: 10
  interaction_delay_min: 500
  interaction_delay_max: 2000
  screenshot_capture: true

data:
  output_dir: "./data"
  report_formats: ["json", "csv", "html"]
```

#### AWS Configuration (`config/aws.yaml`)

```yaml
app:
  name: "inputer-performance-monitor"
  host: "0.0.0.0"
  port: 8000

mcp_server:
  executable_path: "/usr/bin/chromium"  # Amazon Linux
  headless: true
  disable_gpu: true
  no_sandbox: true

llm_agent:
  provider: "bedrock"
  url: "https://bedrock-runtime.{region}.amazonaws.com"
  model: "anthropic.claude-3-haiku-20240307-v1:0"

data:
  storage_backend: "s3"
  s3_bucket: "${RESULTS_BUCKET}"

aws:
  bedrock:
    region: "${AWS_DEFAULT_REGION}"
    models:
      primary: "anthropic.claude-3-haiku-20240307-v1:0"
      fallback: "anthropic.claude-instant-v1"

  cloudwatch:
    namespace: "Inputer/Performance"
    log_group: "/ecs/inputer"

monitoring:
  enable_xray: true
  custom_metrics:
    - name: "inp_score"
      type: "histogram"
    - name: "interactions_total"
      type: "counter"
```

## 📖 Usage Examples

### Basic Analysis

```bash
# Single URL analysis
inputer --urls https://example.com

# Multiple URLs
inputer \
  --urls https://example.com \
  --urls https://example.com/products \
  --max-interactions 15 \
  --output-dir ./results \
  --verbose
```

### Advanced Configuration

```bash
# Using custom configuration file
inputer \
  --urls https://app.example.com/dashboard \
  --config-file config/production.yaml \
  --max-interactions 20 \
  --output-dir ./reports

# Docker deployment
docker-compose up -d
docker-compose exec inputer-monitor \
  inputer --urls https://example.com
```

### AWS Lambda Triggers

```bash
# Manual analysis via Lambda
aws lambda invoke --function-name inputer-scheduled-prod \
  --payload '{
    "urls": ["https://example.com", "https://app.example.com"],
    "subnets": ["subnet-xxx", "subnet-yyy"],
    "max_interactions": 15
  }' response.json

# Scheduled analysis (automatically via EventBridge)
# Runs every Monday at 9 AM UTC
```

### Programmatic Usage

```python
from src.python.main import main_automation_loop
from src.python.core.orchestrator import PerformanceOrchestrator
from src.python.config.settings import Settings

# Initialize
settings = Settings()
orchestrator = PerformanceOrchestrator(settings)
await orchestrator.initialize()

# Run analysis
results = await main_automation_loop(
    orchestrator=orchestrator,
    target_urls=["https://example.com"],
    max_interactions=10
)

# Process results
for url, result in results.items():
    print(f"URL: {url}")
    print(f"Worst INP: {result.get('worst_inp')}ms")
    print(f"Total Interactions: {result.get('total_interactions')}")
```

## 🔍 API Reference

### Core Classes

#### PerformanceOrchestrator

```python
class PerformanceOrchestrator:
    async def initialize(self) -> None:
        """Initialize all components and start services."""

    async def analyze_page(self, url: str, max_interactions: int = 10) -> Dict[str, Any]:
        """Analyze a single page for INP issues."""

    async def generate_final_report(self, results: Dict[str, Any], output_dir: str) -> Path:
        """Generate and export final report."""

    async def cleanup(self) -> None:
        """Clean up resources and shut down services."""
```

#### ElementDiscoveryEngine

```python
class ElementDiscoveryEngine:
    async def discover_interactive_elements(self) -> List[Dict[str, Any]]:
        """Discover interactive elements on the current page."""

    def _calculate_inp_potential(self, element: Dict[str, Any]) -> float:
        """Calculate how likely an element is to cause INP issues."""
```

#### UserInteractionEngine

```python
class UserInteractionEngine:
    async def execute_interaction(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a user interaction with realistic timing."""

    async def wait_for_page_stability(self, timeout: int = 5) -> bool:
        """Wait for page to become stable after interactions."""
```

#### PerformanceAnalyzer

```python
class PerformanceAnalyzer:
    async def start_trace(self) -> Dict[str, Any]:
        """Start performance tracing."""

    async def stop_trace(self) -> Dict[str, Any]:
        """Stop tracing and get trace data."""

    async def analyze_trace(self, trace_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze trace data to extract performance metrics."""
```

### Data Structures

#### Element Descriptor

```python
{
    "selector": "button.dropdown-toggle:nth-of-type(1)",
    "tag": "button",
    "type": "button",
    "text": "Select Option",
    "visible": True,
    "position": {"x": 100, "y": 200, "width": 120, "height": 40},
    "inp_potential_score": 4.5,
    "discovery_stage": "immediate"
}
```

#### Action Definition

```python
{
    "action": "click",  # click, hover, type, scroll, none
    "selector": ".dropdown-toggle",
    "reasoning": "High INP potential dropdown component",
    "text": "optional text for type actions",
    "amount": 500  # optional scroll amount
}
```

#### Performance Result

```python
{
    "inp_score": 847,
    "classification": "poor",  # good, needs_improvement, poor
    "cls_score": 0.15,
    "worst_entry": {
        "type": "click",
        "target": "button",
        "inputDelay": 50,
        "processingTime": 720,
        "presentationDelay": 77
    }
}
```

#### Analysis Result

```python
{
    "url": "https://example.com",
    "session_id": "session_1699123456",
    "timestamp": 1699123456,
    "total_interactions": 8,
    "worst_inp": 847,
    "worst_element": ".dropdown-toggle:nth-of-type(1)",
    "interactions": [...],
    "performance_data": [...],
    "summary": {
        "average_inp": 234,
        "success_rate": 0.875
    }
}
```

## 📊 Monitoring & Observability

### CloudWatch Integration (AWS)

#### Custom Metrics

```python
# Automatically published metrics
cloudwatch_metrics = [
    "Inputer/Performance/INPScore",
    "Inputer/Performance/InteractionCount",
    "Inputer/Performance/AnalysisDuration",
    "Inputer/Performance/ErrorRate",
    "Inputer/Performance/SuccessRate"
]
```

#### Log Structure

```json
{
    "timestamp": "2023-11-04T15:30:45Z",
    "level": "INFO",
    "component": "orchestrator",
    "session_id": "session_1699123456",
    "url": "https://example.com",
    "message": "Starting page analysis",
    "context": {
        "max_interactions": 10,
        "interaction_num": 1
    }
}
```

#### Dashboard Widgets

```yaml
Dashboard Widgets:
  - ECS Resource Utilization (CPU, Memory)
  - INP Score Distribution (Histogram)
  - Error Rate Trend (Time Series)
  - Analysis Success Rate (Gauge)
  - Recent Errors (Log Insights)
  - Cost Tracking (Bedrock API calls)
```

### Prometheus Metrics (Docker)

```python
# Exposed metrics at /metrics
prometheus_metrics = [
    "inputer_inp_score_histogram",
    "inputer_interactions_total_counter",
    "inputer_analysis_duration_histogram",
    "inputer_errors_total_counter",
    "inputer_page_load_duration_histogram"
]
```

### Health Checks

```python
# Health check endpoint
GET /health
{
    "status": "healthy",
    "timestamp": "2023-11-04T15:30:45Z",
    "services": {
        "mcp_server": "healthy",
        "llm_agent": "healthy",
        "chrome": "healthy"
    },
    "version": "1.0.0"
}
```

## 🔧 Troubleshooting

### Common Issues

#### 1. Chrome/MCP Server Issues

**Problem**: Chrome fails to start or MCP server connection fails

```bash
# Check Chrome installation
google-chrome --version
chromium --version

# Test MCP server manually
npx chrome-devtools-mcp --port 3001 --headless

# Check process conflicts
lsof -i :3001
```

**Solution**:
```bash
# Set correct Chrome path
export CHROME_EXECUTABLE_PATH=/usr/bin/google-chrome
# or
export CHROME_EXECUTABLE_PATH=/usr/bin/chromium

# Kill conflicting processes
pkill -f chrome-devtools-mcp
```

#### 2. LLM Agent Connection Issues

**Local Ollama Problems**:
```bash
# Check Ollama status
ollama list
ollama serve

# Test connection
curl http://localhost:11434/v1/models

# Pull required model
ollama pull llama2
```

**AWS Bedrock Problems**:
```bash
# Check Bedrock access
aws bedrock list-foundation-models --region us-east-1

# Test model invocation
aws bedrock invoke-model \
  --model-id anthropic.claude-3-haiku-20240307-v1:0 \
  --body '{"anthropic_version":"bedrock-2023-05-31","max_tokens":10,"messages":[{"role":"user","content":"Hi"}]}'
```

#### 3. Performance Issues

**Slow Analysis**:
- Reduce `max_interactions_per_page`
- Increase `interaction_delay_min/max` for stability
- Disable screenshot capture
- Use faster LLM model (Claude Haiku vs Sonnet)

**High Memory Usage**:
- Enable Chrome headless mode
- Clear Chrome cache between analyses
- Limit concurrent analyses
- Increase ECS task memory (AWS)

**Network Timeouts**:
- Increase `page_load_timeout`
- Check network connectivity
- Verify security group settings (AWS)

#### 4. AWS Deployment Issues

**CloudFormation Failures**:
```bash
# Check stack events
aws cloudformation describe-stack-events \
  --stack-name inputer-performance-monitor-prod

# View failed resources
aws cloudformation describe-stack-resources \
  --stack-name inputer-performance-monitor-prod \
  --logical-resource-id <resource-id>
```

**ECS Task Failures**:
```bash
# Check service status
aws ecs describe-services \
  --cluster inputer-prod \
  --services inputer-prod

# View stopped tasks
aws ecs list-tasks \
  --cluster inputer-prod \
  --desired-status STOPPED

# Get task logs
aws logs tail /ecs/inputer-prod --follow
```

### Debug Mode

#### Enable Verbose Logging

```bash
# Local
inputer --verbose --urls https://example.com

# Docker
docker-compose exec inputer-monitor \
  inputer --verbose --urls https://example.com

# AWS (update environment variable)
LOG_LEVEL=DEBUG
```

#### Debug Configuration

```yaml
# config/debug.yaml
logging:
  level: "DEBUG"
  format: "text"  # More readable than JSON

performance:
  screenshot_capture: true  # Capture screenshots for debugging
  interaction_delay_min: 1000  # Slower for observation
  max_interactions_per_page: 3  # Fewer interactions for testing
```

### Performance Optimization

#### Memory Optimization

```yaml
# docker-compose.yml
services:
  inputer-monitor:
    deploy:
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 1G
```

#### Chrome Optimization

```python
# Additional Chrome flags for performance
chrome_args = [
    "--headless",
    "--disable-gpu",
    "--no-sandbox",
    "--disable-dev-shm-usage",  # Reduce memory usage
    "--disable-extensions",
    "--disable-plugins",
    "--disable-images",         # Skip images for faster loading
    "--disable-javascript",     # Only if JS analysis not needed
]
```

## 👨‍💻 Development Guide

### Project Structure

```
inputer/
├── src/python/                 # Core Python application
│   ├── main.py                # Entry point & CLI interface
│   ├── core/                  # Core business logic
│   │   ├── orchestrator.py    # Main coordination engine
│   │   ├── element_discovery.py  # Element discovery algorithms
│   │   ├── interaction_engine.py # User interaction simulation
│   │   └── performance_analyzer.py # Performance measurement
│   ├── interfaces/            # External service interfaces
│   │   ├── mcp_client.py      # Chrome DevTools MCP client
│   │   ├── llm_client.py      # Local LLM client (Ollama)
│   │   └── bedrock_client.py  # AWS Bedrock client (Claude)
│   ├── config/               # Configuration management
│   │   └── settings.py       # Pydantic-based settings
│   └── utils/                # Utilities and helpers
│       ├── logger.py         # Structured logging
│       └── data_export.py    # Multi-format reporting
├── config/                   # Configuration files
│   ├── config.yaml          # Local development config
│   └── aws.yaml             # AWS production config
├── docs/                    # Documentation
│   ├── deployment/          # Deployment configurations
│   │   └── aws/             # AWS CloudFormation templates
│   ├── AWS-DEPLOYMENT.md    # AWS deployment guide
│   └── docs.md              # Complete documentation (this file)
├── scripts/                 # Utility scripts
│   ├── start.sh             # Local setup script
│   └── deploy-aws.sh        # AWS deployment script
├── tests/                   # Test suites
├── docker-compose.yml       # Multi-service local deployment
├── Dockerfile              # Container configuration
├── requirements.txt        # Python dependencies
└── package.json            # Node.js dependencies (MCP server)
```

### Development Setup

#### Prerequisites

```bash
# Python 3.13+
python --version

# Node.js 18+
node --version

# Docker and Docker Compose
docker --version
docker-compose --version

# Chrome/Chromium
google-chrome --version
```

#### Local Environment

```bash
# Clone repository
git clone <repository-url>
cd inputer

# Run setup script
./scripts/start.sh

# Or manual setup:
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
source .venv/bin/activate
uv pip install -e .

# Create .env file
cp .env.example .env
# Edit .env with your configuration
```

#### Development Dependencies

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Development tools include:
# - pytest (testing)
# - black (code formatting)
# - flake8 (linting)
# - mypy (type checking)
# - pre-commit (git hooks)
```

### Code Style and Standards

#### Python Code Style

```bash
# Format code
black src/python/

# Lint code
flake8 src/python/

# Type check
mypy src/python/

# Run all checks
pre-commit run --all-files
```

#### Key Principles

1. **Under 500 lines per file**: Keep modules focused and maintainable
2. **Type hints**: Use Python type annotations
3. **Error handling**: Comprehensive try/catch with logging
4. **Async/await**: Use async patterns for I/O operations
5. **Structured logging**: Use structlog for contextual logging

### Testing

#### Test Structure

```
tests/
├── unit/                    # Unit tests
│   ├── test_element_discovery.py
│   ├── test_interaction_engine.py
│   ├── test_performance_analyzer.py
│   └── test_orchestrator.py
├── integration/             # Integration tests
│   ├── test_mcp_integration.py
│   ├── test_llm_integration.py
│   └── test_end_to_end.py
└── fixtures/                # Test fixtures and mock data
    ├── sample_pages/
    └── mock_responses/
```

#### Running Tests

```bash
# Run all tests
pytest

# Run specific test suite
pytest tests/unit/

# Run with coverage
pytest --cov=src/python/

# Run integration tests (requires services)
docker-compose up -d
pytest tests/integration/
```

#### Example Test

```python
# tests/unit/test_element_discovery.py
import pytest
from src.python.core.element_discovery import ElementDiscoveryEngine

@pytest.mark.asyncio
async def test_element_discovery():
    """Test element discovery functionality."""
    # Mock MCP client
    mock_mcp = MockMCPClient()

    # Initialize discovery engine
    engine = ElementDiscoveryEngine(mock_mcp, settings)

    # Test discovery
    elements = await engine.discover_interactive_elements()

    # Assertions
    assert len(elements) > 0
    assert all('selector' in element for element in elements)
    assert all('inp_potential_score' in element for element in elements)
```

### Contributing

#### Development Workflow

1. **Fork repository**: Create your own fork
2. **Create branch**: `git checkout -b feature/amazing-feature`
3. **Make changes**: Follow code style guidelines
4. **Add tests**: Ensure good test coverage
5. **Run tests**: `pytest` and `pre-commit run --all-files`
6. **Commit changes**: `git commit -m 'Add amazing feature'`
7. **Push branch**: `git push origin feature/amazing-feature`
8. **Create PR**: Open a Pull Request with description

#### Code Review Checklist

- [ ] Code follows style guidelines (black, flake8, mypy)
- [ ] Changes are covered by tests
- [ ] All tests pass
- [ ] Documentation is updated
- [ ] No secrets or credentials in code
- [ ] Performance impact considered
- [ ] Error handling is comprehensive

### Architecture Decisions

#### Why These Technologies?

**Python**:
- Rich ecosystem for web automation and AI
- Excellent async support for I/O operations
- Strong typing support with mypy

**Chrome DevTools MCP**:
- Direct access to Chrome Performance API
- Real-time performance measurement
- Standard protocol for browser automation

**LLM Integration**:
- Local (Ollama): Development flexibility and privacy
- AWS Bedrock: Production scalability and reliability
- Structured prompting for reliable decision making

**Multi-format Reporting**:
- JSON: Programmatic analysis and integration
- CSV: Spreadsheet analysis and data science
- HTML: Human-readable reports for stakeholders

#### Design Patterns

**Observer Pattern**: Element discovery with event-driven updates
**Strategy Pattern**: LLM client switching (Local vs Bedrock)
**Factory Pattern**: Configuration-based component creation
**Async/Await**: Non-blocking I/O for performance
**Dependency Injection**: Testable component architecture

### Performance Considerations

#### Bottlenecks and Optimizations

1. **Chrome Startup Time**:
   - Solution: Reuse browser instances
   - Implementation: Connection pooling in MCP client

2. **LLM Response Time**:
   - Solution: Model selection based on use case
   - Implementation: Haiku for speed, Sonnet for accuracy

3. **Element Discovery**:
   - Solution: Multi-stage discovery with caching
   - Implementation: Progressive element scoring

4. **Network I/O**:
   - Solution: Async operations and timeouts
   - Implementation: httpx with connection limits

#### Memory Management

```python
# Explicit cleanup patterns
try:
    await orchestrator.initialize()
    results = await orchestrator.analyze_page(url)
finally:
    await orchestrator.cleanup()  # Always cleanup resources
```

#### Scalability Patterns

**Horizontal Scaling**: Multiple ECS tasks for parallel analysis
**Vertical Scaling**: Configurable CPU/memory based on workload
**Cost Optimization**: Spot instances and intelligent model selection
**Resource Isolation**: Container-based deployment with limits

This documentation provides a comprehensive guide to understanding, deploying, and extending the Inputer Performance Monitor system. For the latest updates and examples, refer to the source code and configuration files in the repository.