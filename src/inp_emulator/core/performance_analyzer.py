"""
Performance Analyzer - Measures and correlates INP and performance data.

This component handles the critical task of measuring performance metrics
and correlating them with specific user interactions and DOM elements.
"""

import asyncio
import json
import time
from typing import Any, Dict, List, Optional, Tuple

import structlog


logger = structlog.get_logger(__name__)


class PerformanceAnalyzer:
    """
    Analyzer for measuring INP and other performance metrics.

    Key capabilities:
    - Measures Interaction to Next Paint (INP)
    - Correlates performance issues with specific elements
    - Tracks layout shifts and visual stability
    - Analyzes JavaScript execution times
    - Provides actionable performance insights
    """

    def __init__(self, mcp_client):
        """Initialize the performance analyzer."""
        self.playwright_client = mcp_client
        self.logger = logger.bind(component="performance_analyzer")

        # Trace collection state
        self.is_tracing = False
        self.current_trace: Optional[Dict] = None

        # Performance metric thresholds (based on Core Web Vitals)
        self.thresholds = {
            "inp": {
                "good": 200,      # < 200ms is good
                "needs_improvement": 500,  # 200-500ms needs improvement
                # > 500ms is poor
            },
            "cls": {
                "good": 0.1,      # < 0.1 is good
                "needs_improvement": 0.25,  # 0.1-0.25 needs improvement
                # > 0.25 is poor
            },
            "lcp": {
                "good": 2500,     # < 2.5s is good
                "needs_improvement": 4000,  # 2.5-4s needs improvement
                # > 4s is poor
            }
        }

    async def start_trace(self) -> Dict[str, Any]:
        """Start performance tracing."""
        try:
            if self.is_tracing:
                await self.stop_trace()

            result = await self.playwright_client.start_performance_trace()
            self.is_tracing = True

            self.logger.debug("Performance trace started")
            return result

        except Exception as e:
            self.logger.error("Failed to start performance trace", error=str(e))
            raise

    async def stop_trace(self) -> Dict[str, Any]:
        """Stop performance tracing and get trace data."""
        try:
            if not self.is_tracing:
                self.logger.warning("Attempted to stop trace when not tracing")
                return {}

            trace_data = await self.playwright_client.stop_performance_trace()
            self.is_tracing = False
            self.current_trace = trace_data

            self.logger.debug("Performance trace stopped")
            return trace_data

        except Exception as e:
            self.logger.error("Failed to stop performance trace", error=str(e))
            self.is_tracing = False
            raise

    async def analyze_trace(self, trace_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze trace data to extract performance metrics.

        Args:
            trace_data: Raw trace data from Chrome DevTools

        Returns:
            Dict containing analyzed performance metrics
        """
        try:
            analysis_start = time.time()

            # Extract and calculate various performance metrics
            inp_metrics = await self._analyze_inp_metrics(trace_data)
            layout_metrics = await self._analyze_layout_metrics(trace_data)
            javascript_metrics = await self._analyze_javascript_metrics(trace_data)
            network_metrics = await self._analyze_network_metrics(trace_data)

            # Combine all metrics
            combined_metrics = {
                "timestamp": time.time(),
                "analysis_duration": time.time() - analysis_start,
                "inp": inp_metrics,
                "layout": layout_metrics,
                "javascript": javascript_metrics,
                "network": network_metrics,
                "overall_score": self._calculate_overall_score(
                    inp_metrics, layout_metrics, javascript_metrics
                )
            }

            # Add main INP score to top level for easy access
            combined_metrics["inp_score"] = inp_metrics.get("score")

            self.logger.debug(
                "Performance analysis complete",
                inp_score=combined_metrics.get("inp_score"),
                overall_score=combined_metrics.get("overall_score")
            )

            return combined_metrics

        except Exception as e:
            self.logger.error("Failed to analyze performance trace", error=str(e))
            return {
                "timestamp": time.time(),
                "error": str(e),
                "inp_score": None
            }

    async def _analyze_inp_metrics(self, trace_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze INP (Interaction to Next Paint) metrics from captured event timing data."""
        try:
            # Get INP entries captured by PerformanceObserver
            inp_script = """
                (() => {
                    const entries = window.__inpEntries || [];

                    if (entries.length === 0) {
                        return {score: null, measurement_method: 'none', entries: []};
                    }

                    // Find the worst (highest duration) interaction
                    let worstINP = 0;
                    let worstEntry = null;

                    for (const entry of entries) {
                        if (entry.duration > worstINP) {
                            worstINP = entry.duration;
                            worstEntry = entry;
                        }
                    }

                    return {
                        score: Math.round(worstINP),
                        measurement_method: 'event_timing_api',
                        worst_entry: worstEntry,
                        total_interactions: entries.length,
                        entries: entries
                    };
                })()
            """

            result = await self.playwright_client.evaluate_script(inp_script)

            if result and isinstance(result, dict):
                inp_score = result.get("score")

                # Classify INP score
                classification = self._classify_metric(inp_score, "inp") if inp_score else "unknown"

                return {
                    "score": inp_score,
                    "classification": classification,
                    "details": result,
                    "measurement_timestamp": time.time()
                }

            return {
                "score": None,
                "classification": "unknown",
                "error": "Invalid script result",
                "measurement_timestamp": time.time()
            }

        except Exception as e:
            self.logger.error("Failed to analyze INP metrics", error=str(e))
            return {
                "score": None,
                "classification": "error",
                "error": str(e),
                "measurement_timestamp": time.time()
            }

    async def _analyze_layout_metrics(self, trace_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze layout shift and visual stability metrics."""
        try:
            # JavaScript to measure Cumulative Layout Shift (CLS)
            cls_script = """
            (() => {
                let clsValue = 0;
                let layoutShifts = [];

                // Try to get CLS from PerformanceObserver
                if ('PerformanceObserver' in window) {
                    try {
                        const layoutShiftEntries = performance.getEntriesByType('layout-shift') || [];

                        layoutShiftEntries.forEach(entry => {
                            // Only count shifts not caused by user interaction
                            if (!entry.hadRecentInput) {
                                clsValue += entry.value;
                                layoutShifts.push({
                                    value: entry.value,
                                    startTime: Math.round(entry.startTime),
                                    sources: entry.sources?.length || 0
                                });
                            }
                        });

                        return {
                            cls_score: Math.round(clsValue * 1000) / 1000,
                            shift_count: layoutShifts.length,
                            shifts: layoutShifts,
                            measurement_method: 'performance_observer'
                        };

                    } catch (e) {
                        console.warn('Error measuring CLS:', e);
                    }
                }

                // Fallback: Check for elements that might cause shifts
                const potentialShifters = document.querySelectorAll('img:not([width]):not([height]), iframe, video, .ad, .banner');

                return {
                    cls_score: null,
                    potential_shifters: potentialShifters.length,
                    measurement_method: 'element_analysis_fallback'
                };
            })();
            """

            result = await self.playwright_client.evaluate_script(cls_script)

            if result and isinstance(result, dict):
                cls_score = result.get("cls_score")
                cls_classification = self._classify_metric(cls_score, "cls") if cls_score else "unknown"

                return {
                    "cls_score": cls_score,
                    "cls_classification": cls_classification,
                    "shift_details": result,
                    "measurement_timestamp": time.time()
                }

            return {
                "cls_score": None,
                "cls_classification": "unknown",
                "error": "Invalid script result",
                "measurement_timestamp": time.time()
            }

        except Exception as e:
            self.logger.error("Failed to analyze layout metrics", error=str(e))
            return {
                "cls_score": None,
                "cls_classification": "error",
                "error": str(e),
                "measurement_timestamp": time.time()
            }

    async def _analyze_javascript_metrics(self, trace_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze JavaScript execution and blocking metrics."""
        try:
            # JavaScript to analyze script execution timing
            js_script = """
            (() => {
                const measurements = [];

                // Get resource timing for scripts
                const scriptResources = performance.getEntriesByType('resource').filter(
                    entry => entry.initiatorType === 'script' || entry.name.includes('.js')
                );

                let totalScriptTime = 0;
                let longestScript = null;
                let longestDuration = 0;

                scriptResources.forEach(script => {
                    const duration = script.responseEnd - script.startTime;
                    totalScriptTime += duration;

                    if (duration > longestDuration) {
                        longestDuration = duration;
                        longestScript = {
                            url: script.name.split('/').pop() || script.name,
                            duration: Math.round(duration),
                            transferSize: script.transferSize || 0
                        };
                    }
                });

                // Check for long tasks
                const longTasks = performance.getEntriesByType('longtask') || [];
                const totalLongTaskTime = longTasks.reduce((sum, task) => sum + task.duration, 0);
                const longTaskDetails = longTasks.map(task => ({
                    duration: task.duration,
                    startTime: task.startTime,
                    name: task.name
                }));

                return {
                    script_count: scriptResources.length,
                    total_script_time: Math.round(totalScriptTime),
                    longest_script: longestScript,
                    long_task_count: longTasks.length,
                    total_long_task_time: Math.round(totalLongTaskTime),
                    long_tasks: longTaskDetails,
                    average_script_time: scriptResources.length > 0 ? Math.round(totalScriptTime / scriptResources.length) : 0
                };
            })();
            """

            result = await self.playwright_client.evaluate_script(js_script)

            if result and isinstance(result, dict):
                return {
                    "execution_metrics": result,
                    "blocking_assessment": self._assess_js_blocking(result),
                    "measurement_timestamp": time.time()
                }

            return {
                "execution_metrics": {},
                "blocking_assessment": "unknown",
                "error": "Invalid script result",
                "measurement_timestamp": time.time()
            }

        except Exception as e:
            self.logger.error("Failed to analyze JavaScript metrics", error=str(e))
            return {
                "execution_metrics": {},
                "blocking_assessment": "error",
                "error": str(e),
                "measurement_timestamp": time.time()
            }

    async def _analyze_network_metrics(self, trace_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze network-related performance metrics."""
        try:
            # JavaScript to analyze network timing
            network_script = """
            (() => {
                const resources = performance.getEntriesByType('resource') || [];
                const navigation = performance.getEntriesByType('navigation')[0];

                let totalTransferSize = 0;
                let requestCount = 0;
                let slowestRequest = null;
                let slowestDuration = 0;

                resources.forEach(resource => {
                    const duration = resource.responseEnd - resource.startTime;
                    totalTransferSize += resource.transferSize || 0;
                    requestCount++;

                    if (duration > slowestDuration) {
                        slowestDuration = duration;
                        slowestRequest = {
                            url: resource.name.split('/').pop() || resource.name,
                            duration: Math.round(duration),
                            transferSize: resource.transferSize || 0,
                            type: resource.initiatorType
                        };
                    }
                });

                return {
                    request_count: requestCount,
                    total_transfer_size: totalTransferSize,
                    slowest_request: slowestRequest,
                    dom_content_loaded: navigation ? Math.round(navigation.domContentLoadedEventEnd - navigation.navigationStart) : null,
                    load_complete: navigation ? Math.round(navigation.loadEventEnd - navigation.navigationStart) : null
                };
            })();
            """

            result = await self.playwright_client.evaluate_script(network_script)

            if result and isinstance(result, dict):
                return {
                    "network_metrics": result,
                    "measurement_timestamp": time.time()
                }

            return {
                "network_metrics": {},
                "error": "Invalid script result",
                "measurement_timestamp": time.time()
            }

        except Exception as e:
            self.logger.error("Failed to analyze network metrics", error=str(e))
            return {
                "network_metrics": {},
                "error": str(e),
                "measurement_timestamp": time.time()
            }

    def _classify_metric(self, value: Optional[float], metric_type: str) -> str:
        """Classify a performance metric value as good/needs improvement/poor."""
        if value is None:
            return "unknown"

        thresholds = self.thresholds.get(metric_type, {})
        good_threshold = thresholds.get("good", 0)
        needs_improvement_threshold = thresholds.get("needs_improvement", float('inf'))

        if value <= good_threshold:
            return "good"
        elif value <= needs_improvement_threshold:
            return "needs_improvement"
        else:
            return "poor"

    def _assess_js_blocking(self, js_metrics: Dict[str, Any]) -> str:
        """Assess JavaScript blocking potential based on metrics."""
        try:
            long_task_time = js_metrics.get("total_long_task_time", 0)
            script_count = js_metrics.get("script_count", 0)
            total_script_time = js_metrics.get("total_script_time", 0)

            # High blocking potential indicators
            if long_task_time > 1000 or script_count > 20 or total_script_time > 5000:
                return "high"
            elif long_task_time > 500 or script_count > 10 or total_script_time > 2000:
                return "medium"
            else:
                return "low"

        except Exception:
            return "unknown"

    def _calculate_overall_score(
        self,
        inp_metrics: Dict[str, Any],
        layout_metrics: Dict[str, Any],
        javascript_metrics: Dict[str, Any]
    ) -> float:
        """Calculate an overall performance score from individual metrics."""
        try:
            scores = []

            # INP score (weight: 40%)
            inp_score = inp_metrics.get("score")
            if inp_score is not None:
                inp_normalized = max(0, min(100, 100 - (inp_score / 10)))  # Convert to 0-100 scale
                scores.append(("inp", inp_normalized, 0.4))

            # CLS score (weight: 30%)
            cls_score = layout_metrics.get("cls_score")
            if cls_score is not None:
                cls_normalized = max(0, min(100, 100 - (cls_score * 200)))  # Convert to 0-100 scale
                scores.append(("cls", cls_normalized, 0.3))

            # JavaScript blocking (weight: 30%)
            js_blocking = javascript_metrics.get("blocking_assessment", "unknown")
            js_score_map = {"low": 90, "medium": 60, "high": 30, "unknown": 50}
            js_score = js_score_map.get(js_blocking, 50)
            scores.append(("js", js_score, 0.3))

            # Calculate weighted average
            if scores:
                total_weight = sum(weight for _, _, weight in scores)
                weighted_sum = sum(score * weight for _, score, weight in scores)
                overall_score = weighted_sum / total_weight if total_weight > 0 else 50

                return round(overall_score, 1)

            return 50.0  # Default score if no metrics available

        except Exception as e:
            self.logger.error("Error calculating overall score", error=str(e))
            return 50.0

    async def get_current_metrics(self) -> Dict[str, Any]:
        """Get current performance metrics without starting a new trace."""
        try:
            # Get current metrics from the browser
            current_metrics = await self.playwright_client.get_performance_metrics()

            # Add timestamp
            current_metrics["measurement_timestamp"] = time.time()

            return current_metrics

        except Exception as e:
            self.logger.error("Failed to get current metrics", error=str(e))
            return {
                "measurement_timestamp": time.time(),
                "error": str(e)
            }