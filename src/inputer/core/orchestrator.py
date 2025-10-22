"""
Performance Orchestrator - Central coordination for INP hunting.
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Any

import structlog

from inputer.config.settings import Settings
from inputer.interfaces.playwright_client import PlaywrightClient
from inputer.core.element_discovery import ElementDiscoveryEngine
from inputer.core.interaction_engine import UserInteractionEngine
from inputer.core.performance_analyzer import PerformanceAnalyzer
from inputer.utils.data_export import DataExporter


logger = structlog.get_logger(__name__)


class PerformanceOrchestrator:
    """
    Main orchestrator that coordinates all components for automated INP hunting.

    Systematically tests interactive elements to find performance issues.
    """

    def __init__(self, settings: Settings):
        """Initialize the orchestrator with configuration."""
        self.settings = settings
        self.logger = logger.bind(component="orchestrator")

        # Core components
        self.playwright_client: Optional[PlaywrightClient] = None
        self.element_discovery: Optional[ElementDiscoveryEngine] = None
        self.interaction_engine: Optional[UserInteractionEngine] = None
        self.performance_analyzer: Optional[PerformanceAnalyzer] = None
        self.data_exporter: Optional[DataExporter] = None

        # State tracking
        self.current_session_id: Optional[str] = None
        self.is_initialized = False

    async def initialize(self) -> None:
        """Initialize all components and start services."""
        if self.is_initialized:
            return

        self.logger.info("Initializing performance orchestrator")

        try:
            # Generate session ID for this run
            from datetime import datetime
            self.current_session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

            # Initialize Playwright client with video recording config
            self.playwright_client = PlaywrightClient(self.settings.mcp_server)
            self.playwright_client.session_id = self.current_session_id
            self.playwright_client.performance_config = self.settings.performance
            await self.playwright_client.initialize()

            # Initialize other components
            self.element_discovery = ElementDiscoveryEngine(
                mcp_client=self.playwright_client,
                settings=self.settings.performance
            )

            self.interaction_engine = UserInteractionEngine(
                mcp_client=self.playwright_client,
                settings=self.settings.performance,
                session_id=self.current_session_id
            )

            self.performance_analyzer = PerformanceAnalyzer(
                mcp_client=self.playwright_client
            )

            self.data_exporter = DataExporter(
                settings=self.settings.data
            )

            self.is_initialized = True
            self.logger.info("Orchestrator initialization complete", session_id=self.current_session_id)

        except Exception as e:
            self.logger.error("Failed to initialize orchestrator", error=str(e))
            await self.cleanup()
            raise

    async def analyze_page(
        self,
        url: str,
        max_interactions: int = 10
    ) -> Dict[str, Any]:
        """
        Analyze a single page for INP issues using the main automation loop.

        Args:
            url: URL to analyze
            max_interactions: Maximum number of interactions to perform

        Returns:
            Dict containing analysis results
        """
        if not self.is_initialized:
            raise RuntimeError("Orchestrator not initialized")

        session_id = f"session_{int(time.time())}"
        self.current_session_id = session_id
        session_logger = self.logger.bind(session_id=session_id, url=url)

        session_logger.info("Starting page analysis")

        results = {
            "url": url,
            "session_id": session_id,
            "timestamp": time.time(),
            "interactions": [],
            "performance_data": [],
            "worst_inp": None,
            "worst_element": None,
            "total_interactions": 0,
            "errors": []
        }

        try:
            # Step 1: Initial Page Load & Baseline
            await self._perform_initial_load(url, results)

            # Step 2: Observe-Reason-Act Cycle
            await self._perform_interaction_cycle(
                url=url,
                max_interactions=max_interactions,
                results=results
            )

            # Step 3: Final Analysis
            await self._perform_final_analysis(results)

            session_logger.info(
                "Page analysis complete",
                total_interactions=results["total_interactions"],
                worst_inp=results["worst_inp"]
            )

        except Exception as e:
            session_logger.error("Error during page analysis", error=str(e))
            results["errors"].append({
                "type": "analysis_error",
                "message": str(e),
                "timestamp": time.time()
            })
            raise

        return results

    async def _perform_initial_load(self, url: str, results: Dict) -> None:
        """Perform initial page load and baseline measurement."""
        session_logger = self.logger.bind(url=url)
        session_logger.info("Performing initial page load")

        try:
            # Navigate to page
            await self.playwright_client.navigate_page(url)

            # Start performance trace
            await self.performance_analyzer.start_trace()

            # Wait for initial content
            await asyncio.sleep(2)  # Basic wait for initial rendering

            # Stop trace and get baseline
            trace_data = await self.performance_analyzer.stop_trace()

            baseline_metrics = await self.performance_analyzer.analyze_trace(trace_data)

            results["baseline_metrics"] = baseline_metrics
            session_logger.info("Initial load complete", metrics=baseline_metrics)

        except Exception as e:
            session_logger.error("Failed initial page load", error=str(e))
            raise

    async def _perform_interaction_cycle(
        self,
        url: str,
        max_interactions: int,
        results: Dict
    ) -> None:
        """Perform the main Observe-Reason-Act cycle."""
        session_logger = self.logger.bind(url=url)

        for interaction_num in range(max_interactions):
            cycle_logger = session_logger.bind(interaction=interaction_num + 1)
            cycle_logger.info("Starting interaction cycle")

            try:
                # OBSERVE: Capture current browser state
                browser_state = await self._observe_browser_state()

                # REASON: Use LLM to decide next action
                next_action = await self._reason_next_action(
                    browser_state=browser_state,
                    interaction_history=results["interactions"]
                )

                if not next_action:
                    cycle_logger.info("No more viable actions, ending cycle")
                    break

                # ACT: Execute the chosen action
                interaction_result = await self._act_on_decision(next_action)

                # MEASURE: Analyze performance impact
                performance_data = await self._measure_performance_impact()

                # Record results
                interaction_record = {
                    "interaction_num": interaction_num + 1,
                    "action": next_action,
                    "result": interaction_result,
                    "performance": performance_data,
                    "timestamp": time.time()
                }

                results["interactions"].append(interaction_record)
                results["performance_data"].append(performance_data)
                results["total_interactions"] += 1

                # Update worst INP if applicable
                if performance_data.get("inp_score"):
                    if (not results["worst_inp"] or
                        performance_data["inp_score"] > results["worst_inp"]):
                        results["worst_inp"] = performance_data["inp_score"]
                        results["worst_element"] = next_action.get("selector")

                cycle_logger.info(
                    "Interaction cycle complete",
                    action=next_action.get("action"),
                    inp_score=performance_data.get("inp_score")
                )

            except Exception as e:
                cycle_logger.error("Error in interaction cycle", error=str(e))
                results["errors"].append({
                    "type": "interaction_error",
                    "interaction_num": interaction_num + 1,
                    "message": str(e),
                    "timestamp": time.time()
                })
                continue

    async def _observe_browser_state(self) -> Dict[str, Any]:
        """Capture current browser state for LLM reasoning."""
        try:
            # Discover interactive elements
            elements = await self.element_discovery.discover_interactive_elements()

            # Get screenshot (optional, for debugging)
            screenshot_path = None
            if self.settings.performance.screenshot_capture:
                screenshot_path = await self.playwright_client.take_screenshot()

            # Get console messages
            console_messages = await self.playwright_client.get_console_messages()

            # Get current page info
            page_info = await self.playwright_client.get_page_info()

            return {
                "elements": elements,
                "screenshot_path": screenshot_path,
                "console_messages": console_messages,
                "page_info": page_info,
                "timestamp": time.time()
            }

        except Exception as e:
            self.logger.error("Failed to observe browser state", error=str(e))
            raise

    async def _reason_next_action(
        self,
        browser_state: Dict[str, Any],
        interaction_history: List[Dict]
    ) -> Optional[Dict[str, Any]]:
        """Use LLM to determine the next best action."""
        try:
            # Prepare context for LLM
            context = self._prepare_llm_context(browser_state, interaction_history)

            # Query LLM for next action
            response = await self.llm_client.get_next_action(context)

            return response

        except Exception as e:
            self.logger.error("Failed to reason next action", error=str(e))
            return None

    async def _act_on_decision(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the LLM's chosen action."""
        try:
            result = await self.interaction_engine.execute_interaction(action)
            return result

        except Exception as e:
            self.logger.error("Failed to execute action", action=action, error=str(e))
            raise

    async def _measure_performance_impact(self) -> Dict[str, Any]:
        """Measure the performance impact of the last interaction."""
        try:
            # Start trace before measuring
            await self.performance_analyzer.start_trace()

            # Small delay to capture interaction effects
            await asyncio.sleep(1)

            # Stop trace and analyze
            trace_data = await self.performance_analyzer.stop_trace()
            performance_metrics = await self.performance_analyzer.analyze_trace(trace_data)

            return performance_metrics

        except Exception as e:
            self.logger.error("Failed to measure performance", error=str(e))
            return {}

    def _prepare_llm_context(
        self,
        browser_state: Dict[str, Any],
        interaction_history: List[Dict]
    ) -> Dict[str, Any]:
        """Prepare context data for LLM decision making."""
        return {
            "available_elements": browser_state.get("elements", []),
            "page_info": browser_state.get("page_info", {}),
            "console_messages": browser_state.get("console_messages", []),
            "previous_interactions": interaction_history[-5:],  # Last 5 interactions
            "goal": "Find interactive elements that cause high INP scores"
        }

    async def _perform_final_analysis(self, results: Dict) -> None:
        """Perform final analysis and summary of results."""
        try:
            # Calculate summary statistics
            all_inp_scores = [
                perf.get("inp_score", 0)
                for perf in results["performance_data"]
                if perf.get("inp_score")
            ]

            if all_inp_scores:
                results["summary"] = {
                    "total_interactions": len(all_inp_scores),
                    "average_inp": sum(all_inp_scores) / len(all_inp_scores),
                    "worst_inp": max(all_inp_scores),
                    "best_inp": min(all_inp_scores)
                }

            self.logger.info("Final analysis complete", summary=results.get("summary"))

        except Exception as e:
            self.logger.error("Failed final analysis", error=str(e))

    async def generate_final_report(
        self,
        results: Dict[str, Any],
        output_dir: str
    ) -> Path:
        """Generate and export final report."""
        try:
            report_path = await self.data_exporter.export_results(
                results=results,
                output_dir=output_dir
            )

            self.logger.info("Report generated", path=str(report_path))
            return report_path

        except Exception as e:
            self.logger.error("Failed to generate report", error=str(e))
            raise

    async def cleanup(self) -> None:
        """Clean up resources and shut down services."""
        self.logger.info("Cleaning up orchestrator")

        try:
            if self.playwright_client:
                await self.playwright_client.cleanup()

        except Exception as e:
            self.logger.error("Error during cleanup", error=str(e))

        self.is_initialized = False
        self.logger.info("Cleanup complete")