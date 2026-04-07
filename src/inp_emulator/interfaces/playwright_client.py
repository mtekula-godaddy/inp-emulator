"""
Playwright Client for browser automation and performance monitoring.

Launches system Chrome via CDP (Chrome DevTools Protocol) to avoid
bot detection that targets Playwright's bundled Chromium.
"""

import asyncio
import platform
import shutil
import subprocess
import tempfile
import time
from typing import Any, Dict, List, Optional
from pathlib import Path

from playwright.async_api import async_playwright, Browser, BrowserContext, Page
import structlog

from inp_emulator.config.settings import MCPServerConfig


logger = structlog.get_logger(__name__)

CDP_PORT = 9222


def _find_chrome() -> str:
    """Find the system Chrome executable."""
    system = platform.system()

    if system == "Darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    elif system == "Linux":
        candidates = [
            "google-chrome",
            "google-chrome-stable",
            "chromium",
            "chromium-browser",
        ]
    elif system == "Windows":
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
    else:
        candidates = []

    for candidate in candidates:
        if Path(candidate).is_absolute():
            if Path(candidate).exists():
                return candidate
        else:
            found = shutil.which(candidate)
            if found:
                return found

    raise RuntimeError(
        "Could not find Chrome. Install Google Chrome or set CHROME_EXECUTABLE_PATH in .env"
    )


