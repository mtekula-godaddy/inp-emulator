"""
Data Export utilities for performance analysis results.
"""

import csv
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple
import statistics

import pandas as pd
import structlog

from inputer.config.settings import DataConfig


logger = structlog.get_logger(__name__)


class DataExporter:
    """
    Export performance analysis results to various formats.

    Supports:
    - JSON format for programmatic use
    - CSV format for spreadsheet analysis
    - HTML reports for human readability
    - Summary statistics and insights
    """

    def __init__(self, settings: DataConfig):
        """Initialize the data exporter."""
        self.settings = settings
        self.logger = logger.bind(component="data_exporter")

        # Ensure output directory exists
        self.output_dir = Path(settings.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def export_results(
        self,
        results: Dict[str, Any],
        output_dir: str
    ) -> Path:
        """
        Export analysis results to configured formats.

        Args:
            results: Analysis results from orchestrator
            output_dir: Directory to save results

        Returns:
            Path to the main report file
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_filename = f"inputer_report_{timestamp}"

        self.logger.info("Exporting results", output_dir=str(output_path))

        try:
            main_report_path = None

            # Export to each requested format
            for format_type in self.settings.report_formats:
                if format_type.lower() == "json":
                    path = await self._export_json(results, output_path, base_filename)
                    if not main_report_path:
                        main_report_path = path

                elif format_type.lower() == "csv":
                    await self._export_csv(results, output_path, base_filename)
                    # Also export executive summary CSV for multi-URL analysis
                    if len(results) > 1:
                        await self._export_executive_summary_csv(results, output_path, base_filename)

                elif format_type.lower() == "html":
                    path = await self._export_html(results, output_path, base_filename)
                    if not main_report_path:
                        main_report_path = path

            # Create summary file
            await self._create_summary(results, output_path, base_filename)

            self.logger.info("Export complete", main_report=str(main_report_path))
            return main_report_path or output_path / f"{base_filename}.json"

        except Exception as e:
            self.logger.error("Failed to export results", error=str(e))
            raise

    async def _export_json(
        self,
        results: Dict[str, Any],
        output_path: Path,
        base_filename: str
    ) -> Path:
        """Export results to JSON format."""
        try:
            json_path = output_path / f"{base_filename}.json"

            # Prepare data for JSON export
            json_data = {
                "metadata": {
                    "export_timestamp": time.time(),
                    "export_date": datetime.now().isoformat(),
                    "tool_version": "1.0.0",
                    "format_version": "1.0"
                },
                "results": results,
                "summary": self._generate_summary_stats(results)
            }

            # Write JSON file
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)

            self.logger.debug("JSON export complete", path=str(json_path))
            return json_path

        except Exception as e:
            self.logger.error("Failed to export JSON", error=str(e))
            raise

    async def _export_csv(
        self,
        results: Dict[str, Any],
        output_path: Path,
        base_filename: str
    ) -> Path:
        """Export results to CSV format."""
        try:
            csv_path = output_path / f"{base_filename}.csv"

            # Flatten results for CSV export
            csv_rows = []

            for url, url_results in results.items():
                if isinstance(url_results, dict) and "interactions" in url_results:
                    interactions = url_results.get("interactions", [])

                    for interaction in interactions:
                        row = self._flatten_interaction_for_csv(url, interaction)
                        csv_rows.append(row)

            # Write CSV file
            if csv_rows:
                fieldnames = csv_rows[0].keys() if csv_rows else []

                with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(csv_rows)

            self.logger.debug("CSV export complete", path=str(csv_path))
            return csv_path

        except Exception as e:
            self.logger.error("Failed to export CSV", error=str(e))
            raise

    async def _export_executive_summary_csv(
        self,
        results: Dict[str, Any],
        output_path: Path,
        base_filename: str
    ) -> Path:
        """Export executive summary CSV - one row per URL for quick scanning."""
        try:
            csv_path = output_path / f"{base_filename}_executive_summary.csv"

            # Detect outliers first
            outlier_data, element_aggregation = self._detect_outliers(results)

            # Build summary rows - one per URL
            summary_rows = []

            for url, url_results in results.items():
                if isinstance(url_results, dict) and "interactions" in url_results:
                    interactions = url_results.get("interactions", [])

                    # Calculate per-URL metrics
                    total_interactions = len(interactions)
                    successful = sum(1 for i in interactions if i.get("result", {}).get("success", False))
                    success_rate = (successful / total_interactions * 100) if total_interactions > 0 else 0

                    # Get INP scores
                    inp_scores = [
                        i.get("performance", {}).get("inp", {}).get("score")
                        for i in interactions
                        if i.get("performance", {}).get("inp", {}).get("score") is not None
                    ]

                    avg_inp = statistics.mean(inp_scores) if inp_scores else None
                    worst_inp = max(inp_scores) if inp_scores else None

                    # Count INP classifications
                    good_count = sum(1 for i in interactions
                                   if i.get("performance", {}).get("inp", {}).get("classification") == "good")
                    needs_improvement_count = sum(1 for i in interactions
                                                 if i.get("performance", {}).get("inp", {}).get("classification") == "needs_improvement")
                    poor_count = sum(1 for i in interactions
                                   if i.get("performance", {}).get("inp", {}).get("classification") == "poor")

                    # Get worst element details
                    worst_element_selector = url_results.get("worst_element", "")
                    worst_element_text = ""

                    # Find the interaction with worst INP to get element label
                    for interaction in interactions:
                        if interaction.get("action", {}).get("selector") == worst_element_selector:
                            element = interaction.get("element", {})
                            worst_element_text = element.get("label", "") or element.get("text", "")
                            break

                    # Get outlier flag
                    outlier_info = outlier_data.get(url, {})
                    outlier_flag = outlier_info.get('flag', '✅')

                    row = {
                        "url": url,
                        "outlier_flag": outlier_flag,
                        "total_interactions": total_interactions,
                        "success_rate_pct": f"{success_rate:.1f}",
                        "worst_inp_ms": worst_inp if worst_inp else "",
                        "worst_inp_element": worst_element_selector,
                        "worst_element_text": worst_element_text,
                        "avg_inp_ms": f"{avg_inp:.1f}" if avg_inp else "",
                        "poor_count": poor_count,
                        "needs_improvement_count": needs_improvement_count,
                        "good_count": good_count
                    }

                    summary_rows.append(row)

            # Sort by worst INP (descending) for easy scanning
            summary_rows.sort(key=lambda x: float(x["worst_inp_ms"]) if x["worst_inp_ms"] else 0, reverse=True)

            # Write CSV file
            if summary_rows:
                fieldnames = summary_rows[0].keys()

                with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(summary_rows)

            self.logger.info("Executive summary CSV export complete", path=str(csv_path))
            return csv_path

        except Exception as e:
            self.logger.error("Failed to export executive summary CSV", error=str(e))
            raise

    async def _export_html(
        self,
        results: Dict[str, Any],
        output_path: Path,
        base_filename: str
    ) -> Path:
        """Export results to HTML format."""
        try:
            html_path = output_path / f"{base_filename}.html"

            # Generate HTML report
            html_content = self._generate_html_report(results)

            # Write HTML file
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)

            self.logger.debug("HTML export complete", path=str(html_path))
            return html_path

        except Exception as e:
            self.logger.error("Failed to export HTML", error=str(e))
            raise

    async def _create_summary(
        self,
        results: Dict[str, Any],
        output_path: Path,
        base_filename: str
    ) -> Path:
        """Create a summary file with key insights."""
        try:
            summary_path = output_path / f"{base_filename}_summary.md"

            summary_text = self._generate_text_summary(results)

            with open(summary_path, 'w', encoding='utf-8') as f:
                f.write(summary_text)

            self.logger.debug("Summary created", path=str(summary_path))
            return summary_path

        except Exception as e:
            self.logger.error("Failed to create summary", error=str(e))
            raise

    def _flatten_interaction_for_csv(self, url: str, interaction: Dict[str, Any]) -> Dict[str, Any]:
        """Flatten an interaction record for CSV export."""
        try:
            action = interaction.get("action", {})
            result = interaction.get("result", {})
            performance = interaction.get("performance", {})
            element = interaction.get("element", {})

            # Get element label for human readability (prefer label over text for clarity)
            element_text = element.get("label", "") or element.get("text", "")

            # Determine if this interaction is an outlier (INP > 200ms)
            inp_score = performance.get("inp", {}).get("score")
            outlier_flag = ""
            if inp_score:
                if inp_score > 500:
                    outlier_flag = "🚨"
                elif inp_score > 200:
                    outlier_flag = "⚠️"

            return {
                "url": url,
                "interaction_num": interaction.get("interaction_num", ""),
                "timestamp": interaction.get("timestamp", ""),
                "action_type": action.get("action", ""),
                "selector": action.get("selector", ""),
                "element_text": element_text,
                "action_text": action.get("text", ""),
                "execution_time": interaction.get("execution_time", ""),
                "success": result.get("success", ""),
                "measured_inp": performance.get("inp", {}).get("measured_score", "") or "",
                "inp_coefficient": performance.get("inp", {}).get("coefficient", "") or "",
                "estimated_inp": performance.get("inp", {}).get("estimated_score", "") or inp_score or "",
                "inp_classification": performance.get("inp", {}).get("classification", ""),
                "outlier_flag": outlier_flag,
                "cls_score": performance.get("layout", {}).get("cls_score", ""),
                "cls_classification": performance.get("layout", {}).get("cls_classification", ""),
                "js_blocking": performance.get("javascript", {}).get("blocking_assessment", ""),
                "overall_score": performance.get("overall_score", "")
            }

        except Exception as e:
            self.logger.error("Error flattening interaction", error=str(e))
            return {"error": str(e)}

    def _generate_summary_stats(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate summary statistics from results."""
        try:
            summary = {
                "total_urls": len(results),
                "total_interactions": 0,
                "successful_interactions": 0,
                "worst_inp_score": None,
                "worst_inp_url": None,
                "worst_inp_element": None,
                "average_inp_score": None,
                "inp_score_distribution": {"good": 0, "needs_improvement": 0, "poor": 0, "unknown": 0}
            }

            all_inp_scores = []
            worst_inp = 0

            for url, url_results in results.items():
                if isinstance(url_results, dict):
                    interactions = url_results.get("interactions", [])
                    summary["total_interactions"] += len(interactions)

                    for interaction in interactions:
                        # Count successful interactions
                        if interaction.get("result", {}).get("success", False):
                            summary["successful_interactions"] += 1

                        # Analyze INP scores
                        performance = interaction.get("performance", {})
                        inp_data = performance.get("inp", {})
                        inp_score = inp_data.get("score")

                        if inp_score is not None:
                            all_inp_scores.append(inp_score)

                            # Track worst INP
                            if inp_score > worst_inp:
                                worst_inp = inp_score
                                summary["worst_inp_score"] = inp_score
                                summary["worst_inp_url"] = url
                                summary["worst_inp_element"] = interaction.get("action", {}).get("selector", "")

                            # Count INP classifications
                            classification = inp_data.get("classification", "unknown")
                            if classification in summary["inp_score_distribution"]:
                                summary["inp_score_distribution"][classification] += 1

            # Calculate average INP
            if all_inp_scores:
                summary["average_inp_score"] = sum(all_inp_scores) / len(all_inp_scores)

            # Calculate success rate
            if summary["total_interactions"] > 0:
                summary["success_rate"] = summary["successful_interactions"] / summary["total_interactions"]

            return summary

        except Exception as e:
            self.logger.error("Error generating summary stats", error=str(e))
            return {"error": str(e)}

    def _detect_outliers(self, results: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, List[str]]]:
        """
        Detect outlier URLs and elements based on INP performance.

        Returns:
            Tuple of (outlier_data, element_aggregation)
            - outlier_data: {url: {is_outlier: bool, reason: str, ...}}
            - element_aggregation: {selector: [list of urls where it appears]}
        """
        try:
            # Collect all worst INP scores per URL
            url_worst_inps = {}
            element_occurrences = {}  # Track which elements appear on which URLs

            for url, url_results in results.items():
                if isinstance(url_results, dict):
                    worst_inp = url_results.get('worst_inp')
                    worst_element = url_results.get('worst_element')

                    if worst_inp is not None:
                        url_worst_inps[url] = worst_inp

                    # Track element occurrences
                    for interaction in url_results.get('interactions', []):
                        selector = interaction.get('action', {}).get('selector')
                        inp_score = interaction.get('performance', {}).get('inp', {}).get('score')

                        if selector and inp_score:
                            if selector not in element_occurrences:
                                element_occurrences[selector] = []
                            element_occurrences[selector].append({
                                'url': url,
                                'inp_score': inp_score
                            })

            # Calculate median worst INP
            outlier_data = {}
            if url_worst_inps:
                worst_inp_values = list(url_worst_inps.values())
                median_worst_inp = statistics.median(worst_inp_values)
                outlier_threshold = median_worst_inp * 2  # 2x median is outlier

                for url, worst_inp in url_worst_inps.items():
                    is_outlier = worst_inp > outlier_threshold and worst_inp > 200  # Must be > 200ms too
                    outlier_data[url] = {
                        'is_outlier': is_outlier,
                        'worst_inp': worst_inp,
                        'median_worst_inp': median_worst_inp,
                        'threshold': outlier_threshold,
                        'flag': '🚨' if worst_inp > 500 else '⚠️' if is_outlier else '✅'
                    }

            # Aggregate problematic elements across URLs
            element_aggregation = {}
            for selector, occurrences in element_occurrences.items():
                avg_inp = statistics.mean([o['inp_score'] for o in occurrences])
                urls_affected = [o['url'] for o in occurrences]

                # Flag elements that appear on multiple URLs with poor INP
                if len(urls_affected) > 1 and avg_inp > 200:
                    element_aggregation[selector] = {
                        'urls': urls_affected,
                        'occurrences': len(urls_affected),
                        'avg_inp': avg_inp,
                        'is_problematic': True
                    }

            return outlier_data, element_aggregation

        except Exception as e:
            self.logger.error("Error detecting outliers", error=str(e))
            return {}, {}

    def _generate_html_report(self, results: Dict[str, Any]) -> str:
        """Generate an HTML report."""
        try:
            summary = self._generate_summary_stats(results)

            html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Inputer Performance Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background-color: #f4f4f4; padding: 20px; border-radius: 5px; }}
        .summary {{ margin: 20px 0; }}
        .metric {{ display: inline-block; margin: 10px; padding: 10px; border: 1px solid #ddd; border-radius: 5px; }}
        .url-section {{ margin: 20px 0; padding: 15px; border-left: 3px solid #007cba; }}
        .interaction {{ margin: 10px 0; padding: 10px; background-color: #f9f9f9; }}
        .good {{ color: green; }}
        .needs-improvement {{ color: orange; }}
        .poor {{ color: red; }}
        .unknown {{ color: gray; }}
        table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f4f4f4; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🎯 Inputer Performance Report</h1>
        <p>Generated on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
    </div>

    <div class="summary">
        <h2>📊 Summary</h2>
        <div class="metric">
            <strong>Total URLs:</strong> {summary.get('total_urls', 0)}
        </div>
        <div class="metric">
            <strong>Total Interactions:</strong> {summary.get('total_interactions', 0)}
        </div>
        <div class="metric">
            <strong>Success Rate:</strong> {summary.get('success_rate') or 0:.1%}
        </div>
        <div class="metric">
            <strong>Worst INP:</strong> {summary.get('worst_inp_score') if summary.get('worst_inp_score') is not None else 'N/A'}ms
        </div>
        <div class="metric">
            <strong>Average INP:</strong> {f'{summary.get("average_inp_score"):.1f}' if summary.get('average_inp_score') is not None else 'N/A'}ms
        </div>
    </div>
"""

            # Add detailed results for each URL
            for url, url_results in results.items():
                if isinstance(url_results, dict):
                    html += f"""
    <div class="url-section">
        <h3>🌐 {url}</h3>
        <p><strong>Total Interactions:</strong> {url_results.get('total_interactions', 0)}</p>
        <p><strong>Worst INP:</strong> {url_results.get('worst_inp', 'N/A')}ms</p>
"""

                    interactions = url_results.get("interactions", [])
                    if interactions:
                        html += """
        <table>
            <tr>
                <th>#</th>
                <th>Action</th>
                <th>Element</th>
                <th>INP Score</th>
                <th>Classification</th>
                <th>Success</th>
            </tr>
"""
                        for interaction in interactions:
                            action = interaction.get("action", {})
                            result = interaction.get("result", {})
                            performance = interaction.get("performance", {})
                            inp_data = performance.get("inp", {})

                            classification = inp_data.get("classification", "unknown")
                            class_name = classification.replace("_", "-")

                            html += f"""
            <tr>
                <td>{interaction.get('interaction_num', '')}</td>
                <td>{action.get('action', '')}</td>
                <td>{action.get('selector', '')[:50]}...</td>
                <td>{inp_data.get('score', 'N/A')}</td>
                <td class="{class_name}">{classification.replace('_', ' ').title()}</td>
                <td>{'✅' if result.get('success') else '❌'}</td>
            </tr>
"""

                        html += "</table>"

                    html += "</div>"

            html += """
</body>
</html>
"""

            return html

        except Exception as e:
            self.logger.error("Error generating HTML report", error=str(e))
            return f"<html><body><h1>Error generating report: {e}</h1></body></html>"

    def _generate_text_summary(self, results: Dict[str, Any]) -> str:
        """Generate a Markdown summary of the results."""
        try:
            summary = self._generate_summary_stats(results)

            text = f"""# Inputer Performance Monitor - Analysis Summary

**Report Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## 📊 Overview

| Metric | Value |
|--------|-------|
| Total URLs Analyzed | {summary.get('total_urls', 0)} |
| Total Interactions | {summary.get('total_interactions', 0)} |
| Successful Interactions | {summary.get('successful_interactions', 0)} |
| Success Rate | {summary.get('success_rate') or 0:.1%} |

## ⚡ Performance Metrics

| Metric | Value |
|--------|-------|
| Worst INP Score | {summary.get('worst_inp_score') if summary.get('worst_inp_score') is not None else 'N/A'}ms |
| Average INP Score | {f'{summary.get("average_inp_score"):.1f}' if summary.get('average_inp_score') is not None else 'N/A'}ms |
| Worst INP URL | {summary.get('worst_inp_url') or 'N/A'} |
| Worst INP Element | {summary.get('worst_inp_element') or 'N/A'} |

## 📈 INP Score Distribution

| Classification | Count |
|---------------|-------|
| 🟢 Good (< 200ms) | {summary.get('inp_score_distribution', {}).get('good', 0)} |
| 🟡 Needs Improvement (200-500ms) | {summary.get('inp_score_distribution', {}).get('needs_improvement', 0)} |
| 🔴 Poor (> 500ms) | {summary.get('inp_score_distribution', {}).get('poor', 0)} |
| ⚪ Unknown | {summary.get('inp_score_distribution', {}).get('unknown', 0)} |
"""

            # Add Top 5 sections for multi-URL analysis
            if len(results) > 1:
                outlier_data, element_aggregation = self._detect_outliers(results)

                # Top 5 Worst URLs
                url_rankings = [(url, data.get('worst_inp', 0)) for url, data in outlier_data.items()]
                url_rankings.sort(key=lambda x: x[1], reverse=True)
                top_5_urls = url_rankings[:5]

                text += "\n## 🔝 Top 5 Worst Performing URLs\n\n"
                text += "| Rank | URL | Worst INP (ms) | Flag |\n"
                text += "|------|-----|----------------|------|\n"

                for rank, (url, worst_inp) in enumerate(top_5_urls, 1):
                    flag = outlier_data.get(url, {}).get('flag', '✅')
                    text += f"| {rank} | {url} | {worst_inp:.1f} | {flag} |\n"

                # Top 5 Problematic Elements (across all URLs)
                if element_aggregation:
                    text += "\n## 🎯 Top 5 Most Problematic Elements\n\n"
                    text += "| Rank | Element | Avg INP (ms) | URLs Affected |\n"
                    text += "|------|---------|--------------|---------------|\n"

                    element_rankings = [(sel, data) for sel, data in element_aggregation.items()]
                    element_rankings.sort(key=lambda x: x[1]['avg_inp'], reverse=True)
                    top_5_elements = element_rankings[:5]

                    for rank, (selector, data) in enumerate(top_5_elements, 1):
                        avg_inp = data['avg_inp']
                        urls_count = data['occurrences']
                        text += f"| {rank} | `{selector[:50]}...` | {avg_inp:.1f} | {urls_count} |\n"

            text += "\n## 🌐 Detailed Results by URL\n"

            for url, url_results in results.items():
                if isinstance(url_results, dict):
                    text += f"""
### {url}

- **Total Interactions:** {url_results.get('total_interactions', 0)}
- **Worst INP:** {url_results.get('worst_inp') or 'N/A'}ms
- **Worst Element:** {url_results.get('worst_element') or 'N/A'}
- **Errors:** {len(url_results.get('errors', []))}
"""

            text += "\n## 💡 Recommendations\n\n"

            # Add recommendations based on analysis
            worst_inp = summary.get('worst_inp_score', 0)
            if worst_inp and worst_inp > 500:
                text += "- 🚨 **CRITICAL:** INP scores > 500ms detected. Investigate JavaScript execution blocking.\n"
            elif worst_inp and worst_inp > 200:
                text += "- ⚠️ **WARNING:** INP scores > 200ms detected. Consider optimizing interaction responsiveness.\n"

            poor_count = summary.get('inp_score_distribution', {}).get('poor', 0)
            if poor_count > 0:
                text += f"- 🔴 **{poor_count} interactions** have poor INP scores. Focus on these elements first.\n"

            success_rate = summary.get('success_rate', 1.0)
            if success_rate < 0.8:
                text += "- 🔧 **Low interaction success rate** detected. Check for element accessibility issues.\n"

            if not any([worst_inp and worst_inp > 200, poor_count > 0, success_rate < 0.8]):
                text += "- ✅ **No critical issues detected.** Performance appears to be within acceptable ranges.\n"

            text += "\n---\n\n*For detailed analysis, see the accompanying JSON or HTML reports.*\n"

            return text

        except Exception as e:
            self.logger.error("Error generating text summary", error=str(e))
            return f"# Error Generating Summary\n\n**Error:** {e}"