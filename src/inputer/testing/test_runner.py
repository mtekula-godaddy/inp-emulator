"""
Test Runner - Run performance analysis without LLM dependency.
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional

import structlog

from inputer.config.settings import Settings
from inputer.core.orchestrator import PerformanceOrchestrator
from inputer.core.page_analyzer import PageAnalyzer


logger = structlog.get_logger(__name__)


class TestRunner:
    """
    Test runner for performance analysis without LLM dependency.

    Supports different testing modes:
    - mock: Uses mock LLM with various strategies
    - deterministic: Uses predefined action sequences
    - element_scan: Tests all discovered elements systematically
    """

    def __init__(self, settings: Settings, test_mode: str = "mock"):
        """
        Initialize test runner.

        Args:
            settings: Application settings
            test_mode: Test mode ("mock", "deterministic", "element_scan")
        """
        self.settings = settings
        self.test_mode = test_mode
        self.logger = logger.bind(component="test_runner", mode=test_mode)

    async def run_test_analysis(
        self,
        urls: List[str],
        strategy: str = "priority",
        max_interactions: int = 10,
        output_dir: str = "./test_results",
        skip_header: bool = True
    ) -> Dict[str, any]:
        """
        Run performance analysis in test mode.

        Args:
            urls: URLs to analyze
            strategy: Testing strategy for mock LLM
            max_interactions: Maximum interactions per page
            output_dir: Output directory for results
            skip_header: Exclude elements within header tags (default: True)

        Returns:
            Test results and analysis
        """
        self.logger.info(
            "Starting test analysis",
            urls=urls,
            strategy=strategy,
            mode=self.test_mode
        )

        # Create custom orchestrator with mock LLM
        orchestrator = await self._create_test_orchestrator(strategy)

        try:
            await orchestrator.initialize()

            results = {}
            for url in urls:
                self.logger.info("Testing URL", url=url)

                try:
                    if self.test_mode == "element_scan":
                        result = await self._run_element_scan(orchestrator, url, max_interactions, skip_header)
                    else:
                        result = await orchestrator.analyze_page(url, max_interactions)

                    results[url] = result
                    self.logger.info(
                        "URL test complete",
                        url=url,
                        interactions=result.get("total_interactions", 0)
                    )

                except Exception as e:
                    self.logger.error("Error testing URL", url=url, error=str(e))
                    results[url] = {"error": str(e)}

            # Generate test report
            report_path = await self._generate_test_report(results, output_dir, strategy)

            return {
                "results": results,
                "report_path": report_path,
                "test_mode": self.test_mode,
                "strategy": strategy,
                "summary": self._generate_test_summary(results)
            }

        finally:
            await orchestrator.cleanup()

    async def _create_test_orchestrator(self, strategy: str) -> PerformanceOrchestrator:
        """Create orchestrator with Playwright client."""

        # Create modified orchestrator with test-specific data directory
        test_settings = self.settings
        test_settings.data.output_dir = "./test_results"
        orchestrator = PerformanceOrchestrator(test_settings)

        # Generate session ID for this test run
        from datetime import datetime
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        orchestrator.current_session_id = session_id

        # Initialize Playwright client with video recording config and test data paths
        from inputer.interfaces.playwright_client import PlaywrightClient
        playwright_client = PlaywrightClient(test_settings.mcp_server)
        playwright_client.session_id = session_id
        playwright_client.performance_config = test_settings.performance
        playwright_client.data_dir = "test_results"  # Store all test artifacts in test_results/
        await playwright_client.initialize()
        orchestrator.playwright_client = playwright_client

        # Initialize element discovery with Playwright
        from inputer.core.element_discovery import ElementDiscoveryEngine
        orchestrator.element_discovery = ElementDiscoveryEngine(
            mcp_client=playwright_client,
            settings=self.settings.performance
        )

        # Initialize interaction engine with Playwright
        from inputer.core.interaction_engine import UserInteractionEngine
        orchestrator.interaction_engine = UserInteractionEngine(
            mcp_client=playwright_client,
            settings=self.settings.performance,
            session_id=session_id
        )

        # Initialize performance analyzer with Playwright
        from inputer.core.performance_analyzer import PerformanceAnalyzer
        orchestrator.performance_analyzer = PerformanceAnalyzer(
            mcp_client=playwright_client
        )

        # Initialize data exporter
        from inputer.utils.data_export import DataExporter
        orchestrator.data_exporter = DataExporter(self.settings.data)

        # Mark as initialized to skip the normal initialization
        orchestrator.is_initialized = True

        return orchestrator

    async def _run_element_scan(
        self,
        orchestrator: PerformanceOrchestrator,
        url: str,
        max_interactions: int,
        skip_header: bool = True
    ) -> Dict[str, any]:
        """
        Run systematic element scan without LLM.

        Tests all discovered elements in priority order.

        Args:
            orchestrator: Performance orchestrator instance
            url: URL to test
            max_interactions: Maximum number of elements to test
            skip_header: Exclude elements within header tags (default: True)
        """
        session_id = f"scan_{int(time.time())}"

        results = {
            "url": url,
            "session_id": session_id,
            "test_mode": "element_scan",
            "interactions": [],
            "performance_data": [],
            "total_interactions": 0,
            "worst_inp": None,
            "worst_element": None
        }

        try:
            # Initial navigation - waits for domcontentloaded (DOM ready)
            await orchestrator.playwright_client.navigate_page(url)

            # Minimal wait - we want to catch INP while page is still loading/settling
            # Real users click as soon as they see interactive elements, not after everything loads
            await asyncio.sleep(0.3)

            # Analyze page characteristics to calculate input delay coefficient
            page_analyzer = PageAnalyzer()
            # Get a baseline performance measurement for coefficient calculation
            baseline_perf = await orchestrator._measure_performance_impact()
            page_analysis = await page_analyzer.analyze_page(
                orchestrator.playwright_client.page,
                url,
                baseline_perf
            )

            inp_coefficient = page_analysis["coefficient"]
            self.logger.info(
                "Page analysis complete",
                url=url,
                coefficient=inp_coefficient,
                frameworks=page_analysis["frameworks"],
                js_size_kb=page_analysis["js_total_size_kb"],
                third_party_domains=page_analysis["third_party_domains"],
                long_tasks=page_analysis["long_tasks_count"]
            )

            # Discover all elements
            elements = await orchestrator.element_discovery.discover_interactive_elements(skip_nav_footer=skip_header)

            if not elements:
                self.logger.warning("No elements discovered for scanning", url=url)
                return results

            # Elements are already sorted and filtered by element_discovery
            # Just deduplicate by selector - keep only first occurrence of each unique selector
            seen_selectors = set()
            unique_elements = []
            for element in elements:
                selector = element.get("selector", "")
                if selector not in seen_selectors:
                    seen_selectors.add(selector)
                    unique_elements.append(element)

            # Test each element up to max_interactions
            for i, element in enumerate(unique_elements[:max_interactions]):
                interaction_num = i + 1
                selector = element.get("selector", "")

                self.logger.info(
                    "Testing element",
                    interaction=interaction_num,
                    selector=selector,
                    inp_potential=element.get("inp_potential_score")
                )

                # Reload page to reset state before each interaction
                # navigate_page now waits for LCP automatically
                await orchestrator.playwright_client.navigate_page(url)

                # Get element label for overlay
                element_label = (element.get("label", "") or element.get("text", "") or selector[:30]).replace("'", "\\'")

                # Add visible interaction counter overlay to video (bottom-right)
                await orchestrator.playwright_client.page.evaluate(f"""
                    () => {{
                        const overlay = document.createElement('div');
                        overlay.id = 'test-interaction-overlay';
                        overlay.style.position = 'fixed';
                        overlay.style.bottom = '10px';
                        overlay.style.right = '10px';
                        overlay.style.backgroundColor = 'rgba(0, 0, 0, 0.8)';
                        overlay.style.color = 'white';
                        overlay.style.padding = '10px 20px';
                        overlay.style.borderRadius = '5px';
                        overlay.style.fontSize = '18px';
                        overlay.style.fontFamily = 'monospace';
                        overlay.style.zIndex = '999999';
                        overlay.innerHTML = '<div>#{interaction_num}: {element_label}</div>';
                        document.body.appendChild(overlay);
                    }}
                """)

                # Generate action based on element type
                action = self._generate_scan_action(element)

                try:
                    # Execute interaction
                    interaction_result = await orchestrator.interaction_engine.execute_interaction(action)

                    # Measure performance
                    performance_data = await orchestrator._measure_performance_impact()

                    # Calculate estimated real-world INP using coefficient
                    measured_inp = interaction_result.get("inp_ms")
                    if measured_inp is not None:
                        if "inp" not in performance_data:
                            performance_data["inp"] = {}

                        # Calculate estimated real-world INP
                        estimated_inp = round(measured_inp * inp_coefficient, 1)

                        self.logger.info(
                            "INP calculated",
                            selector=selector[:50],
                            measured_inp=measured_inp,
                            coefficient=inp_coefficient,
                            estimated_inp=estimated_inp
                        )

                        # Store both measured and estimated values
                        performance_data["inp"]["measured_score"] = measured_inp
                        performance_data["inp"]["estimated_score"] = estimated_inp
                        performance_data["inp"]["coefficient"] = inp_coefficient
                        performance_data["inp"]["score"] = estimated_inp  # Use estimated for classification

                        # Update classification based on estimated real-world INP
                        if estimated_inp < 200:
                            performance_data["inp"]["classification"] = "good"
                        elif estimated_inp < 500:
                            performance_data["inp"]["classification"] = "needs_improvement"
                        else:
                            performance_data["inp"]["classification"] = "poor"

                        self.logger.debug(
                            "INP classification complete",
                            selector=selector[:50],
                            measured=measured_inp,
                            estimated=estimated_inp,
                            classification=performance_data["inp"]["classification"]
                        )

                    # Record results
                    interaction_record = {
                        "interaction_num": interaction_num,
                        "element": element,
                        "action": action,
                        "result": interaction_result,
                        "performance": performance_data,
                        "timestamp": time.time()
                    }

                    results["interactions"].append(interaction_record)
                    results["performance_data"].append(performance_data)
                    results["total_interactions"] += 1

                    # Update worst INP (use estimated INP for comparison)
                    estimated_inp_value = performance_data.get("inp", {}).get("estimated_score")
                    if estimated_inp_value and (not results["worst_inp"] or estimated_inp_value > results["worst_inp"]):
                        results["worst_inp"] = estimated_inp_value
                        results["worst_element"] = selector

                except Exception as e:
                    self.logger.error(
                        "Error testing element",
                        selector=selector,
                        error=str(e)
                    )
                    continue

            return results

        except Exception as e:
            self.logger.error("Error in element scan", url=url, error=str(e))
            results["error"] = str(e)
            return results

    def _generate_scan_action(self, element: Dict[str, any]) -> Dict[str, any]:
        """Generate action for element scanning."""
        elem_type = element.get("type", "").lower()
        selector = element.get("selector", "")

        if "input" in elem_type and "text" in elem_type:
            return {
                "action": "type",
                "selector": selector,
                "text": "test"
            }
        elif "select" in elem_type or "dropdown" in elem_type:
            return {
                "action": "click",
                "selector": selector
            }
        else:
            return {
                "action": "click",
                "selector": selector
            }

    async def _generate_test_report(
        self,
        results: Dict[str, any],
        output_dir: str,
        strategy: str
    ) -> Path:
        """Generate test report."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Use orchestrator's data exporter
        from inputer.utils.data_export import DataExporter
        exporter = DataExporter(self.settings.data)

        # Export results and get actual report path
        report_path = await exporter.export_results(results, str(output_path))

        return report_path

    def _generate_test_summary(self, results: Dict[str, any]) -> Dict[str, any]:
        """Generate summary of test results."""
        summary = {
            "total_urls": len(results),
            "successful_urls": 0,
            "total_interactions": 0,
            "worst_inp_overall": None,
            "worst_url": None
        }

        for url, result in results.items():
            if "error" not in result:
                summary["successful_urls"] += 1
                summary["total_interactions"] += result.get("total_interactions", 0)

                worst_inp = result.get("worst_inp")
                if worst_inp and (not summary["worst_inp_overall"] or worst_inp > summary["worst_inp_overall"]):
                    summary["worst_inp_overall"] = worst_inp
                    summary["worst_url"] = url

        return summary


