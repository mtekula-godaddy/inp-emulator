# Inputer

A browser automation tool for finding likely INP culprits.

## What it does

INP (Interaction to Next Paint) is a Core Web Vitals metric that measures how quickly a page responds to user interactions. High INP scores indicate poor user experience and can negatively impact Google search rankings. Existing tools like Lighthouse do not simulate actual user behavior, making INP issues difficult to identify.

Inputer finds interactive elements on web pages, clicks/taps them, measures INP, and reports which elements cause delays.

Core capabilities:
- Finds interactive elements during page rendering
- Simulates user interactions with touch events (mobile) or mouse events (desktop)
- Measures INP and correlates scores with specific DOM elements
- Detects visual outcomes (CSS class changes, DOM mutations, visibility changes)
- Exports results to JSON, CSV, and HTML
- Supports mobile emulation (Pixel 5) and network throttling (4G/3G)

## How it works

1. Loads a page in Playwright-controlled browser
2. Discovers interactive elements (buttons, links, dropdowns, form controls, carousels, tabs)
3. Filters out navigation, footer, and share buttons
4. Scores elements by likelihood to cause INP issues
5. Interacts with elements in priority order
6. Measures INP for each interaction
7. Captures before/after screenshots
8. Exports results showing which elements caused the worst INP scores

Element filtering excludes navigation/footer/social buttons by default. Use `--include-header` to test these elements.

Detection methods:
- DOM mutations
- CSS class changes on html/body
- Element visibility changes
- Text content appearance

## Setup

Requirements:
- Python 3.13+
- Chrome or Chromium

Installation:
```bash
git clone <repository-url>
cd inputer
./scripts/start.sh
```

Or manually:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
source .venv/bin/activate
uv pip install -e .
cp .env.example .env
```

## Usage

Basic command:
```bash
PYTHONPATH=$(pwd)/src python3 src/inputer/testing/test_runner.py https://example.com element_scan priority
```

Test 5 elements instead of default 2:
```bash
PYTHONPATH=$(pwd)/src python3 src/inputer/testing/test_runner.py https://example.com element_scan priority 5
```

Include navigation/header elements:
```bash
PYTHONPATH=$(pwd)/src python3 src/inputer/testing/test_runner.py https://example.com element_scan priority --include-header
```

Test multiple URLs from a file:
```bash
PYTHONPATH=$(pwd)/src python3 src/inputer/testing/test_runner.py urls.txt element_scan priority
```

Selection strategies:
- `priority` - Tests elements scored most likely to cause INP issues
- `sequential` - Tests elements in discovery order
- `random` - Random element selection
- `problematic` - Focuses on dropdowns, modals, carousels

## Output

Results are saved to `./test_results/` in three formats:

- **JSON** - Full data for programmatic analysis
- **CSV** - Spreadsheet-compatible format
- **HTML** - Visual report

INP classifications:
- Good: < 200ms
- Needs Improvement: 200-500ms
- Poor: > 500ms

Example output:
```
Test Results Summary
Strategy: priority
URLs Tested: 1/1
Total Interactions: 8
Worst INP: 847ms on https://example.com

Report saved to: ./test_results/test_report_priority_1699123456.json
```

Screenshots saved to `data/screenshots/{session_id}/` showing before/after state for each interaction.

## Configuration

Key settings in `.env`:

```bash
CHROME_HEADLESS=false  # false helps avoid bot detection
MOBILE_EMULATION=true  # Emulate Pixel 5
NETWORK_THROTTLING=None  # Options: None, "Fast 4G", "Slow 4G", "Fast 3G"
MAX_INTERACTIONS_PER_PAGE=10
SCREENSHOT_CAPTURE=true
```

## Troubleshooting

Chrome fails to start:
```bash
google-chrome --version
export CHROME_EXECUTABLE_PATH=/usr/bin/chromium-browser
```

Enable debug output:
```bash
python src/inputer/main.py --verbose -u https://example.com
```