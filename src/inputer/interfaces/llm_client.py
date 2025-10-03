"""
LLM Agent Client - Interface for AI-driven decision making.
"""

import json
import logging
from typing import Any, Dict, List, Optional

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from inputer.config.settings import LLMAgentConfig


logger = structlog.get_logger(__name__)


class LLMClient:
    """
    Client for communicating with the local LLM agent.

    Handles:
    - Sending browser state to LLM for analysis
    - Getting structured action decisions
    - Managing conversation context
    """

    def __init__(self, config: LLMAgentConfig):
        """Initialize LLM client with configuration."""
        self.config = config
        self.logger = logger.bind(component="llm_client")

        # HTTP client for API calls
        self.http_client: Optional[httpx.AsyncClient] = None

        # Conversation context
        self.conversation_history: List[Dict[str, Any]] = []

    async def initialize(self) -> None:
        """Initialize the LLM client."""
        self.logger.info("Initializing LLM client", url=self.config.url)

        self.http_client = httpx.AsyncClient(
            timeout=self.config.timeout,
            limits=httpx.Limits(max_connections=5)
        )

        # Test connection
        await self._test_connection()

        self.logger.info("LLM client initialization complete")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5))
    async def _test_connection(self) -> None:
        """Test connection to LLM agent."""
        try:
            # Try a simple health check or model query
            response = await self.http_client.post(
                f"{self.config.url}/v1/chat/completions",
                json={
                    "model": self.config.model,
                    "messages": [{"role": "user", "content": "Hello"}],
                    "max_tokens": 10
                }
            )

            if response.status_code == 200:
                self.logger.info("LLM connection test successful")
                return

        except Exception as e:
            self.logger.error("LLM connection test failed", error=str(e))
            raise

        raise RuntimeError("Failed to connect to LLM agent")

    async def get_next_action(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Get the next action decision from the LLM based on current context.

        Args:
            context: Current browser state and available options

        Returns:
            Structured action to perform, or None if no action recommended
        """
        try:
            # Build prompt for LLM
            prompt = self._build_action_prompt(context)

            # Query LLM
            response = await self._query_llm(prompt)

            # Parse and validate response
            action = self._parse_action_response(response)

            if action:
                self.logger.info("LLM recommended action", action=action.get("action"))
            else:
                self.logger.info("LLM recommended no action")

            return action

        except Exception as e:
            self.logger.error("Failed to get next action from LLM", error=str(e))
            return None

    def _build_action_prompt(self, context: Dict[str, Any]) -> str:
        """Build a comprehensive prompt for the LLM to decide the next action."""

        # Extract key information from context
        elements = context.get("available_elements", [])
        page_info = context.get("page_info", {})
        previous_interactions = context.get("previous_interactions", [])
        goal = context.get("goal", "Find interactive elements that cause high INP scores")

        # Build element list for LLM
        element_descriptions = []
        for idx, element in enumerate(elements):
            elem_desc = f"{idx + 1}. {element.get('type', 'unknown')} - '{element.get('selector', 'no selector')}'"
            if element.get('text'):
                elem_desc += f" (text: '{element['text'][:50]}...')"
            if element.get('visible', True):
                elem_desc += " [visible]"
            else:
                elem_desc += " [hidden]"
            element_descriptions.append(elem_desc)

        # Build interaction history summary
        history_summary = ""
        if previous_interactions:
            history_summary = "\nPrevious interactions:\n"
            for interaction in previous_interactions[-3:]:  # Last 3 interactions
                action = interaction.get("action", {})
                performance = interaction.get("performance", {})
                inp_score = performance.get("inp_score", "unknown")
                history_summary += f"- {action.get('action', 'unknown')} on '{action.get('selector', 'unknown')}' -> INP: {inp_score}ms\n"

        # Construct the full prompt
        prompt = f"""
You are an AI assistant that helps identify web elements that cause poor Interaction to Next Paint (INP) performance.

Current page: {page_info.get('url', 'unknown')}
Title: {page_info.get('title', 'unknown')}

Goal: {goal}

Available interactive elements on the page:
{chr(10).join(element_descriptions) if element_descriptions else "No interactive elements found"}

{history_summary}

Your task is to choose the BEST next element to interact with to find INP performance issues. Consider:
1. Elements that are likely to trigger heavy JavaScript or DOM manipulation
2. Elements that haven't been tested yet
3. Complex interactive components (dropdowns, accordions, modals, etc.)
4. Elements that might cause layout shifts

Respond with a JSON object in the following format:
{{
    "action": "click|hover|type|scroll|none",
    "selector": "css-selector-string",
    "reasoning": "explanation of why this element was chosen",
    "text": "text to type (only for type actions)",
    "amount": 500 (only for scroll actions)
}}

If no good elements remain to test, respond with {{"action": "none", "reasoning": "explanation"}}.

Choose carefully - focus on elements most likely to reveal INP performance issues.
"""

        return prompt.strip()

    async def _query_llm(self, prompt: str) -> str:
        """Send prompt to LLM and get response."""
        if not self.http_client:
            raise RuntimeError("LLM client not initialized")

        try:
            # Prepare messages for chat completion
            messages = [
                {
                    "role": "system",
                    "content": "You are an expert web performance analyst specializing in Interaction to Next Paint (INP) optimization. Always respond with valid JSON."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]

            # Add conversation context if available
            if self.conversation_history:
                messages = self.conversation_history[-5:] + messages

            payload = {
                "model": self.config.model,
                "messages": messages,
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_tokens,
                "stop": None
            }

            response = await self.http_client.post(
                f"{self.config.url}/v1/chat/completions",
                json=payload
            )

            response.raise_for_status()
            result = response.json()

            # Extract response content
            response_content = result["choices"][0]["message"]["content"]

            # Update conversation history
            self.conversation_history.append({"role": "user", "content": prompt})
            self.conversation_history.append({"role": "assistant", "content": response_content})

            # Keep only last 10 messages to prevent context explosion
            if len(self.conversation_history) > 10:
                self.conversation_history = self.conversation_history[-10:]

            return response_content

        except httpx.HTTPError as e:
            self.logger.error("HTTP error querying LLM", error=str(e))
            raise RuntimeError(f"LLM communication error: {e}")

        except Exception as e:
            self.logger.error("Error querying LLM", error=str(e))
            raise

    def _parse_action_response(self, response: str) -> Optional[Dict[str, Any]]:
        """Parse LLM response into structured action."""
        try:
            # Extract JSON from response (handle potential markdown formatting)
            response = response.strip()

            # Find JSON block if wrapped in markdown
            if "```json" in response:
                start = response.find("```json") + 7
                end = response.find("```", start)
                if end != -1:
                    response = response[start:end]
            elif "```" in response:
                start = response.find("```") + 3
                end = response.find("```", start)
                if end != -1:
                    response = response[start:end]

            # Parse JSON
            action_data = json.loads(response.strip())

            # Validate required fields
            if not isinstance(action_data, dict):
                raise ValueError("Response is not a JSON object")

            action_type = action_data.get("action")
            if not action_type:
                raise ValueError("Missing 'action' field")

            # Return None if LLM says no action
            if action_type == "none":
                return None

            # Validate action type
            valid_actions = ["click", "hover", "type", "scroll"]
            if action_type not in valid_actions:
                raise ValueError(f"Invalid action type: {action_type}")

            # Validate selector for most actions
            if action_type in ["click", "hover", "type"] and not action_data.get("selector"):
                raise ValueError(f"Missing selector for {action_type} action")

            # Validate text for type actions
            if action_type == "type" and not action_data.get("text"):
                raise ValueError("Missing text for type action")

            self.logger.debug("Parsed LLM action", action=action_data)
            return action_data

        except json.JSONDecodeError as e:
            self.logger.error("Failed to parse LLM response as JSON", response=response[:200], error=str(e))
            return None

        except ValueError as e:
            self.logger.error("Invalid LLM action response", error=str(e))
            return None

        except Exception as e:
            self.logger.error("Unexpected error parsing LLM response", error=str(e))
            return None

    async def analyze_performance_results(
        self,
        interaction_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Have the LLM analyze performance results and provide insights.

        Args:
            interaction_results: List of all interaction results

        Returns:
            Analysis and recommendations from LLM
        """
        try:
            # Build analysis prompt
            prompt = self._build_analysis_prompt(interaction_results)

            # Query LLM
            response = await self._query_llm(prompt)

            # Parse response (expecting structured analysis)
            analysis = self._parse_analysis_response(response)

            return analysis

        except Exception as e:
            self.logger.error("Failed to analyze performance results", error=str(e))
            return {"error": str(e)}

    def _build_analysis_prompt(self, results: List[Dict[str, Any]]) -> str:
        """Build prompt for final performance analysis."""

        # Summarize results for LLM
        results_summary = []
        for result in results:
            action = result.get("action", {})
            performance = result.get("performance", {})
            inp_score = performance.get("inp_score", "unknown")

            summary = f"Action: {action.get('action')} on '{action.get('selector')}' -> INP: {inp_score}ms"
            results_summary.append(summary)

        prompt = f"""
You are analyzing the results of an automated INP (Interaction to Next Paint) performance test.

Test Results:
{chr(10).join(results_summary)}

Please analyze these results and provide insights in JSON format:
{{
    "worst_performer": {{
        "selector": "css-selector",
        "inp_score": 123,
        "action": "click|hover|type|scroll"
    }},
    "insights": [
        "Key insight about performance patterns",
        "Another important observation"
    ],
    "recommendations": [
        "Specific recommendation for improvement",
        "Another actionable suggestion"
    ],
    "summary": "Overall summary of findings"
}}

Focus on identifying patterns and providing actionable recommendations for improving INP performance.
"""

        return prompt.strip()

    def _parse_analysis_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM analysis response."""
        try:
            # Similar JSON extraction logic as in _parse_action_response
            response = response.strip()

            if "```json" in response:
                start = response.find("```json") + 7
                end = response.find("```", start)
                if end != -1:
                    response = response[start:end]

            analysis_data = json.loads(response.strip())
            return analysis_data

        except Exception as e:
            self.logger.error("Failed to parse analysis response", error=str(e))
            return {"error": f"Failed to parse analysis: {e}"}

    async def cleanup(self) -> None:
        """Clean up LLM client resources."""
        self.logger.info("Cleaning up LLM client")

        try:
            if self.http_client:
                await self.http_client.aclose()

        except Exception as e:
            self.logger.error("Error during LLM cleanup", error=str(e))

        self.logger.info("LLM client cleanup complete")