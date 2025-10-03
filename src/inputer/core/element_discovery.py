"""
Element Discovery Engine - Intelligent discovery of interactive elements.

This is a critical component that finds interactive elements during page rendering
and identifies candidates most likely to cause INP issues.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Set

import structlog

from inputer.config.settings import PerformanceConfig


logger = structlog.get_logger(__name__)


class ElementDiscoveryEngine:
    """
    Intelligent engine for discovering interactive elements on web pages.

    Key capabilities:
    - Discovers elements during page rendering (not just after load)
    - Prioritizes elements likely to cause INP issues
    - Handles dynamic content and lazy-loaded elements
    - Filters out non-interactive or problematic elements
    """

    def __init__(self, mcp_client, settings: PerformanceConfig):
        """Initialize the element discovery engine."""
        self.playwright_client = mcp_client
        self.settings = settings
        self.logger = logger.bind(component="element_discovery")

        # Cache for discovered elements
        self.element_cache: Dict[str, List[Dict]] = {}
        self.discovery_attempts = 0

        # Element selectors that typically cause INP issues
        self.high_impact_selectors = [
            "button", "a", "[role=button]", "[role=link]",
            "input[type=submit]", "input[type=button]",
            ".dropdown", ".accordion", ".modal-trigger",
            "[data-toggle]", "[data-bs-toggle]", "[onclick]",
            ".carousel", ".tab", ".slider", "[role=tab]",
            "select", "input[type=checkbox]", "input[type=radio]"
        ]

        # Elements to avoid (likely to cause issues or not useful)
        self.avoid_selectors = [
            "input[type=hidden]", "input[type=password]",
            ".disabled", "[disabled]", "[aria-disabled=true]",
            "script", "style", "noscript", "iframe",
            ".sr-only", ".visually-hidden", "[style*='display: none']"
        ]

    async def discover_interactive_elements(self, skip_nav_footer: bool = False) -> List[Dict[str, Any]]:
        """
        Main method to discover interactive elements on the current page.

        Args:
            skip_nav_footer: If True, filter out navigation and footer elements before limiting results

        Returns:
            List of interactive element descriptors with metadata
        """
        self.discovery_attempts += 1
        attempt_logger = self.logger.bind(attempt=self.discovery_attempts)

        attempt_logger.info("Starting element discovery")

        try:
            # Multi-stage discovery approach
            elements = []

            # Stage 1: Quick discovery of immediately visible elements
            immediate_elements = await self._discover_immediate_elements()
            elements.extend(immediate_elements)

            # Stage 2: Wait for dynamic content and discover again
            await asyncio.sleep(1)  # Allow for dynamic loading
            dynamic_elements = await self._discover_dynamic_elements()
            elements.extend(dynamic_elements)

            # Stage 3: Trigger lazy loading and discover more
            lazy_elements = await self._discover_lazy_elements()
            elements.extend(lazy_elements)

            # Remove duplicates and filter
            unique_elements = self._deduplicate_elements(elements)

            # Filter by viewport visibility
            viewport_accessible_elements = await self._filter_by_viewport_visibility(unique_elements)

            # Final filtering and prioritization
            filtered_elements = await self._filter_and_prioritize_elements(viewport_accessible_elements, skip_nav_footer)

            attempt_logger.info(
                "Element discovery complete",
                total_found=len(elements),
                unique=len(unique_elements),
                viewport_accessible=len(viewport_accessible_elements),
                final_filtered=len(filtered_elements)
            )

            return filtered_elements

        except Exception as e:
            attempt_logger.error("Error during element discovery", error=str(e))
            return []

    async def _discover_immediate_elements(self) -> List[Dict[str, Any]]:
        """Discover immediately visible interactive elements using Playwright."""
        try:
            # Use Playwright's take_snapshot to get all page elements
            snapshot = await self.playwright_client.take_snapshot()

            # Playwright returns {'elements': [...]} format
            if isinstance(snapshot, dict) and 'elements' in snapshot:
                elements = snapshot['elements']

                # Add discovery metadata
                for element in elements:
                    element['discovery_stage'] = 'immediate'
                    # Set priority based on element type
                    element['priority'] = 'high' if element.get('tag') == 'button' else 'medium'

                self.logger.debug("Immediate elements discovered via Playwright", count=len(elements))
                return elements
            else:
                self.logger.warning("Unexpected snapshot format", snapshot_type=type(snapshot).__name__)
                return []

        except Exception as e:
            self.logger.error("Failed to discover immediate elements", error=str(e))
            return []

    async def _discover_dynamic_elements(self) -> List[Dict[str, Any]]:
        """Skip dynamic discovery - take_snapshot already captures all elements."""
        # take_snapshot gets the current state, so we don't need separate dynamic discovery
        return []

    async def _discover_lazy_elements(self) -> List[Dict[str, Any]]:
        """Skip lazy discovery for now - take_snapshot handles current page state."""
        # We could scroll and take another snapshot, but for now keep it simple
        return []

    async def _discover_lazy_elements_old(self) -> List[Dict[str, Any]]:
        """OLD: Discover elements that appear after initial load."""
        try:
            # JavaScript to find elements that might have appeared dynamically
            dynamic_script = """
            (() => {
                const elements = [];

                // Look for commonly dynamic elements
                const dynamicSelectors = [
                    '.lazy-load', '.deferred', '[data-lazy]',
                    '.modal', '.popup', '.overlay', '.toast',
                    '.notification', '.alert', '.banner',
                    '[aria-live]', '[role="alert"]', '[role="status"]'
                ];

                dynamicSelectors.forEach(selector => {
                    try {
                        const found = document.querySelectorAll(selector);
                        found.forEach((el, index) => {
                            // Check if element is interactable
                            const isInteractable = (
                                el.tagName === 'BUTTON' ||
                                el.tagName === 'A' ||
                                el.getAttribute('role') === 'button' ||
                                el.getAttribute('onclick') ||
                                el.querySelector('button, a, [role="button"]')
                            );

                            if (isInteractable) {
                                const rect = el.getBoundingClientRect();

                                elements.push({
                                    selector: `${selector}:nth-of-type(${index + 1})`,
                                    tag: el.tagName.toLowerCase(),
                                    type: 'dynamic',
                                    text: (el.textContent || '').trim().substring(0, 100),
                                    visible: rect.width > 0 && rect.height > 0,
                                    position: {
                                        x: Math.round(rect.left),
                                        y: Math.round(rect.top),
                                        width: Math.round(rect.width),
                                        height: Math.round(rect.height)
                                    },
                                    attributes: {
                                        id: el.id || null,
                                        class: el.className || null
                                    },
                                    complexity_score: 2,  // Dynamic elements often more complex
                                    discovery_stage: 'dynamic'
                                });
                            }
                        });
                    } catch (e) {
                        console.warn('Error with dynamic selector:', selector, e);
                    }
                });

                return elements;
            })();
            """

            result = await self.playwright_client.evaluate_script(dynamic_script)
            # Handle both direct list results and MCP response format
            if isinstance(result, dict) and "content" in result and "result" in result["content"]:
                elements = result["content"]["result"] if isinstance(result["content"]["result"], list) else []
            else:
                elements = result if isinstance(result, list) else []

            self.logger.debug("Dynamic elements discovered", count=len(elements))
            return elements

        except Exception as e:
            self.logger.error("Failed to discover dynamic elements", error=str(e))
            return []

    async def _discover_lazy_elements(self) -> List[Dict[str, Any]]:
        """Discover elements that load lazily by triggering scroll/interaction."""
        try:
            # Scroll to trigger lazy loading
            await self.playwright_client.scroll_page("down", 1000)
            await asyncio.sleep(0.5)

            await self.playwright_client.scroll_page("up", 500)
            await asyncio.sleep(0.5)

            # JavaScript to find any new elements that appeared
            lazy_script = """
            (() => {
                const elements = [];

                // Look for elements that might be lazy-loaded
                const lazySelectors = [
                    '[data-src]', '[loading="lazy"]', '.lazy',
                    '.infinite-scroll', '.load-more',
                    '.pagination button', '.pagination a'
                ];

                lazySelectors.forEach(selector => {
                    try {
                        const found = document.querySelectorAll(selector);
                        found.forEach((el, index) => {
                            if (el.offsetParent !== null) {
                                const rect = el.getBoundingClientRect();

                                elements.push({
                                    selector: `${selector}:nth-of-type(${index + 1})`,
                                    tag: el.tagName.toLowerCase(),
                                    type: 'lazy',
                                    text: (el.textContent || el.alt || '').trim().substring(0, 100),
                                    visible: true,
                                    position: {
                                        x: Math.round(rect.left),
                                        y: Math.round(rect.top),
                                        width: Math.round(rect.width),
                                        height: Math.round(rect.height)
                                    },
                                    attributes: {
                                        id: el.id || null,
                                        class: el.className || null
                                    },
                                    complexity_score: 1,
                                    discovery_stage: 'lazy'
                                });
                            }
                        });
                    } catch (e) {
                        console.warn('Error with lazy selector:', selector, e);
                    }
                });

                return elements;
            })();
            """

            result = await self.playwright_client.evaluate_script(lazy_script)
            # Handle both direct list results and MCP response format
            if isinstance(result, dict) and "content" in result and "result" in result["content"]:
                elements = result["content"]["result"] if isinstance(result["content"]["result"], list) else []
            else:
                elements = result if isinstance(result, list) else []

            self.logger.debug("Lazy elements discovered", count=len(elements))
            return elements

        except Exception as e:
            self.logger.error("Failed to discover lazy elements", error=str(e))
            return []

    def _deduplicate_elements(self, elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate elements based on position and content."""
        try:
            seen_elements: Set[str] = set()
            unique_elements = []

            for element in elements:
                # Create a unique key based on position and text
                position = element.get("position", {})
                text = element.get("text", "")
                element_key = f"{position.get('x', 0)},{position.get('y', 0)}:{text[:20]}"

                if element_key not in seen_elements:
                    seen_elements.add(element_key)
                    unique_elements.append(element)

            self.logger.debug(
                "Deduplication complete",
                original=len(elements),
                unique=len(unique_elements)
            )

            return unique_elements

        except Exception as e:
            self.logger.error("Error during deduplication", error=str(e))
            return elements

    async def _filter_by_viewport_visibility(self, elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter elements by viewport visibility - only keep elements that are accessible via scrolling."""
        try:
            # JavaScript to check viewport visibility and scrollability for all elements
            visibility_script = """
            (elements) => {
                const viewportHeight = window.innerHeight;
                const documentHeight = document.documentElement.scrollHeight;

                return elements.map(el => {
                    const selector = el.selector;
                    let domElement;

                    try {
                        domElement = document.querySelector(selector);
                        if (!domElement) return {...el, viewport_accessible: false, reason: 'not_found'};

                        // Get element position first
                        const rect = domElement.getBoundingClientRect();

                        // Check if element has zero size (truly hidden)
                        if (rect.width === 0 || rect.height === 0) {
                            return {...el, viewport_accessible: false, reason: 'zero_size'};
                        }

                        // Additional check: Is element actually visible using offsetParent?
                        // offsetParent is null if element or any ancestor has display:none
                        if (domElement.offsetParent === null && domElement.tagName !== 'BODY' && domElement.tagName !== 'HTML') {
                            return {...el, viewport_accessible: false, reason: 'not_rendered'};
                        }

                        // Check if element itself is hidden via CSS
                        const computed = window.getComputedStyle(domElement);
                        if (computed.display === 'none' || computed.visibility === 'hidden' || parseFloat(computed.opacity) === 0) {
                            return {...el, viewport_accessible: false, reason: 'css_hidden'};
                        }

                        // Check if parent containers are hidden (close buttons in hidden menus/modals)
                        let parent = domElement.parentElement;
                        while (parent && parent !== document.body) {
                            const parentStyle = window.getComputedStyle(parent);
                            if (parentStyle.display === 'none' ||
                                parentStyle.visibility === 'hidden' ||
                                parseFloat(parentStyle.opacity) === 0) {
                                return {...el, viewport_accessible: false, reason: 'parent_hidden'};
                            }
                            parent = parent.parentElement;
                        }

                        const elementTop = rect.top + window.scrollY;

                        // Check if element is currently in viewport
                        const inViewport = rect.top >= 0 && rect.top < viewportHeight;

                        // Check if element can be reached by scrolling (not in hidden menu)
                        const scrollable = elementTop < documentHeight;

                        return {
                            ...el,
                            viewport_accessible: true,
                            initially_visible: inViewport,
                            requires_scroll: !inViewport && scrollable,
                            scroll_position: elementTop
                        };
                    } catch (e) {
                        return {...el, viewport_accessible: false, reason: 'error'};
                    }
                });
            }
            """

            # Use page.evaluate directly to pass elements as argument
            result = await self.playwright_client.page.evaluate(visibility_script, elements)

            # Filter to only viewport-accessible elements
            accessible_elements = [
                el for el in result
                if el.get('viewport_accessible', False)
            ]

            # Count filtering reasons
            filtered_reasons = {}
            for el in result:
                if not el.get('viewport_accessible', False):
                    reason = el.get('reason', 'unknown')
                    filtered_reasons[reason] = filtered_reasons.get(reason, 0) + 1

            self.logger.info(
                "Viewport visibility filtering complete",
                total=len(elements),
                accessible=len(accessible_elements),
                initially_visible=len([e for e in accessible_elements if e.get('initially_visible')]),
                requires_scroll=len([e for e in accessible_elements if e.get('requires_scroll')]),
                filtered_reasons=filtered_reasons
            )

            return accessible_elements

        except Exception as e:
            self.logger.error("Error during viewport visibility filtering", error=str(e))
            return elements

    async def _filter_and_prioritize_elements(self, elements: List[Dict[str, Any]], skip_nav_footer: bool = False) -> List[Dict[str, Any]]:
        """Filter out problematic elements and prioritize by INP potential.

        Args:
            elements: List of element dictionaries to filter
            skip_nav_footer: If True, filter out navigation and footer elements before limiting results
        """
        try:
            filtered_elements = []

            for element in elements:
                # Skip if element is not visible
                if not element.get("visible", False):
                    continue

                # Skip if element is not viewport accessible (hidden in menu/modal)
                if not element.get("viewport_accessible", True):
                    continue

                # Skip close buttons - they're only useful after opening something first
                # and cause too many false positives in testing
                selector = element.get("selector", "")
                text = element.get("text", "").lower()
                label = element.get("label", "").lower()
                if ("close" in selector.lower() or
                    "close" in text or
                    "close" in label or
                    selector == '[data-cy="close-button"]'):
                    continue

                # Skip footer elements (bottom 50% of page) - too far down and less relevant for INP testing
                position = element.get("position", {})
                y_position = position.get("y", 0)
                scroll_position = element.get("scroll_position", y_position)

                # Check if element is in footer using scroll position or data attributes
                if ("footer" in selector.lower() or
                    "footer" in text or
                    "footer" in label):
                    continue

                # Skip if element is too small (mobile-adjusted thresholds)
                position = element.get("position", {})
                width = position.get("width", 0)
                height = position.get("height", 0)

                # Mobile touch targets should be at least 44px, but allow smaller for some cases
                # due to device pixel ratio scaling
                min_size = 8  # Reduced from 10 for mobile (will be scaled by device pixel ratio)
                if width < min_size or height < min_size:
                    # But allow if it's a clearly interactive element even if small
                    tag = element.get("tag", "").lower()
                    element_type = element.get("type", "").lower()
                    if tag not in ["button", "a"] and "button" not in element_type:
                        continue

                # Skip if element has disabled attributes
                attributes = element.get("attributes", {})
                class_names = attributes.get("class", "") or ""
                if any(avoid in class_names.lower() for avoid in ["disabled", "hidden", "sr-only"]):
                    continue

                # Calculate complexity/INP potential score
                element["inp_potential_score"] = self._calculate_inp_potential(element)

                filtered_elements.append(element)

            # Sort by INP potential (highest first)
            filtered_elements.sort(
                key=lambda x: x.get("inp_potential_score", 0),
                reverse=True
            )

            # Filter out navigation/footer elements if requested (do this BEFORE limiting to 20)
            if skip_nav_footer:
                nav_footer_filtered = []
                for element in filtered_elements:
                    selector = element.get("selector", "")
                    try:
                        # Use JavaScript to check if element is within nav/footer hierarchy
                        is_nav_footer = await self.playwright_client.page.evaluate(f"""
                            () => {{
                                const el = document.querySelector('{selector}');
                                if (!el) return false;

                                // Check if element is within common navigation patterns
                                // 1. Inside <header> tag
                                if (el.closest('header') !== null) return true;

                                // 2. Inside <nav> tag
                                if (el.closest('nav') !== null) return true;

                                // 3. Inside element with role="navigation"
                                if (el.closest('[role="navigation"]') !== null) return true;

                                // 4. Inside element with data-track-name containing "header"
                                const trackElement = el.closest('[data-track-name]');
                                if (trackElement && trackElement.getAttribute('data-track-name').toLowerCase().includes('header')) {{
                                    return true;
                                }}

                                // 5. Inside common nav class patterns
                                if (el.closest('[class*="navbar"]') !== null) return true;
                                if (el.closest('[class*="nav-bar"]') !== null) return true;
                                if (el.closest('[class*="navigation"]') !== null) return true;

                                // 6. Inside common nav ID patterns
                                if (el.closest('#primary-nav') !== null) return true;
                                if (el.closest('#main-nav') !== null) return true;
                                if (el.closest('#site-nav') !== null) return true;
                                if (el.closest('#top-nav') !== null) return true;

                                // 7. Inside footer elements (use word boundaries to avoid matching content__footer, etc)
                                if (el.closest('footer') !== null) return true;
                                if (el.closest('[role="contentinfo"]') !== null) return true;
                                const footerElement = el.closest('[class], [id]');
                                if (footerElement) {{
                                    const classes = footerElement.className || '';
                                    const id = footerElement.id || '';
                                    if (/\\b(site|page|main|global)?-?footer\\b/i.test(classes) || /\\b(site|page|main|global)?-?footer\\b/i.test(id)) {{
                                        return true;
                                    }}
                                }}

                                // 8. Site header patterns (more specific - exclude article__header, section__header, etc)
                                const headerElement = el.closest('[class], [id]');
                                if (headerElement) {{
                                    const classes = headerElement.className || '';
                                    const id = headerElement.id || '';
                                    if (/\\b(site|page|main|global)?-?header\\b/i.test(classes) || /\\b(site|page|main|global)?-?header\\b/i.test(id)) {{
                                        return true;
                                    }}
                                }}

                                // 9. Share/social buttons (not typically INP-critical)
                                const text = (el.textContent || el.getAttribute('aria-label') || '').toLowerCase();
                                if (/\\b(share|tweet|facebook|twitter|linkedin|pinterest|instagram|whatsapp|email this|print this)\\b/i.test(text)) {{
                                    return true;
                                }}
                                if (el.className && /\\b(share|social|sns)[-_]/.test(el.className.toLowerCase())) {{
                                    return true;
                                }}

                                return false;
                            }}
                        """)

                        if not is_nav_footer:
                            nav_footer_filtered.append(element)
                    except Exception as e:
                        # If evaluation fails, keep the element to be safe
                        self.logger.debug(
                            "Error evaluating nav/footer filter, keeping element",
                            selector=selector,
                            error=str(e)
                        )
                        nav_footer_filtered.append(element)

                excluded_count = len(filtered_elements) - len(nav_footer_filtered)
                if excluded_count > 0:
                    self.logger.info(
                        "Filtered navigation/footer elements",
                        total_elements=len(filtered_elements),
                        excluded=excluded_count,
                        remaining=len(nav_footer_filtered)
                    )
                filtered_elements = nav_footer_filtered

            # Limit to reasonable number of elements
            max_elements = 20
            if len(filtered_elements) > max_elements:
                filtered_elements = filtered_elements[:max_elements]

            self.logger.debug(
                "Filtering and prioritization complete",
                filtered_count=len(filtered_elements)
            )

            return filtered_elements

        except Exception as e:
            self.logger.error("Error during filtering", error=str(e))
            return elements

    def _calculate_inp_potential(self, element: Dict[str, Any]) -> float:
        """Calculate how likely an element is to cause INP issues."""
        score = 0.0

        try:
            tag = element.get("tag", "").lower()
            element_type = element.get("type", "").lower()
            text = element.get("text", "").lower()
            attributes = element.get("attributes", {})
            class_names = (attributes.get("class", "") or "").lower()
            data_attrs = attributes.get("data-*", "") or ""

            # Base scores by element type
            type_scores = {
                "button": 3.0,
                "submit": 3.0,
                "dropdown": 4.0,
                "accordion": 4.0,
                "modal": 4.0,
                "tab": 3.5,
                "carousel": 4.5,
                "slider": 4.0,
                "checkbox": 2.0,
                "radio": 2.0,
                "select": 3.0
            }

            # Assign base score
            for elem_type, type_score in type_scores.items():
                if elem_type in element_type or elem_type in tag:
                    score += type_score
                    break
            else:
                score += 1.0  # Default score

            # Bonus for complex class names
            complex_classes = [
                "dropdown", "accordion", "modal", "carousel", "slider",
                "tooltip", "popover", "datepicker", "autocomplete",
                "infinite", "lazy", "dynamic", "ajax"
            ]
            for complex_class in complex_classes:
                if complex_class in class_names:
                    score += 1.5

            # Bonus for data attributes (often indicate complex behavior)
            if "data-" in data_attrs:
                score += 1.0

            # Bonus for JavaScript event indicators
            js_indicators = ["onclick", "toggle", "trigger", "load", "submit"]
            for indicator in js_indicators:
                if indicator in data_attrs or indicator in class_names:
                    score += 1.0

            # Bonus for dynamic discovery stage
            discovery_stage = element.get("discovery_stage", "")
            if discovery_stage == "dynamic":
                score += 2.0
            elif discovery_stage == "lazy":
                score += 1.5

            # Penalty for very common/simple elements
            simple_indicators = ["link", "nav", "menu", "home", "about"]
            for indicator in simple_indicators:
                if indicator in text or indicator in class_names:
                    score -= 0.5

            # Bonus for above-the-fold placement (more likely to be clicked by users)
            position = element.get("position", {})
            y_position = position.get("y", 0)
            if element.get("initially_visible", False):
                score += 2.0  # Element is in initial viewport
            elif y_position < 1000:
                score += 1.0  # Element is near top of page

            # Ensure score is non-negative
            score = max(0.0, score)

            return score

        except Exception as e:
            self.logger.error("Error calculating INP potential", error=str(e))
            return 1.0  # Default score

    async def refresh_element_cache(self) -> None:
        """Refresh the cached elements for the current page."""
        try:
            elements = await self.discover_interactive_elements()
            page_info = await self.playwright_client.get_page_info()
            page_url = page_info.get("url", "unknown")

            self.element_cache[page_url] = elements
            self.logger.debug("Element cache refreshed", url=page_url, count=len(elements))

        except Exception as e:
            self.logger.error("Failed to refresh element cache", error=str(e))

    def get_cached_elements(self, url: str) -> List[Dict[str, Any]]:
        """Get cached elements for a specific URL."""
        return self.element_cache.get(url, [])