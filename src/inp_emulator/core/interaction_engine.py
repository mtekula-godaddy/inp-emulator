"""
User Interaction Engine - Realistic timing and interaction patterns.

This component emulates realistic user behavior patterns and timing
to trigger INP issues that would occur in real usage scenarios.
"""

import asyncio
import random
import time
from typing import Any, Dict, List, Optional

import structlog

from inp_emulator.config.settings import PerformanceConfig


logger = structlog.get_logger(__name__)


class UserInteractionEngine:
    """
    Engine for executing user interactions with realistic timing patterns.

    Key features:
    - Human-like delays between interactions
    - Realistic mouse movement patterns
    - Appropriate timing for different interaction types
    - Context-aware interaction strategies
    """

    def __init__(self, mcp_client, settings: PerformanceConfig, session_id: str = None):
        """Initialize the interaction engine."""
        self.playwright_client = mcp_client
        self.settings = settings
        self.logger = logger.bind(component="interaction_engine")

        # Session ID for organizing screenshots
        self.session_id = session_id or f"session_{int(time.time())}"

        # Timing parameters
        self.min_delay = settings.interaction_delay_min
        self.max_delay = settings.interaction_delay_max

        # Interaction patterns and timing
        self.interaction_timings = {
            "click": {
                "pre_delay": (100, 300),    # Delay before click
                "post_delay": (200, 500),   # Delay after click
                "hover_time": (50, 150)     # Time to hover before click
            },
            "hover": {
                "pre_delay": (50, 200),
                "post_delay": (100, 300),
                "dwell_time": (300, 800)    # Time to keep hovering
            },
            "type": {
                "pre_delay": (200, 500),
                "post_delay": (300, 600),
                "keystroke_delay": (50, 150) # Delay between keystrokes
            },
            "scroll": {
                "pre_delay": (100, 400),
                "post_delay": (200, 500),
                "scroll_speed": (200, 800)  # Pixels per scroll step
            }
        }

        # Track interaction history for pattern analysis
        self.interaction_history: List[Dict[str, Any]] = []

    async def execute_interaction(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a user interaction with realistic timing and behavior.

        Args:
            action: The action to execute (from LLM decision)

        Returns:
            Dict containing execution results and timing information
        """
        start_time = time.time()
        action_type = action.get("action", "unknown")
        selector = action.get("selector", "")

        # Try to get element label for better logging (same priority as snapshot)
        element_text = ""
        try:
            element_text = await self.playwright_client.page.evaluate(f"""
                (selector) => {{
                    const el = document.querySelector(selector);
                    if (!el) return '';

                    // Priority: button/link text > aria-label > data attributes > alt/value
                    let label = '';
                    if (el.tagName === 'BUTTON' || el.tagName === 'A') {{
                        label = el.textContent?.trim() || '';
                    }}
                    if (!label) {{
                        label = el.getAttribute('aria-label') ||
                               el.getAttribute('data-track-name') ||
                               el.getAttribute('title') ||
                               el.getAttribute('alt') ||
                               el.value ||
                               el.textContent?.trim() ||
                               '';
                    }}
                    return label.substring(0, 50);
                }}
            """, selector)
        except:
            pass

        interaction_logger = self.logger.bind(
            action=action_type,
            selector=selector[:50] + "..." if len(selector) > 50 else selector,
            element_text=element_text if element_text else "unknown"
        )

        interaction_logger.info("Executing interaction")

        try:
            # Scroll to element if not in viewport
            await self._scroll_to_element_if_needed(selector)

            # Pre-interaction delay (user thinking/moving mouse)
            await self._pre_interaction_delay(action_type)

            # Take screenshot before interaction (both full page and element-specific)
            pre_screenshot = None
            pre_element_screenshot = None
            if self.settings.screenshot_capture:
                try:
                    # Full page screenshot
                    filename = f"{self.session_id}/pre_{action_type}_{selector.replace(':', '_').replace('[', '').replace(']', '').replace('\"', '')[:30]}_{int(start_time)}.png"
                    pre_screenshot = await self.playwright_client.take_screenshot(filename)
                    interaction_logger.debug("Pre-interaction screenshot captured", path=pre_screenshot)

                    # Element-specific screenshot
                    element_filename = f"{self.session_id}/pre_{action_type}_element_{selector.replace(':', '_').replace('[', '').replace(']', '').replace('\"', '')[:30]}_{int(start_time)}.png"
                    pre_element_screenshot = await self.playwright_client.take_screenshot(element_filename, selector=selector)
                    interaction_logger.debug("Pre-interaction element screenshot captured", path=pre_element_screenshot)
                except Exception as e:
                    interaction_logger.warning("Failed to capture pre-interaction screenshot", error=str(e))

            # Execute the specific interaction
            result = await self._execute_specific_action(action)

            # Take screenshot after interaction (both full page and element-specific)
            post_screenshot = None
            post_element_screenshot = None
            if self.settings.screenshot_capture:
                try:
                    # Full page screenshot
                    filename = f"{self.session_id}/post_{action_type}_{selector.replace(':', '_').replace('[', '').replace(']', '').replace('\"', '')[:30]}_{int(start_time)}.png"
                    post_screenshot = await self.playwright_client.take_screenshot(filename)
                    interaction_logger.debug("Post-interaction screenshot captured", path=post_screenshot)

                    # Element-specific screenshot
                    element_filename = f"{self.session_id}/post_{action_type}_element_{selector.replace(':', '_').replace('[', '').replace(']', '').replace('\"', '')[:30]}_{int(start_time)}.png"
                    post_element_screenshot = await self.playwright_client.take_screenshot(element_filename, selector=selector)
                    interaction_logger.debug("Post-interaction element screenshot captured", path=post_element_screenshot)
                except Exception as e:
                    interaction_logger.warning("Failed to capture post-interaction screenshot", error=str(e))

            # Post-interaction delay (user observing results)
            await self._post_interaction_delay(action_type)

            execution_time = time.time() - start_time

            # Record interaction in history
            interaction_record = {
                "action": action,
                "result": result,
                "execution_time": execution_time,
                "timestamp": start_time,
                "success": result.get("success", False),
                "inp_ms": result.get("inp_ms"),  # Pull INP measurement to top level for easy access
                "screenshots": {
                    "pre_interaction": pre_screenshot,
                    "post_interaction": post_screenshot
                }
            }
            self.interaction_history.append(interaction_record)

            # Keep only last 10 interactions in memory
            if len(self.interaction_history) > 10:
                self.interaction_history = self.interaction_history[-10:]

            interaction_logger.info(
                "Interaction complete",
                execution_time=f"{execution_time:.2f}s",
                success=result.get("success", False)
            )

            return interaction_record

        except Exception as e:
            interaction_logger.error("Interaction failed", error=str(e))
            return {
                "action": action,
                "result": {"success": False, "error": str(e)},
                "execution_time": time.time() - start_time,
                "timestamp": start_time,
                "success": False
            }

    async def _execute_specific_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the specific action type with appropriate behavior."""
        action_type = action.get("action")
        selector = action.get("selector", "")

        try:
            if action_type == "click":
                return await self._execute_click(action)
            elif action_type == "hover":
                return await self._execute_hover(action)
            elif action_type == "type":
                return await self._execute_type(action)
            elif action_type == "scroll":
                return await self._execute_scroll(action)
            else:
                raise ValueError(f"Unknown action type: {action_type}")

        except Exception as e:
            self.logger.error("Failed to execute specific action", action=action_type, error=str(e))
            raise

    async def _execute_click(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a click interaction with realistic mouse behavior."""
        selector = action.get("selector", "")

        try:
            # Check if element is visible and measure time to interactive
            time_to_interactive = await self._measure_time_to_interactive(selector)

            # For desktop, hover first (realistic mouse movement)
            # Skip hover for mobile since mobile devices don't have hover
            is_mobile = hasattr(self.playwright_client.config, 'mobile_emulation') and self.playwright_client.config.mobile_emulation

            if not is_mobile:
                hover_time = random.uniform(*self.interaction_timings["click"]["hover_time"])
                await self.playwright_client.hover_element(selector)
                await asyncio.sleep(hover_time / 1000)  # Convert to seconds
            else:
                hover_time = 0

            # Click and wait for intended outcome (this measures real INP - time to functional response)
            result = await self.playwright_client.click_element(selector, expected_outcome_timeout_ms=3000)

            # Use RAF (requestAnimationFrame) as primary INP measurement
            # This is the industry standard for automation per web.dev
            # Fall back to functional outcome time if RAF not available
            inp_ms = result.get('time_to_next_paint_ms') or result.get('interaction_time_ms')
            outcome_detected = result.get('outcome_detected', False)

            # Store all measurements
            paint_ms = result.get('time_to_next_paint_ms')
            functional_outcome_ms = result.get('interaction_time_ms')

            if paint_ms:
                self.logger.info("INP measured via RAF",
                               inp_ms=inp_ms,
                               outcome_ms=functional_outcome_ms,
                               selector=selector[:50])
            elif outcome_detected:
                self.logger.info("INP measured - outcome detected",
                               inp_ms=inp_ms,
                               selector=selector[:50])
            else:
                self.logger.warning("INP timeout - no functional response",
                                  inp_ms=inp_ms,
                                  selector=selector[:50])

            return {
                "success": outcome_detected,
                "action_type": "click",
                "selector": selector,
                "hover_duration": hover_time,
                "inp_ms": inp_ms,
                "paint_ms": paint_ms,
                "functional_outcome_ms": functional_outcome_ms,
                "has_visual_response": outcome_detected,
                "details": result
            }

        except Exception as e:
            return {
                "success": False,
                "action_type": "click",
                "selector": selector,
                "error": str(e)
            }

    async def _scroll_to_element_if_needed(self, selector: str) -> None:
        """Scroll element into view if it's not currently in the viewport."""
        try:
            # Check if element is in viewport and scroll if needed
            is_in_viewport = await self.playwright_client.page.evaluate("""
                (selector) => {
                    const element = document.querySelector(selector);
                    if (!element) return true; // Can't scroll to non-existent element

                    const rect = element.getBoundingClientRect();
                    return (
                        rect.top >= 0 &&
                        rect.left >= 0 &&
                        rect.bottom <= window.innerHeight &&
                        rect.right <= window.innerWidth
                    );
                }
            """, selector)

            if not is_in_viewport:
                # Scroll element into view with smooth behavior
                await self.playwright_client.page.evaluate("""
                    (selector) => {
                        const element = document.querySelector(selector);
                        if (element) {
                            element.scrollIntoView({
                                behavior: 'smooth',
                                block: 'center',
                                inline: 'nearest'
                            });
                        }
                    }
                """, selector)

                # Wait for scroll animation to complete
                await asyncio.sleep(0.5)

                self.logger.debug("Scrolled to element", selector=selector[:50])
        except Exception as e:
            # Don't fail interaction if scroll fails
            self.logger.warning("Failed to scroll to element", selector=selector[:50], error=str(e))

    async def _execute_hover(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a hover interaction with realistic dwell time."""
        selector = action.get("selector", "")

        try:
            # Hover over the element
            result = await self.playwright_client.hover_element(selector)

            # Realistic dwell time
            dwell_time = random.uniform(*self.interaction_timings["hover"]["dwell_time"])
            await asyncio.sleep(dwell_time / 1000)

            return {
                "success": True,
                "action_type": "hover",
                "selector": selector,
                "dwell_duration": dwell_time,
                "details": result
            }

        except Exception as e:
            return {
                "success": False,
                "action_type": "hover",
                "selector": selector,
                "error": str(e)
            }

    async def _execute_type(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Execute typing with realistic keystroke timing."""
        selector = action.get("selector", "")
        text = action.get("text", "")

        try:
            # First click on the input field
            await self.playwright_client.click_element(selector)
            await asyncio.sleep(0.1)

            # Type with realistic delays between keystrokes
            if len(text) > 1:
                # For longer text, simulate realistic typing
                for i, char in enumerate(text):
                    await self.playwright_client.type_text(selector, char)
                    if i < len(text) - 1:  # Don't delay after last character
                        keystroke_delay = random.uniform(
                            *self.interaction_timings["type"]["keystroke_delay"]
                        )
                        await asyncio.sleep(keystroke_delay / 1000)
            else:
                # For short text, type all at once
                await self.playwright_client.type_text(selector, text)

            return {
                "success": True,
                "action_type": "type",
                "selector": selector,
                "text": text,
                "character_count": len(text)
            }

        except Exception as e:
            return {
                "success": False,
                "action_type": "type",
                "selector": selector,
                "text": text,
                "error": str(e)
            }

    async def _execute_scroll(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Execute scrolling with realistic movement patterns."""
        direction = action.get("direction", "down")
        amount = action.get("amount", 500)

        try:
            # Break large scrolls into smaller, more realistic chunks
            if amount > 500:
                chunks = amount // 300
                chunk_size = amount // chunks

                for i in range(chunks):
                    await self.playwright_client.scroll_page(direction, chunk_size)
                    # Small delay between scroll chunks (realistic behavior)
                    await asyncio.sleep(random.uniform(0.1, 0.3))
            else:
                await self.playwright_client.scroll_page(direction, amount)

            return {
                "success": True,
                "action_type": "scroll",
                "direction": direction,
                "amount": amount
            }

        except Exception as e:
            return {
                "success": False,
                "action_type": "scroll",
                "direction": direction,
                "amount": amount,
                "error": str(e)
            }

    async def _measure_time_to_interactive(self, selector: str) -> Optional[float]:
        """
        Wait for element to become visible and interactive, then add user reaction time.
        Returns time it took for element to become interactive (excluding reaction time).
        """
        try:
            start_time = time.time()
            max_wait = 3  # Maximum 3 seconds to wait for element
            check_interval = 0.1  # Check every 100ms

            while (time.time() - start_time) < max_wait:
                # Check if element is visible AND interactive
                is_ready = await self.playwright_client.page.evaluate(f"""
                    (selector) => {{
                        const el = document.querySelector(selector);
                        if (!el) return false;

                        // Check visibility
                        const rect = el.getBoundingClientRect();
                        const isVisible = rect.width > 0 && rect.height > 0 &&
                                        window.getComputedStyle(el).visibility !== 'hidden' &&
                                        window.getComputedStyle(el).display !== 'none';

                        if (!isVisible) return false;

                        // Check if element is interactive
                        const isInteractiveElement = ['BUTTON', 'A', 'INPUT', 'SELECT', 'TEXTAREA'].includes(el.tagName);

                        // Check if element is not disabled
                        const isEnabled = !el.disabled && !el.hasAttribute('disabled');

                        // Check if pointer events are enabled
                        const style = window.getComputedStyle(el);
                        const pointerEventsEnabled = style.pointerEvents !== 'none';

                        return isInteractiveElement && isEnabled && pointerEventsEnabled;
                    }}
                """, selector)

                if is_ready:
                    time_to_interactive = time.time() - start_time
                    self.logger.info(
                        "Element became visible and interactive",
                        selector=selector[:50],
                        time_to_interactive=f"{time_to_interactive:.3f}s"
                    )

                    # User reaction time - 0.5s after seeing the element
                    await asyncio.sleep(0.5)
                    self.logger.debug("User reaction time complete", selector=selector[:50])

                    return time_to_interactive

                await asyncio.sleep(check_interval)

            # Timeout - element never became visible/interactive
            self.logger.warning(
                "Element did not become visible/interactive in time",
                selector=selector[:50],
                waited=f"{max_wait}s"
            )
            return None

        except Exception as e:
            self.logger.debug("Failed to wait for element interactivity", error=str(e))
            return None

    async def _pre_interaction_delay(self, action_type: str) -> None:
        """Apply realistic delay before interaction (user thinking/moving)."""
        try:
            timing_config = self.interaction_timings.get(action_type, {})
            pre_delay_range = timing_config.get("pre_delay", (100, 300))

            # Add some variability based on previous interactions
            base_delay = random.uniform(*pre_delay_range)

            # Adjust delay based on interaction history
            if len(self.interaction_history) > 0:
                last_interaction = self.interaction_history[-1]
                time_since_last = time.time() - last_interaction["timestamp"]

                # If previous interaction was recent, reduce delay
                if time_since_last < 1.0:
                    base_delay *= 0.7
                # If it's been a while, increase delay (user was reading/thinking)
                elif time_since_last > 5.0:
                    base_delay *= 1.3

            # Apply global delay settings
            total_delay = max(
                self.min_delay,
                min(self.max_delay, base_delay)
            )

            await asyncio.sleep(total_delay / 1000)

        except Exception as e:
            self.logger.error("Error in pre-interaction delay", error=str(e))
            # Fallback to basic delay
            await asyncio.sleep(0.5)

    async def _post_interaction_delay(self, action_type: str) -> None:
        """Apply realistic delay after interaction (user observing results)."""
        try:
            timing_config = self.interaction_timings.get(action_type, {})
            post_delay_range = timing_config.get("post_delay", (200, 500))

            delay = random.uniform(*post_delay_range)

            # Longer delay for actions that typically trigger significant changes
            if action_type in ["click", "type"]:
                delay *= 1.2

            await asyncio.sleep(delay / 1000)

        except Exception as e:
            self.logger.error("Error in post-interaction delay", error=str(e))
            # Fallback to basic delay
            await asyncio.sleep(0.3)

    def get_interaction_statistics(self) -> Dict[str, Any]:
        """Get statistics about recent interactions."""
        if not self.interaction_history:
            return {}

        try:
            total_interactions = len(self.interaction_history)
            successful_interactions = sum(
                1 for interaction in self.interaction_history
                if interaction.get("success", False)
            )

            action_types = {}
            total_execution_time = 0

            for interaction in self.interaction_history:
                action_type = interaction["action"].get("action", "unknown")
                action_types[action_type] = action_types.get(action_type, 0) + 1
                total_execution_time += interaction.get("execution_time", 0)

            return {
                "total_interactions": total_interactions,
                "successful_interactions": successful_interactions,
                "success_rate": successful_interactions / total_interactions if total_interactions > 0 else 0,
                "action_type_distribution": action_types,
                "average_execution_time": total_execution_time / total_interactions if total_interactions > 0 else 0,
                "total_execution_time": total_execution_time
            }

        except Exception as e:
            self.logger.error("Error calculating interaction statistics", error=str(e))
            return {"error": str(e)}

    async def wait_for_page_stability(self, timeout: int = 5) -> bool:
        """
        Wait for page to become stable (useful after interactions that cause changes).

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if page appears stable, False if timeout reached
        """
        try:
            start_time = time.time()

            # JavaScript to check if page is stable
            stability_script = """
            (() => {
                // Check for various indicators of page instability
                const indicators = {
                    pendingRequests: (window.performance?.getEntriesByType?.('xmlhttprequest')?.length || 0) > 0,
                    activeAnimations: document.getAnimations?.()?.length > 0,
                    loadingElements: document.querySelectorAll('[loading], .loading, .spinner').length > 0,
                    documentReady: document.readyState === 'complete'
                };

                // Page is stable if no indicators of instability
                const isStable = !indicators.pendingRequests &&
                                !indicators.activeAnimations &&
                                !indicators.loadingElements &&
                                indicators.documentReady;

                return {
                    stable: isStable,
                    indicators: indicators
                };
            })();
            """

            while time.time() - start_time < timeout:
                try:
                    result = await self.playwright_client.evaluate_script(stability_script)

                    if result and result.get("stable", False):
                        self.logger.debug("Page appears stable")
                        return True

                    # Short wait before checking again
                    await asyncio.sleep(0.5)

                except Exception:
                    # If we can't check stability, assume page is stable after a short wait
                    await asyncio.sleep(1)
                    return True

            self.logger.debug("Page stability timeout reached")
            return False

        except Exception as e:
            self.logger.error("Error waiting for page stability", error=str(e))
            return False