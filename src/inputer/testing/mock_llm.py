"""
Mock LLM Client - Deterministic testing without actual LLM calls.
"""

import logging
import random
from typing import Any, Dict, List, Optional

import structlog


logger = structlog.get_logger(__name__)


class MockLLMClient:
    """
    Mock LLM client for testing without actual LLM API calls.

    Provides deterministic responses based on predefined strategies:
    - Sequential: Tests elements in order
    - Random: Random element selection
    - Priority: Focuses on high INP potential elements
    - Problematic: Targets known problematic element types
    """

    def __init__(self, strategy: str = "priority"):
        """
        Initialize mock LLM client.

        Args:
            strategy: Testing strategy ("sequential", "random", "priority", "problematic")
        """
        self.strategy = strategy
        self.interaction_count = 0
        self.tested_selectors = set()
        self.logger = logger.bind(component="mock_llm", strategy=strategy)

    async def initialize(self) -> None:
        """Initialize mock LLM client."""
        self.logger.info("Mock LLM client initialized")

    async def get_next_action(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Get next action using mock strategy instead of LLM.

        Args:
            context: Current browser state and available options

        Returns:
            Mock action decision based on strategy
        """
        elements = context.get("available_elements", [])
        previous_interactions = context.get("previous_interactions", [])

        if not elements:
            self.logger.info("No elements available for testing")
            return None

        # Filter out already tested elements
        untested_elements = [
            elem for elem in elements
            if elem.get("selector") not in self.tested_selectors
        ]

        if not untested_elements:
            self.logger.info("All elements tested")
            return None

        # Apply strategy to select element
        selected_element = self._select_element_by_strategy(untested_elements)

        if not selected_element:
            return None

        # Generate action based on element type
        action = self._generate_action_for_element(selected_element)

        # Track tested element
        self.tested_selectors.add(selected_element.get("selector"))
        self.interaction_count += 1

        self.logger.info(
            "Mock LLM selected action",
            action=action.get("action"),
            selector=action.get("selector"),
            strategy=self.strategy
        )

        return action

    def _select_element_by_strategy(self, elements: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Select element based on configured strategy."""

        if self.strategy == "sequential":
            # Test elements in order
            return elements[0] if elements else None

        elif self.strategy == "random":
            # Random selection
            return random.choice(elements) if elements else None

        elif self.strategy == "priority":
            # Select element with highest INP potential score
            elements_with_scores = [
                elem for elem in elements
                if elem.get("inp_potential_score", 0) > 0
            ]
            if elements_with_scores:
                return max(elements_with_scores, key=lambda x: x.get("inp_potential_score", 0))
            return elements[0] if elements else None

        elif self.strategy == "problematic":
            # Target known problematic element types
            problematic_types = ["dropdown", "accordion", "modal", "carousel", "tab"]
            for elem in elements:
                elem_type = elem.get("type", "").lower()
                if any(prob_type in elem_type for prob_type in problematic_types):
                    return elem
            # Fallback to priority if no problematic elements
            return self._select_element_by_strategy_priority(elements)

        else:
            # Default to first element
            return elements[0] if elements else None

    def _select_element_by_strategy_priority(self, elements: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Helper method for priority selection."""
        elements_with_scores = [
            elem for elem in elements
            if elem.get("inp_potential_score", 0) > 0
        ]
        if elements_with_scores:
            return max(elements_with_scores, key=lambda x: x.get("inp_potential_score", 0))
        return elements[0] if elements else None

    def _generate_action_for_element(self, element: Dict[str, Any]) -> Dict[str, Any]:
        """Generate appropriate action based on element characteristics."""
        elem_type = element.get("type", "").lower()
        selector = element.get("selector", "")

        # Determine action based on element type
        if "input" in elem_type and "text" in elem_type:
            return {
                "action": "type",
                "selector": selector,
                "text": "test input",
                "reasoning": f"Mock testing text input: {selector}"
            }
        elif "select" in elem_type or "dropdown" in elem_type:
            return {
                "action": "click",
                "selector": selector,
                "reasoning": f"Mock testing dropdown/select: {selector}"
            }
        elif "scroll" in elem_type:
            return {
                "action": "scroll",
                "direction": "down",
                "amount": 500,
                "reasoning": f"Mock testing scroll: {selector}"
            }
        else:
            # Default to click for most interactive elements
            return {
                "action": "click",
                "selector": selector,
                "reasoning": f"Mock testing clickable element: {selector}"
            }

    async def analyze_performance_results(
        self,
        interaction_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Mock analysis of performance results.

        Args:
            interaction_results: List of interaction results

        Returns:
            Mock analysis with insights
        """
        if not interaction_results:
            return {"summary": "No interactions to analyze"}

        # Calculate mock statistics
        total_interactions = len(interaction_results)
        inp_scores = []

        for result in interaction_results:
            performance = result.get("performance", {})
            inp_data = performance.get("inp", {})
            inp_score = inp_data.get("score")
            if inp_score is not None:
                inp_scores.append(inp_score)

        if not inp_scores:
            return {
                "summary": "No INP scores available for analysis",
                "total_interactions": total_interactions
            }

        # Find worst performer
        worst_score = max(inp_scores)
        worst_interaction = None

        for result in interaction_results:
            performance = result.get("performance", {})
            if performance.get("inp", {}).get("score") == worst_score:
                worst_interaction = result
                break

        # Generate mock insights
        insights = []
        recommendations = []

        if worst_score > 500:
            insights.append("Critical INP issues detected (>500ms)")
            recommendations.append("Investigate JavaScript execution blocking on worst performing elements")
        elif worst_score > 200:
            insights.append("INP performance needs improvement (>200ms)")
            recommendations.append("Consider optimizing interaction responsiveness")
        else:
            insights.append("INP performance within acceptable range")

        if len([score for score in inp_scores if score > 500]) > 1:
            insights.append("Multiple elements showing poor INP performance")
            recommendations.append("Focus on systematic performance optimization")

        return {
            "worst_performer": {
                "selector": worst_interaction.get("action", {}).get("selector") if worst_interaction else None,
                "inp_score": worst_score,
                "action": worst_interaction.get("action", {}).get("action") if worst_interaction else None
            },
            "insights": insights,
            "recommendations": recommendations,
            "summary": f"Analyzed {total_interactions} interactions with average INP of {sum(inp_scores)/len(inp_scores):.1f}ms",
            "mock_analysis": True
        }

    async def cleanup(self) -> None:
        """Clean up mock LLM client."""
        self.logger.info("Mock LLM client cleanup complete")

    def get_stats(self) -> Dict[str, Any]:
        """Get mock LLM client statistics."""
        return {
            "strategy": self.strategy,
            "interactions_generated": self.interaction_count,
            "elements_tested": len(self.tested_selectors),
            "tested_selectors": list(self.tested_selectors)
        }


class DeterministicMockLLM(MockLLMClient):
    """
    Deterministic mock LLM for consistent testing.

    Uses predefined action sequences for reproducible tests.
    """

    def __init__(self, action_sequence: List[Dict[str, Any]] = None):
        """
        Initialize deterministic mock.

        Args:
            action_sequence: Predefined sequence of actions to return
        """
        super().__init__(strategy="deterministic")
        self.action_sequence = action_sequence or self._default_action_sequence()
        self.sequence_index = 0

    def _default_action_sequence(self) -> List[Dict[str, Any]]:
        """Default action sequence for testing."""
        return [
            {
                "action": "click",
                "selector": "button:first-of-type",
                "reasoning": "Test first button"
            },
            {
                "action": "click",
                "selector": ".dropdown-toggle",
                "reasoning": "Test dropdown"
            },
            {
                "action": "type",
                "selector": "input[type='text']",
                "text": "test input",
                "reasoning": "Test text input"
            },
            {
                "action": "scroll",
                "direction": "down",
                "amount": 500,
                "reasoning": "Test scroll behavior"
            },
            {
                "action": "none",
                "reasoning": "End test sequence"
            }
        ]

    async def get_next_action(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Return next action from predetermined sequence."""
        if self.sequence_index >= len(self.action_sequence):
            return None

        action = self.action_sequence[self.sequence_index]
        self.sequence_index += 1

        # Return None if action is "none"
        if action.get("action") == "none":
            return None

        self.logger.info(
            "Deterministic mock action",
            sequence_index=self.sequence_index - 1,
            action=action.get("action")
        )

        return action