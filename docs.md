# Inputer - Technical Documentation

## Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Core Components](#core-components)
- [Configuration](#configuration)
- [Usage Examples](#usage-examples)
- [API Reference](#api-reference)
- [Troubleshooting](#troubleshooting)
- [Development](#development)

## Overview

Inputer is a browser automation tool for identifying DOM elements that cause high INP (Interaction to Next Paint) scores.

INP is a Core Web Vitals metric. High INP indicates slow response to user interactions, which degrades user experience and can hurt Google search rankings. Tools like Lighthouse do not simulate actual user behavior, making INP issues hard to identify.

Inputer uses Playwright to:
1. Load pages
2. Find interactive elements
3. Simulate user interactions
4. Measure INP for each interaction
5. Report which elements caused the highest INP scores

Use cases:
- Pre-deployment performance testing
- CI/CD performance regression testing
- Production monitoring
- INP optimization

## Architecture

Components:
- Python orchestrator (`src/inputer/`)
- Playwright browser automation
- Element discovery engine
- Interaction simulator
- Performance measurement
- Data exporter

Process:
1. Element discovery finds interactive elements
2. Elements are scored by INP potential
3. Interactions are executed in priority order
4. Performance is measured for each interaction
5. Results are exported to JSON/CSV/HTML

## Core Components

### Element Discovery Engine

File: `src/inputer/core/element_discovery.py`

Finds interactive elements on pages:
- Buttons, links, dropdowns, form controls, carousels, tabs
- Filters out navigation, footer, and social/share buttons
- Generates validated CSS selectors
- Scores elements by INP potential

Discovery stages:
1. Immediate elements (visible on load)
2. Dynamic elements (appear after load)
3. Lazy-loaded elements (triggered by scrolling)

INP potential scoring factors:
- Element type (dropdown: 4.0, button: 3.0, link: 1.0)
- Complex class names (+1.5 each)
- Data attributes (+1.0)
- JavaScript event indicators (+1.0)
- Discovery stage (dynamic: +2.0, lazy: +1.5)

Example usage:
```python
from core.element_discovery import ElementDiscoveryEngine

engine = ElementDiscoveryEngine(mcp_client, settings)
elements = await engine.discover_interactive_elements()
# Returns list of elements with selectors and INP potential scores
```

### Interaction Engine

File: `src/inputer/core/interaction_engine.py`

Simulates user interactions with variable timing:
- Mobile: touch events (tap)
- Desktop: mouse events (hover + click)
- Variable delays to mimic human behavior
- Waits for page stability after interactions

Supported actions:
- Click (with hover on desktop)
- Type (with keystroke delays)
- Scroll

Timing:
- Click: 100-300ms pre-delay, 200-500ms post-delay
- Hover: 50-150ms duration
- Keystroke: 50-150ms between keys

### Performance Analyzer

File: `src/inputer/core/performance_analyzer.py`

Measures INP using Playwright's Performance Observer API. Captures INP before and after each interaction, correlates scores with specific elements.

Thresholds:
- Good: < 200ms
- Needs Improvement: 200-500ms
- Poor: > 500ms

Also measures CLS (Cumulative Layout Shift):
- Good: < 0.1
- Needs Improvement: 0.1-0.25
- Poor: > 0.25

### Data Exporter

File: `src/inputer/utils/data_export.py`

Exports results to:
- JSON - Complete data
- CSV - Spreadsheet format
- HTML - Visual report

Reports include:
- URL tested
- Total interactions
- Worst INP score
- Element that caused worst INP
- Per-interaction details (action, selector, INP score, classification)
- Screenshots paths

### Orchestrator

File: `src/inputer/core/orchestrator.py`

Coordinates the analysis process:
1. Load page
2. Discover elements
3. Score and prioritize elements
4. Execute interactions
5. Measure performance
6. Generate reports

Each analysis creates a session with unique ID. Results track all interactions and identify worst INP scores.

## Configuration

Key environment variables in `.env`:

```bash
# Browser
CHROME_HEADLESS=false  # false reduces bot detection
CHROME_EXECUTABLE_PATH=/usr/bin/chromium
MOBILE_EMULATION=true  # Pixel 5 emulation
NETWORK_THROTTLING=None  # Options: None, "Fast 4G", "Slow 4G", "Fast 3G"

# Testing
MAX_INTERACTIONS_PER_PAGE=10
INTERACTION_DELAY_MIN=500
INTERACTION_DELAY_MAX=2000
SCREENSHOT_CAPTURE=true

# Output
DATA_OUTPUT_DIR=./data
REPORT_FORMAT=json,csv,html
```

Local config file: `config/config.yaml`

## Usage Examples

Basic:
```bash
PYTHONPATH=$(pwd)/src python3 src/inputer/testing/test_runner.py https://example.com element_scan priority
```

Test 10 elements:
```bash
PYTHONPATH=$(pwd)/src python3 src/inputer/testing/test_runner.py https://example.com element_scan priority 10
```

Multiple URLs from file:
```bash
PYTHONPATH=$(pwd)/src python3 src/inputer/testing/test_runner.py urls.txt element_scan priority
```

Include navigation elements:
```bash
PYTHONPATH=$(pwd)/src python3 src/inputer/testing/test_runner.py https://example.com element_scan priority --include-header
```

## API Reference

### Element Data Structure

```python
{
    "selector": "button.dropdown-toggle:nth-of-type(1)",
    "tag": "button",
    "type": "button",
    "text": "Select Option",
    "visible": True,
    "inp_potential_score": 4.5,
    "discovery_stage": "immediate"  # immediate, dynamic, or lazy
}
```

### Result Data Structure

```python
{
    "url": "https://example.com",
    "session_id": "session_1699123456",
    "total_interactions": 8,
    "worst_inp": 847,
    "worst_element": ".dropdown-toggle:nth-of-type(1)",
    "interactions": [
        {
            "interaction_num": 1,
            "action": "click",
            "selector": ".dropdown",
            "inp_score": 847,
            "classification": "poor"
        }
    ]
}
```

## Troubleshooting

Chrome fails to start:
```bash
google-chrome --version
export CHROME_EXECUTABLE_PATH=/usr/bin/chromium
```

Enable debug logging:
```bash
python src/inputer/main.py --verbose -u https://example.com
```

Memory issues:
- Enable headless mode: `CHROME_HEADLESS=true`
- Reduce max interactions
- Disable screenshots: `SCREENSHOT_CAPTURE=false`

Timeout issues:
- Increase `PAGE_LOAD_TIMEOUT` in config
- Check network connectivity
- Disable network throttling

## Development

Project structure:
```
inputer/
├── src/inputer/
│   ├── core/               # Element discovery, interaction, performance analysis
│   ├── config/             # Settings management
│   ├── testing/            # Test runner
│   └── utils/              # Data export, logging
├── config/                 # Configuration files
├── tests/                  # Unit and integration tests
└── data/                   # Output directory
```

Setup:
```bash
git clone <repository-url>
cd inputer
./scripts/start.sh
```

Run tests:
```bash
pytest tests/unit/
pytest tests/integration/
pytest --cov=src/inputer/
```

Code style:
```bash
black src/inputer/
ruff check src/inputer/
mypy src/inputer/
```