"""
AWS Bedrock Client - LLM interface using AWS Bedrock.
"""

import json
import logging
from typing import Any, Dict, List, Optional

import boto3
import structlog
from botocore.exceptions import ClientError

from inputer.config.settings import LLMAgentConfig


logger = structlog.get_logger(__name__)


class BedrockClient:
    """
    Client for communicating with AWS Bedrock LLM services.

    Handles:
    - Claude and other model interactions via Bedrock
    - Structured prompt engineering for performance analysis
    - Error handling and retry logic
    - Cost optimization through model selection
    """

    def __init__(self, config: LLMAgentConfig, aws_region: str = 'us-east-1'):
        """Initialize Bedrock client."""
        self.config = config
        self.aws_region = aws_region
        self.logger = logger.bind(component="bedrock_client")

        # Initialize Bedrock client
        self.bedrock_client = boto3.client(
            'bedrock-runtime',
            region_name=aws_region
        )

        # Conversation context
        self.conversation_history: List[Dict[str, Any]] = []

        # Model configuration
        self.model_configs = {
            'anthropic.claude-3-haiku-20240307-v1:0': {
                'max_tokens': 4000,
                'supports_system': True,
                'cost_tier': 'low'
            },
            'anthropic.claude-3-sonnet-20240229-v1:0': {
                'max_tokens': 4000,
                'supports_system': True,
                'cost_tier': 'medium'
            },
            'anthropic.claude-instant-v1': {
                'max_tokens': 8000,
                'supports_system': False,
                'cost_tier': 'lowest'
            },
            'amazon.titan-text-express-v1': {
                'max_tokens': 8000,
                'supports_system': False,
                'cost_tier': 'lowest'
            }
        }

    async def initialize(self) -> None:
        """Initialize the Bedrock client."""
        self.logger.info("Initializing Bedrock client", model=self.config.model)

        try:
            # Test connection by listing available models
            response = self.bedrock_client.list_foundation_models()
            available_models = [model['modelId'] for model in response['modelSummaries']]

            if self.config.model not in available_models:
                self.logger.warning(
                    "Configured model not available",
                    configured_model=self.config.model,
                    available_models=available_models[:5]
                )

            self.logger.info("Bedrock client initialization complete")

        except ClientError as e:
            self.logger.error("Failed to initialize Bedrock client", error=str(e))
            raise

    async def get_next_action(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Get the next action decision from Bedrock based on current context.

        Args:
            context: Current browser state and available options

        Returns:
            Structured action to perform, or None if no action recommended
        """
        try:
            # Build prompt for Bedrock
            prompt = self._build_action_prompt(context)

            # Query Bedrock
            response = await self._query_bedrock(prompt)

            # Parse and validate response
            action = self._parse_action_response(response)

            if action:
                self.logger.info("Bedrock recommended action", action=action.get("action"))
            else:
                self.logger.info("Bedrock recommended no action")

            return action

        except Exception as e:
            self.logger.error("Failed to get next action from Bedrock", error=str(e))
            return None

    def _build_action_prompt(self, context: Dict[str, Any]) -> str:
        """Build a comprehensive prompt for Bedrock to decide the next action."""
        elements = context.get("available_elements", [])
        page_info = context.get("page_info", {})
        previous_interactions = context.get("previous_interactions", [])
        goal = context.get("goal", "Find interactive elements that cause high INP scores")

        # Build element list
        element_descriptions = []
        for idx, element in enumerate(elements):
            elem_desc = f"{idx + 1}. {element.get('type', 'unknown')} - '{element.get('selector', 'no selector')}'"
            if element.get('text'):
                elem_desc += f" (text: '{element['text'][:50]}...')"
            if element.get('inp_potential_score'):
                elem_desc += f" [INP potential: {element['inp_potential_score']:.1f}]"
            element_descriptions.append(elem_desc)

        # Build interaction history
        history_summary = ""
        if previous_interactions:
            history_summary = "\nPrevious interactions:\n"
            for interaction in previous_interactions[-3:]:
                action = interaction.get("action", {})
                performance = interaction.get("performance", {})
                inp_score = performance.get("inp_score", "unknown")
                history_summary += f"- {action.get('action', 'unknown')} on '{action.get('selector', 'unknown')}' -> INP: {inp_score}ms\n"

        # Construct the full prompt
        prompt = f"""You are an expert web performance analyst specializing in Interaction to Next Paint (INP) optimization.

Current page: {page_info.get('url', 'unknown')}
Title: {page_info.get('title', 'unknown')}

Goal: {goal}

Available interactive elements on the page:
{chr(10).join(element_descriptions) if element_descriptions else "No interactive elements found"}

{history_summary}

Your task is to choose the BEST next element to interact with to find INP performance issues. Consider:
1. Elements with high INP potential scores (shown in brackets)
2. Elements that are likely to trigger heavy JavaScript or DOM manipulation
3. Complex interactive components (dropdowns, accordions, modals, etc.)
4. Elements that might cause layout shifts
5. Elements that haven't been tested yet

Respond with a JSON object in the following format:
{{
    "action": "click|hover|type|scroll|none",
    "selector": "css-selector-string",
    "reasoning": "explanation of why this element was chosen",
    "text": "text to type (only for type actions)",
    "amount": 500 (only for scroll actions)
}}

If no good elements remain to test, respond with {{"action": "none", "reasoning": "explanation"}}.

Choose carefully - focus on elements most likely to reveal significant INP performance issues."""

        return prompt.strip()

    async def _query_bedrock(self, prompt: str) -> str:
        """Send prompt to Bedrock and get response."""
        try:
            model_config = self.model_configs.get(self.config.model, {})

            # Prepare request based on model type
            if 'claude' in self.config.model.lower():
                # Claude models use messages format
                messages = []

                # Add conversation history if available
                if self.conversation_history:
                    messages.extend(self.conversation_history[-4:])  # Last 4 messages

                messages.append({
                    "role": "user",
                    "content": prompt
                })

                body = {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": min(self.config.max_tokens, model_config.get('max_tokens', 4000)),
                    "temperature": self.config.temperature,
                    "messages": messages
                }

                # Add system message if supported
                if model_config.get('supports_system', False):
                    body["system"] = "You are an expert web performance analyst. Always respond with valid JSON."

            else:
                # Other models (Titan, etc.) use different format
                body = {
                    "inputText": f"System: You are an expert web performance analyst. Always respond with valid JSON.\n\nUser: {prompt}",
                    "textGenerationConfig": {
                        "maxTokenCount": min(self.config.max_tokens, model_config.get('max_tokens', 8000)),
                        "temperature": self.config.temperature,
                        "stopSequences": []
                    }
                }

            # Make API call to Bedrock
            response = self.bedrock_client.invoke_model(
                modelId=self.config.model,
                body=json.dumps(body)
            )

            # Parse response based on model type
            response_body = json.loads(response['body'].read())

            if 'claude' in self.config.model.lower():
                response_content = response_body['content'][0]['text']
            else:
                response_content = response_body['results'][0]['outputText']

            # Update conversation history
            self.conversation_history.append({"role": "user", "content": prompt})
            self.conversation_history.append({"role": "assistant", "content": response_content})

            # Keep only last 8 messages to prevent context explosion
            if len(self.conversation_history) > 8:
                self.conversation_history = self.conversation_history[-8:]

            self.logger.debug("Bedrock query successful", model=self.config.model)
            return response_content

        except ClientError as e:
            self.logger.error("Bedrock API error", error=str(e), model=self.config.model)
            raise RuntimeError(f"Bedrock communication error: {e}")

        except Exception as e:
            self.logger.error("Error querying Bedrock", error=str(e))
            raise

    def _parse_action_response(self, response: str) -> Optional[Dict[str, Any]]:
        """Parse Bedrock response into structured action."""
        try:
            # Extract JSON from response
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

            # Return None if Bedrock says no action
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

            self.logger.debug("Parsed Bedrock action", action=action_data)
            return action_data

        except json.JSONDecodeError as e:
            self.logger.error("Failed to parse Bedrock response as JSON", response=response[:200], error=str(e))
            return None

        except ValueError as e:
            self.logger.error("Invalid Bedrock action response", error=str(e))
            return None

        except Exception as e:
            self.logger.error("Unexpected error parsing Bedrock response", error=str(e))
            return None

    async def analyze_performance_results(
        self,
        interaction_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Have Bedrock analyze performance results and provide insights.

        Args:
            interaction_results: List of all interaction results

        Returns:
            Analysis and recommendations from Bedrock
        """
        try:
            # Build analysis prompt
            prompt = self._build_analysis_prompt(interaction_results)

            # Query Bedrock
            response = await self._query_bedrock(prompt)

            # Parse response
            analysis = self._parse_analysis_response(response)

            return analysis

        except Exception as e:
            self.logger.error("Failed to analyze performance results", error=str(e))
            return {"error": str(e)}

    def _build_analysis_prompt(self, results: List[Dict[str, Any]]) -> str:
        """Build prompt for final performance analysis."""
        results_summary = []
        for result in results:
            action = result.get("action", {})
            performance = result.get("performance", {})
            inp_score = performance.get("inp_score", "unknown")

            summary = f"Action: {action.get('action')} on '{action.get('selector')}' -> INP: {inp_score}ms"
            results_summary.append(summary)

        prompt = f"""Analyze the results of an automated INP (Interaction to Next Paint) performance test.

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

Focus on identifying patterns and providing actionable recommendations for improving INP performance."""

        return prompt.strip()

    def _parse_analysis_response(self, response: str) -> Dict[str, Any]:
        """Parse Bedrock analysis response."""
        try:
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
        """Clean up Bedrock client resources."""
        self.logger.info("Cleaning up Bedrock client")
        # Bedrock client doesn't require explicit cleanup
        self.logger.info("Bedrock client cleanup complete")