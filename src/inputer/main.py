#!/usr/bin/env python3
"""
Inputer Performance Monitor - Main Orchestrator
Coordinates Chrome DevTools MCP and LLM agent for automated INP hunting.
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional

import click
from rich.console import Console
from rich.logging import RichHandler

# Add src/python to Python path
sys.path.insert(0, str(Path(__file__).parent))

from inputer.config.settings import Settings
from inputer.core.orchestrator import PerformanceOrchestrator
from inputer.utils.logger import setup_logging
from inputer.testing.test_runner import run_performance_test


console = Console()


async def main_automation_loop(
    orchestrator: PerformanceOrchestrator,
    target_urls: List[str],
    max_interactions: int = 10
) -> Dict:
    """
    Main INP hunting loop - implements the Observe-Reason-Act cycle.

    Args:
        orchestrator: The main orchestrator instance
        target_urls: List of URLs to test
        max_interactions: Maximum interactions per page

    Returns:
        Dict containing results for all tested URLs
    """
    results = {}

    for url in target_urls:
        console.print(f"🔍 Starting INP analysis for: {url}")

        try:
            # Step 1: Initial Page Load & Baseline
            page_result = await orchestrator.analyze_page(
                url=url,
                max_interactions=max_interactions
            )
            results[url] = page_result

            console.print(f"✅ Completed analysis for: {url}")
            console.print(f"   📊 Total interactions: {page_result.get('total_interactions', 0)}")
            console.print(f"   ⚡ Worst INP: {page_result.get('worst_inp', 'N/A')}ms")

        except Exception as e:
            console.print(f"❌ Error analyzing {url}: {e}")
            results[url] = {"error": str(e)}

    return results


@click.command()
@click.option(
    "--urls",
    "-u",
    multiple=True,
    required=True,
    help="URLs to analyze for INP issues"
)
@click.option(
    "--max-interactions",
    "-i",
    default=10,
    help="Maximum interactions per page"
)
@click.option(
    "--output-dir",
    "-o",
    default="./data/results",
    help="Output directory for results"
)
@click.option(
    "--config-file",
    "-c",
    help="Path to configuration file"
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose logging"
)
@click.option(
    "--test-mode",
    "-t",
    type=click.Choice(["mock", "deterministic", "element_scan"]),
    help="Run in test mode without LLM (mock, deterministic, element_scan)"
)
@click.option(
    "--test-strategy",
    "-s",
    type=click.Choice(["priority", "sequential", "random", "problematic"]),
    default="priority",
    help="Strategy for test mode (priority, sequential, random, problematic)"
)
def cli_main(
    urls: tuple,
    max_interactions: int,
    output_dir: str,
    config_file: Optional[str],
    verbose: bool,
    test_mode: Optional[str],
    test_strategy: str
):
    """
    Inputer Performance Monitor - Automated INP hunting using Chrome DevTools MCP

    Examples:
        # Standard analysis with LLM
        python main.py -u https://example.com

        # Test mode without LLM dependency
        python main.py -u https://example.com --test-mode mock --test-strategy priority

        # Element scan mode (tests all elements systematically)
        python main.py -u https://example.com --test-mode element_scan

        # Multiple URLs with custom config
        python main.py -u https://site1.com -u https://site2.com -c config/aws.yaml -v
    """
    async def async_main():
        # Setup logging
        log_level = logging.DEBUG if verbose else logging.INFO
        setup_logging(log_level)
        logger = logging.getLogger(__name__)

        console.print("🚀 [bold blue]Inputer Performance Monitor[/bold blue]")
        console.print(f"📋 Analyzing {len(urls)} URL(s)")

        if test_mode:
            console.print(f"🧪 [yellow]Running in test mode: {test_mode}[/yellow]")
            console.print(f"📊 Test strategy: {test_strategy}")

        try:
            if test_mode:
                # Run in test mode without LLM
                test_results = await run_performance_test(
                    urls=list(urls),
                    test_mode=test_mode,
                    strategy=test_strategy,
                    max_interactions=max_interactions,
                    config_file=config_file
                )

                console.print(f"✅ [bold green]Test analysis complete![/bold green]")
                console.print(f"📄 Results: {test_results.get('summary', {})}")

            else:
                # Standard analysis with LLM
                # Load configuration
                settings = Settings(config_file=config_file)

                # Initialize orchestrator
                orchestrator = PerformanceOrchestrator(settings)

                # Start services
                console.print("🔧 Initializing services...")
                await orchestrator.initialize()

                # Run main automation loop
                console.print("🎯 Starting performance analysis...")
                results = await main_automation_loop(
                    orchestrator=orchestrator,
                    target_urls=list(urls),
                    max_interactions=max_interactions
                )

                # Generate reports
                console.print("📊 Generating reports...")
                report_path = await orchestrator.generate_final_report(
                    results=results,
                    output_dir=output_dir
                )

                console.print(f"✅ [bold green]Analysis complete![/bold green]")
                console.print(f"📄 Report saved to: {report_path}")

        except Exception as e:
            logger.exception("Fatal error in main execution")
            console.print(f"❌ [bold red]Fatal error:[/bold red] {e}")
            sys.exit(1)

        finally:
            # Cleanup
            console.print("🧹 Cleaning up...")
            if 'orchestrator' in locals():
                await orchestrator.cleanup()

    # Run the async main function
    asyncio.run(async_main())


def main():
    """Entry point for the application."""
    try:
        cli_main()
    except KeyboardInterrupt:
        console.print("\n⚠️ [yellow]Interrupted by user[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"❌ [bold red]Unexpected error:[/bold red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()