# CLI function for running tests
async def run_performance_test(
    urls: List[str],
    test_mode: str = "mock",
    strategy: str = "priority",
    max_interactions: int = 3,
    config_file: Optional[str] = None,
    skip_header: bool = True
):
    """
    CLI function to run performance tests without LLM.

    Args:
        urls: URLs to test
        test_mode: Test mode ("mock", "deterministic", "element_scan")
        strategy: Strategy for mock LLM
        max_interactions: Maximum interactions per page (default: 2)
        config_file: Optional configuration file
        skip_header: Exclude elements within header tags (default: True)
    """
    # Load settings
    settings = Settings(config_file=config_file)

    # Create test runner
    runner = TestRunner(settings, test_mode=test_mode)

    # Run tests
    test_results = await runner.run_test_analysis(
        urls=urls,
        strategy=strategy,
        max_interactions=max_interactions,
        skip_header=skip_header
    )

    # Print summary
    summary = test_results["summary"]
    print(f"\n🧪 Test Results Summary")
    print(f"Test Mode: {test_mode}")
    print(f"Strategy: {strategy}")
    print(f"URLs Tested: {summary['successful_urls']}/{summary['total_urls']}")
    print(f"Total Interactions: {summary['total_interactions']}")

    if summary["worst_inp_overall"]:
        print(f"Worst INP: {summary['worst_inp_overall']}ms on {summary['worst_url']}")

    print(f"\n📄 Report saved to: {test_results['report_path']}")

    return test_results


