"""
Page Analyzer Module

Analyzes page characteristics to calculate an input delay coefficient
for estimating real-world INP from automation measurements.
"""

import structlog
from typing import Dict, Any, List
from urllib.parse import urlparse


class PageAnalyzer:
    """Analyzes page characteristics to predict real-world input delay."""

    def __init__(self):
        self.logger = structlog.get_logger(__name__)

    async def analyze_page(
        self,
        page,
        url: str,
        performance_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze page characteristics to calculate input delay coefficient.

        Args:
            page: Playwright page object
            url: Page URL
            performance_data: Performance metrics from performance analyzer

        Returns:
            Dict with coefficient and breakdown
        """
        self.logger.info("Analyzing page for input delay coefficient", url=url)

        # Detect frameworks
        frameworks = await self._detect_frameworks(page)

        # Analyze JavaScript resources
        js_analysis = await self._analyze_javascript(page)

        # Count third-party domains
        third_party_count = await self._count_third_party_domains(page, url)

        # Get long tasks from performance data
        long_tasks_count = self._count_long_tasks(performance_data)

        # Calculate coefficient
        coefficient_data = self._calculate_coefficient(
            frameworks=frameworks,
            js_total_size=js_analysis['total_size'],
            third_party_count=third_party_count,
            long_tasks_count=long_tasks_count
        )

        result = {
            "coefficient": coefficient_data["coefficient"],
            "base_multiplier": coefficient_data["base"],
            "frameworks": frameworks,
            "js_total_size_kb": js_analysis['total_size'] / 1024,
            "third_party_domains": third_party_count,
            "long_tasks_count": long_tasks_count,
            "breakdown": coefficient_data["breakdown"]
        }

        self.logger.info(
            "Input delay coefficient calculated",
            url=url,
            coefficient=result["coefficient"],
            breakdown=result["breakdown"]
        )

        return result

    async def _detect_frameworks(self, page) -> List[str]:
        """Detect JavaScript frameworks on the page."""
        frameworks = await page.evaluate("""
            () => {
                const detected = [];

                // React
                if (window.React || window.__REACT_DEVTOOLS_GLOBAL_HOOK__ ||
                    document.querySelector('[data-reactroot], [data-reactid]')) {
                    detected.push('React');
                }

                // Angular
                if (window.angular || window.ng ||
                    document.querySelector('[ng-app], [ng-version]')) {
                    detected.push('Angular');
                }

                // Vue
                if (window.Vue || document.querySelector('[data-v-]')) {
                    detected.push('Vue');
                }

                // Next.js
                if (window.__NEXT_DATA__ || document.getElementById('__next')) {
                    detected.push('Next.js');
                }

                // Svelte
                if (document.querySelector('[class^="svelte-"]')) {
                    detected.push('Svelte');
                }

                return detected;
            }
        """)

        return frameworks

    async def _analyze_javascript(self, page) -> Dict[str, Any]:
        """Analyze JavaScript resources on the page."""
        js_resources = await page.evaluate("""
            () => {
                const resources = performance.getEntriesByType('resource')
                    .filter(r => r.initiatorType === 'script' || r.name.endsWith('.js'));

                const total_size = resources.reduce((sum, r) => {
                    // Use transferSize if available, otherwise estimate from duration
                    return sum + (r.transferSize || 0);
                }, 0);

                return {
                    count: resources.length,
                    total_size: total_size
                };
            }
        """)

        return js_resources

    async def _count_third_party_domains(self, page, main_url: str) -> int:
        """Count third-party script domains."""
        main_domain = urlparse(main_url).netloc

        third_party_domains = await page.evaluate("""
            (mainDomain) => {
                const resources = performance.getEntriesByType('resource')
                    .filter(r => r.initiatorType === 'script' || r.name.endsWith('.js'));

                const domains = new Set();
                resources.forEach(r => {
                    try {
                        const url = new URL(r.name);
                        if (url.hostname !== mainDomain && !url.hostname.endsWith('.' + mainDomain)) {
                            domains.add(url.hostname);
                        }
                    } catch (e) {}
                });

                return domains.size;
            }
        """, main_domain)

        return third_party_domains

    def _count_long_tasks(self, performance_data: Dict[str, Any]) -> int:
        """Count long tasks from performance data."""
        # Extract long tasks from performance trace data
        # This would come from the performance analyzer
        long_tasks = performance_data.get('long_tasks', [])
        return len([task for task in long_tasks if task.get('duration', 0) > 50])

    def _calculate_coefficient(
        self,
        frameworks: List[str],
        js_total_size: int,
        third_party_count: int,
        long_tasks_count: int
    ) -> Dict[str, Any]:
        """
        Calculate input delay coefficient based on page characteristics.

        Formula:
        Base: 5.0 (automation is typically 5x faster than real-world)
        + 1.0 per 500KB of JS
        + 1.0 if React/Angular/Vue detected
        + 0.3 per third-party domain
        + 0.5 per long task >50ms
        """
        breakdown = {}

        # Base multiplier
        coefficient = 5.0
        breakdown['base'] = 5.0

        # JS bundle size penalty
        js_size_mb = js_total_size / (1024 * 1024)
        js_penalty = (js_total_size / (500 * 1024)) * 1.0
        coefficient += js_penalty
        breakdown['js_size'] = round(js_penalty, 2)

        # Framework penalty
        framework_penalty = 0
        if any(fw in frameworks for fw in ['React', 'Angular', 'Vue']):
            framework_penalty = 1.0
            coefficient += framework_penalty
        breakdown['framework'] = framework_penalty

        # Third-party scripts penalty
        third_party_penalty = third_party_count * 0.3
        coefficient += third_party_penalty
        breakdown['third_party'] = round(third_party_penalty, 2)

        # Long tasks penalty
        long_task_penalty = long_tasks_count * 0.5
        coefficient += long_task_penalty
        breakdown['long_tasks'] = round(long_task_penalty, 2)

        return {
            "coefficient": round(coefficient, 2),
            "base": 5.0,
            "breakdown": breakdown
        }