class PlaywrightClient:
    """
    Client for browser automation using Playwright.

    Connects to system Chrome via CDP to bypass bot detection that
    fingerprints Playwright's bundled Chromium.
    """

    def __init__(self, config: MCPServerConfig):
        """Initialize the Playwright client."""
        self.config = config
        self.logger = logger.bind(component="playwright_client")

        # Playwright objects
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

        # Chrome subprocess
        self._chrome_process: Optional[subprocess.Popen] = None
        self._chrome_user_data_dir: Optional[str] = None

        # Session state
        self.current_browser_session: Optional[str] = None
        self.inp_entries: List[Dict[str, Any]] = []

        # Optional session ID and performance config for video recording
        self.session_id: Optional[str] = None
        self.performance_config: Optional[Any] = None
        self.data_dir: str = "data"  # Default to data/, can be overridden for tests

    async def initialize(self) -> None:
        """Launch system Chrome and connect via CDP."""
        self.logger.info("Initializing Playwright client")

        try:
            # Find Chrome
            chrome_path = self.config.executable_path or _find_chrome()
            self.logger.info("Using Chrome", path=chrome_path)

            # Temp profile so we don't interfere with user's browser
            self._chrome_user_data_dir = tempfile.mkdtemp(prefix="inp-emulator-")

            # Build Chrome launch args
            chrome_args = [
                chrome_path,
                f'--remote-debugging-port={CDP_PORT}',
                f'--user-data-dir={self._chrome_user_data_dir}',
                '--no-first-run',
                '--no-default-browser-check',
                '--disable-default-apps',
                '--disable-popup-blocking',
                '--disable-translate',
                '--disable-background-timer-throttling',
                '--disable-renderer-backgrounding',
                '--disable-backgrounding-occluded-windows',
            ]

            if self.config.headless:
                chrome_args.append('--headless=new')

            # Set viewport via window size
            if hasattr(self.config, 'mobile_emulation') and self.config.mobile_emulation:
                chrome_args.append(
                    f'--window-size={self.config.viewport_width},{self.config.viewport_height}'
                )

            # Launch Chrome
            self._chrome_process = subprocess.Popen(
                chrome_args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # Wait for CDP to be ready
            await self._wait_for_cdp()

            # Connect Playwright via CDP
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.connect_over_cdp(
                f'http://localhost:{CDP_PORT}'
            )

            # Get the default context created by Chrome
            contexts = self.browser.contexts
            if contexts:
                self.context = contexts[0]
            else:
                self.context = await self.browser.new_context()

            # Get or create a page
            pages = self.context.pages
            if pages:
                self.page = pages[0]
            else:
                self.page = await self.context.new_page()

            # Apply mobile emulation via CDP
            if hasattr(self.config, 'mobile_emulation') and self.config.mobile_emulation:
                cdp = await self.context.new_cdp_session(self.page)
                await cdp.send('Emulation.setDeviceMetricsOverride', {
                    'width': self.config.viewport_width,
                    'height': self.config.viewport_height,
                    'deviceScaleFactor': 1.0,
                    'mobile': True,
                })
                await cdp.send('Emulation.setTouchEmulationEnabled', {
                    'enabled': True,
                })
                await cdp.send('Emulation.setUserAgentOverride', {
                    'userAgent': self.config.user_agent,
                })

            # Set up video recording if enabled
            if (self.performance_config and
                hasattr(self.performance_config, 'video_capture') and
                self.performance_config.video_capture):
                video_dir = f"{self.data_dir}/videos/{self.session_id or 'default'}"
                Path(video_dir).mkdir(parents=True, exist_ok=True)
                self.logger.info("Video recording enabled", dir=video_dir)

            # Set up network throttling if configured
            await self._setup_network_throttling()

            # Set up INP monitoring
            await self._setup_inp_monitoring()

            self.current_browser_session = f"playwright_session_{id(self.page)}"
            self.logger.info("Playwright client initialization complete",
                           session_id=self.current_browser_session)

        except Exception as e:
            self.logger.error("Failed to initialize Playwright client", error=str(e))
            await self.cleanup()
            raise

    async def _wait_for_cdp(self, timeout: float = 10.0) -> None:
        """Wait for Chrome's CDP endpoint to become available."""
        import urllib.request
        import urllib.error

        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            try:
                req = urllib.request.urlopen(
                    f'http://localhost:{CDP_PORT}/json/version',
                    timeout=2
                )
                if req.status == 200:
                    return
            except (urllib.error.URLError, OSError):
                pass
            await asyncio.sleep(0.3)

        raise RuntimeError(f"Chrome CDP did not become available within {timeout}s")

    async def _setup_inp_monitoring(self) -> None:
        """Set up INP (Interaction to Next Paint) monitoring.

        INP measures the time from user interaction (pointerdown/touchstart) to when
        the browser presents the next visual frame. This includes:
        - Input delay: Time to start processing
        - Processing time: Event handler execution
        - Presentation delay: Time to paint
        """
        await self.page.add_init_script("""
            window.__inpEntries = [];

            if ('PerformanceObserver' in window) {
                const observer = new PerformanceObserver((list) => {
                    for (const entry of list.getEntries()) {
                        // Only capture entries with interactionId (real user interactions)
                        if (entry.interactionId) {
                            window.__inpEntries.push({
                                name: entry.name,
                                entryType: entry.entryType,
                                startTime: entry.startTime,
                                duration: entry.duration,
                                interactionId: entry.interactionId,
                                processingStart: entry.processingStart,
                                processingEnd: entry.processingEnd,
                                target: entry.target ? entry.target.tagName : 'unknown',
                                timestamp: Date.now()
                            });
                        }
                    }
                });

                try {
                    observer.observe({
                        type: 'event',
                        buffered: true,
                        durationThreshold: 0
                    });
                } catch (e) {
                    console.warn('Failed to observe event timing:', e);
                }
            }
        """)

    async def _setup_network_throttling(self) -> None:
        """Set up network throttling to simulate realistic mobile conditions."""
        if not hasattr(self.config, 'network_throttling'):
            return

        throttle_profile = self.config.network_throttling
        if not throttle_profile or throttle_profile == "None":
            return

        # Network throttling profiles (based on WebPageTest presets)
        profiles = {
            "Fast 3G": {
                "download_throughput": 1.6 * 1024 * 1024 / 8,  # 1.6 Mbps in bytes/sec
                "upload_throughput": 750 * 1024 / 8,  # 750 Kbps in bytes/sec
                "latency": 40  # 40ms RTT
            },
            "Fast 4G": {
                "download_throughput": 10 * 1024 * 1024 / 8,  # 10 Mbps
                "upload_throughput": 5 * 1024 * 1024 / 8,  # 5 Mbps
                "latency": 10  # 10ms RTT
            },
            "Slow 4G": {
                "download_throughput": 4 * 1024 * 1024 / 8,  # 4 Mbps
                "upload_throughput": 3 * 1024 * 1024 / 8,  # 3 Mbps
                "latency": 20  # 20ms RTT
            },
            "3G": {
                "download_throughput": 1.6 * 1024 * 1024 / 8,
                "upload_throughput": 768 * 1024 / 8,
                "latency": 150  # 150ms RTT
            }
        }

        if throttle_profile in profiles:
            profile = profiles[throttle_profile]
            cdp = await self.page.context.new_cdp_session(self.page)
            await cdp.send('Network.emulateNetworkConditions', {
                'offline': False,
                'downloadThroughput': profile['download_throughput'],
                'uploadThroughput': profile['upload_throughput'],
                'latency': profile['latency']
            })
            self.logger.info("Network throttling enabled", profile=throttle_profile)

    # Navigation methods
    async def navigate_page(self, url: str, **kwargs) -> Dict[str, Any]:
        """Navigate to a specific URL."""
        return await self.navigate_to_page(url, **kwargs)

    async def navigate_to_page(self, url: str, wait_until: str = 'load') -> Dict[str, Any]:
        """Navigate to a specific URL, waiting for page content to render."""
        self.logger.info("Navigating to page", url=url)

        try:
            response = await self.page.goto(url, wait_until='domcontentloaded', timeout=30000)

            # Wait for real page content to appear (handles JS challenge pages)
            # Bot protection pages serve an empty body, then redirect via JS
            try:
                await self.page.wait_for_function(
                    '() => document.title.length > 0 && document.body && document.body.innerText.trim().length > 50',
                    timeout=15000
                )
            except Exception:
                self.logger.warning("Page content did not fully render within timeout", url=url)

            self.logger.info("Page navigation complete", url=url, status=response.status if response else None)
            return {
                'url': url,
                'status': response.status if response else None,
                'success': True
            }
        except Exception as e:
            self.logger.error("Failed to navigate to page", url=url, error=str(e))
            raise

    # Screenshot methods
    async def take_screenshot(self, filename: str = None, selector: str = None) -> Optional[str]:
        """Take a screenshot of the current page or specific element."""
        try:
            if filename:
                # If relative path, store in configured data dir screenshots/
                path = Path(filename)
                if not path.is_absolute():
                    path = Path(self.data_dir) / "screenshots" / filename
            else:
                path = Path(f"{self.data_dir}/screenshots/screenshot_{id(self.page)}.png")

            path.parent.mkdir(parents=True, exist_ok=True)

            # Take element-specific screenshot if selector provided
            if selector:
                try:
                    element = await self.page.query_selector(selector)
                    if element:
                        # Get element bounding box
                        box = await element.bounding_box()
                        if box:
                            # Add padding around element for context (50px on each side)
                            padding = 50
                            clip = {
                                'x': max(0, box['x'] - padding),
                                'y': max(0, box['y'] - padding),
                                'width': box['width'] + (2 * padding),
                                'height': box['height'] + (2 * padding)
                            }
                            # Take screenshot of the clipped region with context
                            await self.page.screenshot(path=str(path), clip=clip)
                            screenshot_path = str(path.absolute())
                            self.logger.debug("Element context screenshot captured", path=screenshot_path, selector=selector)
                            return screenshot_path
                except Exception as e:
                    self.logger.warning("Failed to capture element screenshot, falling back to page", selector=selector, error=str(e))

            # Use viewport-only screenshots for mobile emulation (respects viewport size)
            # Use full_page for desktop to capture entire content
            is_mobile = hasattr(self.config, 'mobile_emulation') and self.config.mobile_emulation
            await self.page.screenshot(path=str(path), full_page=not is_mobile)

            screenshot_path = str(path.absolute())
            self.logger.debug("Screenshot captured", path=screenshot_path)
            return screenshot_path
        except Exception as e:
            self.logger.error("Failed to take screenshot", error=str(e))
            return None

    # Console methods
    async def get_page_info(self) -> Dict[str, Any]:
        """Get current page information including all elements."""
        try:
            # Get page title and URL
            title = await self.page.title()
            url = self.page.url

            # Get all interactive elements
            elements = await self.page.evaluate("""
                () => {
                    const elements = [];
                    const selectors = [
                        'button', 'a[href]', 'input', 'select', 'textarea',
                        '[role="button"]', '[role="link"]', '[role="tab"]',
                        '[onclick]', '[tabindex]'
                    ];

                    selectors.forEach(selector => {
                        document.querySelectorAll(selector).forEach((el, idx) => {
                            const rect = el.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0) {
                                elements.push({
                                    tag: el.tagName.toLowerCase(),
                                    text: (el.textContent || el.value || '').trim().substring(0, 100),
                                    selector: selector + ':nth-of-type(' + (idx + 1) + ')',
                                    visible: true,
                                    position: {
                                        x: Math.round(rect.left),
                                        y: Math.round(rect.top)
                                    }
                                });
                            }
                        });
                    });

                    return elements;
                }
            """)

            return {
                'title': title,
                'url': url,
                'elements': elements
            }
        except Exception as e:
            self.logger.error("Failed to get page info", error=str(e))
            raise

    async def take_snapshot(self) -> Dict[str, Any]:
        """Get a snapshot of all page elements (similar to chrome-devtools-mcp format)."""
        try:
            elements = await self.page.evaluate("""
                () => {
                    const elements = [];
                    const selectors = [
                        'button', 'a', 'input', 'select', 'textarea',
                        '[role="button"]', '[role="link"]', '[role="tab"]',
                        '[role="menuitem"]', '[role="checkbox"]',
                        '[tabindex="0"]', 'li[tabindex]', 'div[tabindex]'
                    ];

                    // Generate a unique CSS selector for an element
                    function generateSelector(el) {
                        // Helper to validate selector
                        function validateSelector(selector) {
                            try {
                                const found = document.querySelector(selector);
                                return found === el;
                            } catch (e) {
                                return false;
                            }
                        }

                        // Helper to check if ID looks like a UUID/hash (unstable)
                        function isUnstableId(id) {
                            // UUIDs: 8-4-4-4-12 hex format (e.g., 6ec9f987-8b25-4e2d-bdcd-fb8d47f1c885)
                            if (/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)) {
                                return true;
                            }
                            // ID prefix patterns (e.g., id-50170cd4-f828-4779-bfac-26781e4ccfca)
                            if (/^id-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)) {
                                return true;
                            }
                            // Long hex strings (likely hashes, e.g., 4b0e9d37-7d64-4304-b086-32833c192f11)
                            if (/^[0-9a-f-]{20,}$/i.test(id)) {
                                return true;
                            }
                            return false;
                        }

                        // Try data-cy or data-testid first (most stable)
                        if (el.getAttribute('data-cy')) {
                            const selector = '[data-cy="' + el.getAttribute('data-cy') + '"]';
                            if (validateSelector(selector)) return selector;
                        }
                        if (el.getAttribute('data-testid')) {
                            const selector = '[data-testid="' + el.getAttribute('data-testid') + '"]';
                            if (validateSelector(selector)) return selector;
                        }

                        // Try data-track-name (often stable)
                        if (el.getAttribute('data-track-name')) {
                            const selector = '[data-track-name="' + el.getAttribute('data-track-name') + '"]';
                            if (validateSelector(selector)) return selector;
                        }

                        // Try ID only if it looks stable (not a UUID/hash)
                        if (el.id && !isUnstableId(el.id)) {
                            const selector = '#' + CSS.escape(el.id);
                            if (validateSelector(selector)) return selector;
                        }

                        // Try class-based selector if element has unique classes
                        if (el.className && typeof el.className === 'string') {
                            const classes = el.className.trim().split(/\\s+/).filter(c => c);
                            if (classes.length > 0) {
                                const selector = el.nodeName.toLowerCase() + '.' + classes.join('.');
                                if (validateSelector(selector)) return selector;
                            }
                        }

                        // Build path with nth-of-type (more reliable than nth-child)
                        let path = [];
                        let current = el;
                        while (current && current.nodeType === Node.ELEMENT_NODE && current !== document.body) {
                            let selector = current.nodeName.toLowerCase();

                            if (current.id) {
                                selector = '#' + CSS.escape(current.id);
                                path.unshift(selector);
                                break;
                            } else {
                                // Use nth-of-type instead of nth-child
                                let sibling = current;
                                let nth = 1;
                                while (sibling = sibling.previousElementSibling) {
                                    if (sibling.nodeName === current.nodeName) nth++;
                                }

                                // Only add nth-of-type if needed (i.e., if there are siblings of same type)
                                let nextSibling = current.nextElementSibling;
                                let hasSameTypeSiblings = false;
                                while (nextSibling) {
                                    if (nextSibling.nodeName === current.nodeName) {
                                        hasSameTypeSiblings = true;
                                        break;
                                    }
                                    nextSibling = nextSibling.nextElementSibling;
                                }

                                if (nth > 1 || hasSameTypeSiblings) {
                                    selector += ':nth-of-type(' + nth + ')';
                                }

                                path.unshift(selector);
                            }
                            current = current.parentElement;
                        }

                        const finalSelector = path.join(' > ');

                        // Validate the selector works
                        if (!validateSelector(finalSelector)) {
                            // Fallback: use a more permissive descendant selector
                            return path.join(' ');
                        }

                        return finalSelector;
                    }

                    selectors.forEach(selector => {
                        document.querySelectorAll(selector).forEach((el) => {
                            const rect = el.getBoundingClientRect();
                            const isVisible = rect.width > 0 && rect.height > 0;

                            // Skip non-interactive tabindex elements
                            if (el.hasAttribute('tabindex')) {
                                // Check if it's actually interactive (has click handlers, aria role, or is a list item)
                                const hasClickHandler = el.hasAttribute('onclick') ||
                                                       el.getAttribute('data-track-promo-click') !== null ||
                                                       el.getAttribute('data-track-eid-click') !== null;
                                const hasInteractiveRole = el.getAttribute('role') === 'button' ||
                                                          el.getAttribute('role') === 'link' ||
                                                          el.getAttribute('role') === 'tab' ||
                                                          el.getAttribute('role') === 'menuitem';
                                const isListItem = el.tagName === 'LI' && el.closest('ul, ol');

                                // Skip if it's just a focusable container (like image-container)
                                const dataCy = el.getAttribute('data-cy') || '';
                                const isContainer = dataCy.includes('container') ||
                                                   dataCy.includes('wrapper') ||
                                                   el.tagName === 'DIV' && !hasClickHandler && !hasInteractiveRole;

                                if (isContainer && !hasClickHandler && !hasInteractiveRole && !isListItem) {
                                    return; // Skip this element
                                }
                            }

                            if (isVisible) {
                                // Get element label - prioritize human-readable text over test attributes
                                let elementLabel = '';

                                // 1. Try visible text content first (most human-readable)
                                const textContent = el.textContent?.trim() || '';
                                if (textContent && textContent.length > 0 && textContent.length < 200) {
                                    elementLabel = textContent;
                                }

                                // 2. If no text, try aria-label (accessibility label)
                                if (!elementLabel) {
                                    elementLabel = el.getAttribute('aria-label') || '';
                                }

                                // 3. Try title attribute
                                if (!elementLabel) {
                                    elementLabel = el.getAttribute('title') || '';
                                }

                                // 4. For inputs, use placeholder or value
                                if (!elementLabel && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA')) {
                                    elementLabel = el.getAttribute('placeholder') || el.value || '';
                                }

                                // 5. For images, use alt text
                                if (!elementLabel && el.tagName === 'IMG') {
                                    elementLabel = el.getAttribute('alt') || '';
                                }

                                // 6. Last resort: use data-track-name or data-cy (not as readable)
                                if (!elementLabel) {
                                    elementLabel = el.getAttribute('data-track-name') ||
                                                 el.getAttribute('data-cy') ||
                                                 el.tagName.toLowerCase();
                                }

                                elements.push({
                                    selector: generateSelector(el),
                                    tag: el.tagName.toLowerCase(),
                                    type: el.type || el.getAttribute('role') || el.tagName.toLowerCase(),
                                    text: (el.textContent || el.value || el.alt || '').trim(),
                                    label: elementLabel.substring(0, 100), // Limit to 100 chars
                                    visible: true,
                                    position: {
                                        x: Math.round(rect.left),
                                        y: Math.round(rect.top),
                                        width: Math.round(rect.width),
                                        height: Math.round(rect.height)
                                    }
                                });
                            }
                        });
                    });

                    return elements;
                }
            """)

            self.logger.debug("Snapshot taken", element_count=len(elements))
            return {'elements': elements}

        except Exception as e:
            self.logger.error("Failed to take snapshot", error=str(e))
            raise

    async def get_console_messages(self) -> List[Dict[str, Any]]:
        """Get console messages from the browser."""
        # Note: Playwright doesn't store historical console messages
        # You need to set up a listener during initialization if needed
        self.logger.warning("Console message history not implemented yet")
        return []

    # JavaScript execution
    async def evaluate_script(self, script: str) -> Any:
        """Execute JavaScript in the browser."""
        try:
            result = await self.page.evaluate(script)
            return result
        except Exception as e:
            self.logger.error("Failed to execute script", error=str(e))
            raise

    # Interaction methods
    async def click_element(self, selector: str, expected_outcome_timeout_ms: int = 3000) -> Dict[str, Any]:
        """Click an element on the page and wait for the intended visual outcome.

        Args:
            selector: CSS selector for the element to click
            expected_outcome_timeout_ms: How long to wait for the intended outcome (default 3000ms)

        Returns:
            Dict with success status and timing info
        """
        try:
            # Check if we're in mobile mode
            is_mobile = hasattr(self.config, 'mobile_emulation') and self.config.mobile_emulation

            # Capture DOM state before interaction
            dom_snapshot_before = await self.page.evaluate("""
                () => {
                    // Helper to check if element is actually visible (has bounding rect with dimensions)
                    const isVisiblyRendered = (el) => {
                        if (!el) return false;
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    };

                    // Check for visible text content (detects slide-in menus/drawers)
                    const hasVisibleText = (text) => {
                        const walker = document.createTreeWalker(
                            document.body,
                            NodeFilter.SHOW_TEXT,
                            null,
                            false
                        );
                        let node;
                        while (node = walker.nextNode()) {
                            if (node.textContent.trim() === text) {
                                const parent = node.parentElement;
                                if (parent && parent.offsetParent !== null) {
                                    const rect = parent.getBoundingClientRect();
                                    if (rect.width > 0 && rect.height > 0 && rect.top >= 0 && rect.left >= 0) {
                                        return true;
                                    }
                                }
                            }
                        }
                        return false;
                    };

                    return {
                        bodyChildCount: document.body.children.length,
                        bodyClassName: document.body.className,
                        htmlClassName: document.documentElement.className,
                        dialogExists: !!document.querySelector('[role="dialog"]'),
                        dialogVisible: isVisiblyRendered(document.querySelector('[role="dialog"]')),
                        menuDrawerExists: !!document.querySelector('.drawer, .menu-drawer, [class*="drawer"]'),
                        menuDrawerVisible: isVisiblyRendered(document.querySelector('.drawer, .menu-drawer, [class*="drawer"]')),
                        navVisible: Array.from(document.querySelectorAll('nav')).some(n => n.offsetParent !== null),
                        overlayExists: !!document.querySelector('.overlay, .modal-backdrop, [class*="overlay"]'),
                        overlayVisible: isVisiblyRendered(document.querySelector('.overlay, .modal-backdrop, [class*="overlay"]')),
                        filterVisible: hasVisibleText('Filter'),
                        applyVisible: hasVisibleText('Apply')
                    };
                }
            """)

            # Set up requestAnimationFrame to track next paint
            await self.page.evaluate("""
                () => {
                    window.__inpTestData = {
                        clickTime: null,
                        nextPaintTime: null,
                        paintTimings: []
                    };
                }
            """)

            # Perform the interaction
            start_time = time.time()

            self.logger.debug("Starting interaction",
                            selector=selector,
                            mobile=is_mobile,
                            html_class_before=dom_snapshot_before.get('htmlClassName'),
                            overlay_before=dom_snapshot_before.get('overlayExists'))

            # Set up PerformanceObserver to capture Event Timing entry from Playwright's click
            # Extract processingStart (includes input delay) and measure to next paint
            await self.page.evaluate("""
                () => {
                    window.__inpTestData.eventEntry = null;

                    if ('PerformanceObserver' in window && PerformanceObserver.supportedEntryTypes?.includes('event')) {
                        const observer = new PerformanceObserver((list) => {
                            for (const entry of list.getEntries()) {
                                if (entry.name === 'pointerdown' || entry.name === 'mousedown' || entry.name === 'click') {
                                    // Capture the event timing entry
                                    window.__inpTestData.eventEntry = {
                                        name: entry.name,
                                        startTime: entry.startTime,
                                        processingStart: entry.processingStart,
                                        processingEnd: entry.processingEnd,
                                        duration: entry.duration
                                    };

                                    // Measure from processingStart to next paint
                                    const procStart = entry.processingStart;
                                    requestAnimationFrame(() => {
                                        requestAnimationFrame(() => {
                                            const paintTime = performance.now();
                                            const inp = paintTime - procStart;

                                            window.__inpTestData.clickTime = procStart;
                                            window.__inpTestData.nextPaintTime = paintTime;
                                            window.__inpTestData.paintTimings = [{
                                                time: paintTime,
                                                delta: inp
                                            }];
                                        });
                                    });
                                }
                            }
                        });
                        observer.observe({ type: 'event', buffered: true, durationThreshold: 0 });
                    }
                }
            """)

            # Perform Playwright's real browser click (generates trusted events)
            if is_mobile:
                try:
                    await self.page.tap(selector, timeout=5000)
                except Exception:
                    # CDP-connected contexts don't support tap — fall back to click
                    await self.page.click(selector, timeout=5000)
            else:
                await self.page.click(selector, timeout=5000)

            # Wait for PerformanceObserver and RAF to complete
            await self.page.wait_for_timeout(150)

            self.logger.debug("Interaction completed, starting outcome detection")

            # Give JavaScript a moment to process the event before we start checking
            await self.page.wait_for_timeout(100)

            # Wait for and detect the intended outcome
            outcome_detected = False
            check_interval = 0.1  # Check every 100ms
            timeout_seconds = expected_outcome_timeout_ms / 1000

            while (time.time() - start_time) < timeout_seconds:
                dom_snapshot_after = await self.page.evaluate("""
                    () => {
                        // Helper to check if element is actually visible (has bounding rect with dimensions)
                        const isVisiblyRendered = (el) => {
                            if (!el) return false;
                            const rect = el.getBoundingClientRect();
                            return rect.width > 0 && rect.height > 0;
                        };

                        // Check for visible text content (detects slide-in menus/drawers)
                        const hasVisibleText = (text) => {
                            const walker = document.createTreeWalker(
                                document.body,
                                NodeFilter.SHOW_TEXT,
                                null,
                                false
                            );
                            let node;
                            while (node = walker.nextNode()) {
                                if (node.textContent.trim() === text) {
                                    const parent = node.parentElement;
                                    if (parent && parent.offsetParent !== null) {
                                        const rect = parent.getBoundingClientRect();
                                        if (rect.width > 0 && rect.height > 0 && rect.top >= 0 && rect.left >= 0) {
                                            return true;
                                        }
                                    }
                                }
                            }
                            return false;
                        };

                        return {
                            bodyChildCount: document.body.children.length,
                            bodyClassName: document.body.className,
                            htmlClassName: document.documentElement.className,
                            dialogExists: !!document.querySelector('[role="dialog"]'),
                            dialogVisible: isVisiblyRendered(document.querySelector('[role="dialog"]')),
                            menuDrawerExists: !!document.querySelector('.drawer, .menu-drawer, [class*="drawer"]'),
                            menuDrawerVisible: isVisiblyRendered(document.querySelector('.drawer, .menu-drawer, [class*="drawer"]')),
                            navVisible: Array.from(document.querySelectorAll('nav')).some(n => n.offsetParent !== null),
                            overlayExists: !!document.querySelector('.overlay, .modal-backdrop, [class*="overlay"]'),
                            overlayVisible: isVisiblyRendered(document.querySelector('.overlay, .modal-backdrop, [class*="overlay"]')),
                            filterVisible: hasVisibleText('Filter'),
                            applyVisible: hasVisibleText('Apply')
                        };
                    }
                """)

                # Check if meaningful DOM changes occurred (not just scroll)
                # Now includes visibility changes for CSS-animated drawers/modals and text appearance
                if (dom_snapshot_after['dialogExists'] != dom_snapshot_before['dialogExists'] or
                    dom_snapshot_after['dialogVisible'] != dom_snapshot_before['dialogVisible'] or
                    dom_snapshot_after['menuDrawerExists'] != dom_snapshot_before['menuDrawerExists'] or
                    dom_snapshot_after['menuDrawerVisible'] != dom_snapshot_before['menuDrawerVisible'] or
                    dom_snapshot_after['overlayExists'] != dom_snapshot_before['overlayExists'] or
                    dom_snapshot_after['overlayVisible'] != dom_snapshot_before['overlayVisible'] or
                    dom_snapshot_after['filterVisible'] != dom_snapshot_before['filterVisible'] or
                    dom_snapshot_after['applyVisible'] != dom_snapshot_before['applyVisible'] or
                    dom_snapshot_after['bodyChildCount'] != dom_snapshot_before['bodyChildCount'] or
                    dom_snapshot_after['bodyClassName'] != dom_snapshot_before['bodyClassName'] or
                    dom_snapshot_after['htmlClassName'] != dom_snapshot_before['htmlClassName']):

                    outcome_detected = True
                    interaction_time_ms = (time.time() - start_time) * 1000
                    self.logger.info("Intended outcome detected",
                                   selector=selector,
                                   time_ms=round(interaction_time_ms, 1),
                                   mobile=is_mobile,
                                   html_class_before=dom_snapshot_before.get('htmlClassName'),
                                   html_class_after=dom_snapshot_after.get('htmlClassName'))
                    break

                await self.page.wait_for_timeout(int(check_interval * 1000))

            if not outcome_detected:
                interaction_time_ms = (time.time() - start_time) * 1000
                # Get final state for debugging
                final_state = await self.page.evaluate("""
                    () => {
                        return {
                            htmlClassName: document.documentElement.className,
                            bodyClassName: document.body.className,
                            overlayExists: !!document.querySelector('.overlay, .modal-backdrop, [class*="overlay"]')
                        };
                    }
                """)
                self.logger.warning("No intended outcome detected within timeout",
                                  selector=selector,
                                  timeout_ms=expected_outcome_timeout_ms,
                                  mobile=is_mobile,
                                  html_class_before=dom_snapshot_before.get('htmlClassName'),
                                  html_class_final=final_state.get('htmlClassName'),
                                  overlay_before=dom_snapshot_before.get('overlayExists'),
                                  overlay_final=final_state.get('overlayExists'))

            # Read RAF-based INP measurement (time to next paint)
            paint_data = await self.page.evaluate("""
                () => {
                    if (!window.__inpTestData) return null;
                    return {
                        clickTime: window.__inpTestData.clickTime,
                        nextPaintTime: window.__inpTestData.nextPaintTime,
                        paintTimings: window.__inpTestData.paintTimings
                    };
                }
            """)

            time_to_next_paint_ms = None
            if paint_data and paint_data.get('paintTimings') and len(paint_data['paintTimings']) > 0:
                time_to_next_paint_ms = round(paint_data['paintTimings'][0]['delta'], 1)

            return {
                'success': outcome_detected,
                'selector': selector,
                'interaction_time_ms': round(interaction_time_ms, 1),
                'time_to_next_paint_ms': time_to_next_paint_ms,
                'paint_timings': paint_data.get('paintTimings') if paint_data else [],
                'outcome_detected': outcome_detected
            }

        except Exception as e:
            self.logger.error("Failed to interact with element", selector=selector, error=str(e))
            raise

    async def hover_element(self, selector: str) -> Dict[str, Any]:
        """Hover over an element on the page."""
        try:
            await self.page.hover(selector, timeout=5000)
            self.logger.debug("Element hovered", selector=selector)
            return {'success': True, 'selector': selector}
        except Exception as e:
            self.logger.error("Failed to hover element", selector=selector, error=str(e))
            raise

    async def fill_element(self, selector: str, text: str) -> Dict[str, Any]:
        """Fill text into an input element."""
        try:
            await self.page.fill(selector, text, timeout=5000)
            return {'success': True, 'selector': selector, 'text': text}
        except Exception as e:
            self.logger.error("Failed to fill element", selector=selector, error=str(e))
            raise

    async def scroll_page(self, direction: str = "down", amount: int = 100) -> Dict[str, Any]:
        """Scroll the page."""
        try:
            scroll_amount = amount if direction == "down" else -amount
            await self.page.evaluate(f"window.scrollBy(0, {scroll_amount})")
            await asyncio.sleep(0.5)  # Wait for any lazy-loaded content
            return {'success': True, 'direction': direction, 'amount': amount}
        except Exception as e:
            self.logger.error("Failed to scroll page", error=str(e))
            raise

    async def wait_for_element(self, selector: str, timeout: int = 5000) -> bool:
        """Wait for an element to appear."""
        try:
            await self.page.wait_for_selector(selector, timeout=timeout)
            return True
        except Exception as e:
            self.logger.error("Failed to wait for element", selector=selector, error=str(e))
            return False

    # Performance methods
    async def start_performance_trace(self) -> Dict[str, Any]:
        """Start performance tracing."""
        try:
            # Start Chrome DevTools Protocol tracing
            await self.context.tracing.start(screenshots=True, snapshots=True)
            self.logger.debug("Performance trace started")
            return {'success': True}
        except Exception as e:
            self.logger.error("Failed to start performance trace", error=str(e))
            raise

    async def stop_performance_trace(self) -> Dict[str, Any]:
        """Stop performance tracing and get results."""
        try:
            trace_path = Path(f"{self.data_dir}/traces/trace_{id(self.page)}.zip")
            trace_path.parent.mkdir(parents=True, exist_ok=True)

            await self.context.tracing.stop(path=str(trace_path))

            self.logger.debug("Performance trace stopped", path=str(trace_path))
            return {
                'success': True,
                'trace_path': str(trace_path.absolute())
            }
        except Exception as e:
            self.logger.error("Failed to stop performance trace", error=str(e))
            raise

    async def get_inp_entry_count(self) -> int:
        """Get the current number of INP entries."""
        try:
            count = await self.page.evaluate("() => (window.__inpEntries || []).length")
            return count
        except Exception as e:
            self.logger.error("Failed to get INP entry count", error=str(e))
            return 0

    async def get_interaction_inp(self, entry_count_before: int, timeout_ms: int = 3000) -> Optional[Dict[str, Any]]:
        """
        Get INP measurement for the interaction we just performed.

        Args:
            entry_count_before: Number of INP entries before the interaction
            timeout_ms: How long to wait for a new INP entry (default 3000ms)

        Returns:
            INP entry dict if found, None if no new entry after timeout
        """
        try:
            start_time = asyncio.get_event_loop().time()
            check_interval = 0.05  # Check every 50ms

            while (asyncio.get_event_loop().time() - start_time) < (timeout_ms / 1000):
                result = await self.page.evaluate("""
                    (beforeCount) => {
                        const currentEntries = window.__inpEntries || [];

                        // Check if we have new entries since the interaction
                        if (currentEntries.length > beforeCount) {
                            // Get the newest entry (most recent interaction)
                            const newEntry = currentEntries[currentEntries.length - 1];
                            return {
                                hasNewEntry: true,
                                entry: newEntry,
                                totalEntries: currentEntries.length
                            };
                        }

                        return {
                            hasNewEntry: false,
                            totalEntries: currentEntries.length
                        };
                    }
                """, entry_count_before)

                if result.get('hasNewEntry'):
                    entry = result['entry']
                    self.logger.info("INP captured for interaction",
                                   inp_ms=entry.get('duration'),
                                   entry_type=entry.get('name'),
                                   interaction_id=entry.get('interactionId'))
                    return entry

                await asyncio.sleep(check_interval)

            # Timeout - no new INP entry detected
            self.logger.warning("No INP entry detected after interaction",
                              timeout_ms=timeout_ms,
                              entries_before=entry_count_before,
                              message="Interaction may not have triggered visual response")
            return None

        except Exception as e:
            self.logger.error("Failed to get interaction INP", error=str(e))
            return None

    async def get_performance_metrics(self) -> Dict[str, Any]:
        """Get performance metrics including INP data."""
        try:
            # Get INP entries collected during interactions
            inp_entries = await self.page.evaluate("window.__inpEntries || []")

            # Calculate worst INP
            worst_inp = 0
            worst_entry = None

            for entry in inp_entries:
                if entry.get('duration', 0) > worst_inp:
                    worst_inp = entry['duration']
                    worst_entry = entry

            # Get other performance metrics
            metrics = await self.page.evaluate("""
                () => {
                    const navTiming = performance.getEntriesByType('navigation')[0];
                    const paintEntries = performance.getEntriesByType('paint');

                    return {
                        navigation: navTiming ? {
                            domInteractive: navTiming.domInteractive,
                            domComplete: navTiming.domComplete,
                            loadEventEnd: navTiming.loadEventEnd
                        } : null,
                        paint: paintEntries.map(p => ({
                            name: p.name,
                            startTime: p.startTime
                        }))
                    };
                }
            """)

            return {
                'inp': {
                    'worst_inp': worst_inp,
                    'worst_entry': worst_entry,
                    'total_interactions': len(inp_entries),
                    'all_entries': inp_entries
                },
                'navigation': metrics.get('navigation'),
                'paint': metrics.get('paint')
            }

        except Exception as e:
            self.logger.error("Failed to get performance metrics", error=str(e))
            raise

    async def cleanup(self) -> None:
        """Clean up Playwright connection and Chrome subprocess."""
        self.logger.info("Cleaning up Playwright client")

        try:
            if self.page and not self.page.is_closed():
                try:
                    await self.page.close()
                except Exception:
                    pass

            if self.context:
                try:
                    await self.context.close()
                except Exception:
                    pass

            if self.browser:
                try:
                    await self.browser.close()
                except Exception:
                    pass

            if self.playwright:
                try:
                    await self.playwright.stop()
                except Exception:
                    pass

            # Terminate Chrome subprocess
            if self._chrome_process:
                try:
                    self._chrome_process.terminate()
                    self._chrome_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._chrome_process.kill()
                except Exception:
                    pass

            # Clean up temp user data dir
            if self._chrome_user_data_dir:
                import shutil as _shutil
                try:
                    _shutil.rmtree(self._chrome_user_data_dir, ignore_errors=True)
                except Exception:
                    pass

            self.logger.info("Playwright client cleanup complete")

        except Exception as e:
            self.logger.error("Error during cleanup", error=str(e))
            # Force cleanup
            if self._chrome_process:
                try:
                    self._chrome_process.kill()
                except Exception:
                    pass
