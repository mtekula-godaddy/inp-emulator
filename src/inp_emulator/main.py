#!/usr/bin/env python3
"""
INP Emulator - Main Orchestrator
Automated INP hunting using Chrome DevTools and systematic element testing.
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

from inp_emulator.config.settings import Settings
from inp_emulator.utils.logger import setup_logging
from inp_emulator.testing.test_runner import run_performance_test


console = Console()


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
def cli_main(
    urls: tuple,
    max_interactions: int,
    output_dir: str,
    config_file: Optional[str],
    verbose: bool
):
    """
    INP Emulator - Automated INP hunting using Chrome DevTools

    Examples:
        # Test a single URL
        python main.py -u https://example.com

        # Test with more interactions
        python main.py -u https://example.com -i 5

        # Multiple URLs with custom config
        python main.py -u https://site1.com -u https://site2.com -c config/config.yaml -v
    """
    async def async_main():
        # Setup logging
        log_level = logging.DEBUG if verbose else logging.INFO
        setup_logging(log_level)
        logger = logging.getLogger(__name__)

        console.print("🚀 [bold blue]INP Emulator[/bold blue]")
        console.print(f"📋 Analyzing {len(urls)} URL(s)")

        try:
            # Run performance test
            test_results = await run_performance_test(
                urls=list(urls),
                max_interactions=max_interactions,
                config_file=config_file
            )

            console.print(f"✅ [bold green]Analysis complete![/bold green]")
            console.print(f"📄 Results: {test_results.get('summary', {})}")

        except Exception as e:
            logger.exception("Fatal error in main execution")
            console.print(f"❌ [bold red]Fatal error:[/bold red] {e}")
            sys.exit(1)

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