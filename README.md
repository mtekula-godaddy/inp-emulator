# INP Emulator

A browser automation tool for finding likely INP culprits.

## What it does

INP (Interaction to Next Paint) is a Core Web Vitals metric that measures how quickly a page responds to user interactions. High INP scores indicate poor user experience and can negatively impact Google search rankings. Existing tools like Lighthouse do not simulate actual user behavior, making INP issues difficult to identify.

INP Emulator finds interactive elements on web pages, clicks/taps them, measures INP, and reports which elements cause delays. It applies a coefficient to estimate real-world INP from automation measurements (typical range: 2.5-4.0x based on page complexity).

Core capabilities:
- Finds interactive elements during page rendering (buttons, links, accordions, expandable lists)
- Simulates user interactions with touch events (mobile) or mouse events (desktop)
- Measures INP and estimates real-world performance (targets: US users ~350ms, distant countries ~650ms)
- Prioritizes elements by user behavior patterns (position-dominant scoring)
- Uses human-readable labels instead of technical selectors in reports
- Detects visual outcomes (CSS class changes, DOM mutations, visibility changes)
- Exports results to JSON, CSV, and HTML
- Supports mobile emulation (Pixel 5) and network throttling (4G/3G)

## How it works

1. Loads a page in Playwright-controlled browser (emulating a smartphone viewport)
2. Discovers interactive elements (buttons, links, dropdowns, form controls, carousels, tabs, expandable lists)
3. Filters out navigation, footer, share buttons, disclaimers, and account links
4. Scores elements by likelihood to cause INP issues based on user behavior:
   - **Position is dominant**: Above-the-fold elements score highest
   - Elements 2-3 scrolls down (Y < 3000px) are not penalized
   - Mid-page elements (Y < 5000px) get reduced priority (50% score)
   - Deep page elements (Y > 5000px) are heavily penalized (10% score)
   - Element size (larger, more prominent CTAs score higher)
   - Primary action indicators ("See Plans", "Buy Now", "Get Started")
   - Secondary CTAs ("Learn More", "Read More") are kept separate from primary CTAs
   - De-prioritizes utility buttons (tooltips, help, close)
5. Deduplicates similar elements while preserving CTA variety (keeps top scorer from each category)
6. Interacts with elements in priority order
7. Measures INP for each interaction
8. Captures before/after screenshots with element labels
9. Exports results showing which elements caused the worst INP scores

Element filtering excludes navigation, footer, social buttons, disclaimers, legal links, and account links by default. Use `--include-header` to test navigation/header elements.

Detection methods:
- DOM mutations
- CSS class changes on html/body
- Element visibility changes
- Text content appearance

## Setup

Requirements:
- Python 3.13+
- Google Chrome (system install — the tool launches it via CDP to avoid bot detection)

Installation:
```bash
git clone <repository-url>
cd inp-emulator
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
source .venv/bin/activate
uv pip install -e .
cp .env.example .env
```

## Usage

Basic command:
```bash
inp-emulator-test https://example.com
```

Test 5 elements instead of default 3:
```bash
inp-emulator-test https://example.com 5
```

Include navigation/header elements:
```bash
inp-emulator-test https://example.com --include-header
```

Test multiple URLs from a file:
```bash
inp-emulator-test urls.txt
```

## Output

Results are saved to `./test_results/` in three formats:

- **JSON** - Full data for programmatic analysis
- **CSV** - Spreadsheet-compatible format
- **HTML** - Visual report

INP classifications (based on estimated real-world performance):
- Good: < 200ms
- Needs Improvement: 200-500ms
- Poor: > 500ms

Reports show both measured automation values and estimated real-world INP using a coefficient (base: 2.5x, adjusted for page complexity).

Example terminal output:
```
Test Results Summary
URLs Tested: 1/1
Total Interactions: 3
Worst INP: 847ms on 'See Plans and Pricing'

Report saved to: test_results/inp_emulator_report_20251022_110833.json
```

Screenshots saved to `data/screenshots/{session_id}/` with before/after state for each interaction.

Debug logging shows:
- Elements discovered and filtered
- Top 10 scored elements available for testing
- Coefficient calculation breakdown (base + JS size + frameworks + third-party + long tasks)

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

Chrome not found:
```bash
# The tool auto-detects Chrome on macOS, Linux, and Windows.
# If it can't find it, set the path explicitly:
export CHROME_EXECUTABLE_PATH=/path/to/chrome
```

Enable debug output:
```bash
python src/inp_emulator/main.py --verbose -u https://example.com
```