def main():
    """CLI entry point for test runner."""
    import sys
    import argparse
    import os

    parser = argparse.ArgumentParser(
        description="Run INP performance tests on web pages",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test single URL (skip header, 2 elements)
  python test_runner.py https://example.com element_scan priority

  # Test single URL with 5 elements
  python test_runner.py https://example.com element_scan priority 5

  # Test single URL, include header elements
  python test_runner.py https://example.com element_scan priority --include-header

  # Test multiple URLs from file
  python test_runner.py urls.txt element_scan priority

  # Test file with 5 elements per URL, include headers
  python test_runner.py urls.txt element_scan priority 5 --include-header
        """
    )

    parser.add_argument("url_or_file", help="URL to test or path to file containing URLs (one per line)")
    parser.add_argument("test_mode", nargs="?", default="mock",
                       help="Test mode: mock, deterministic, element_scan (default: mock)")
    parser.add_argument("strategy", nargs="?", default="priority",
                       help="Strategy: priority, sequential, random, problematic (default: priority)")
    parser.add_argument("max_interactions", nargs="?", type=int, default=3,
                       help="Number of elements to test per page (default: 3)")

    parser.add_argument("--include-header", action="store_true", dest="include_header",
                       help="Include header elements in testing (default: exclude)")
    parser.add_argument("--skip-header", action="store_false", dest="include_header",
                       help="Exclude header elements from testing (default)")
    parser.set_defaults(include_header=False)

    args = parser.parse_args()

    # Determine if input is a file or URL
    urls = []
    if os.path.isfile(args.url_or_file):
        # Read URLs from file
        with open(args.url_or_file, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip empty lines, comments, and header lines
                if line and not line.startswith('#') and line.startswith('http'):
                    urls.append(line)
    else:
        # Single URL
        urls = [args.url_or_file]

    asyncio.run(run_performance_test(
        urls=urls,
        test_mode=args.test_mode,
        strategy=args.strategy,
        max_interactions=args.max_interactions,
        skip_header=not args.include_header
    ))


if __name__ == "__main__":
    main()