"""
Mistral Tool Call Formatter
============================

Uses Mistral in Ollama to intelligently format tool calling and parameter passing
from natural language prompts to properly structured MCP tool calls.

Features:
- Understands tool schemas and requirements
- Extracts parameters from natural language
- Validates and formats arguments according to schema
- Handles complex parameter types (arrays, objects, etc.)
"""

import json
import re
from typing import Dict, Any, List, Optional
import requests


class MistralToolFormatter:
    """
    Uses Mistral to intelligently parse user queries and format them into
    proper MCP tool calls with correctly extracted parameters.
    """

    def __init__(self, ollama_url: str = "http://192.168.2.232:11434", model: str = "mistral"):
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model

    def _post(self, endpoint: str, payload: dict) -> dict:
        """Make a POST request to Ollama."""
        response = requests.post(
            f"{self.ollama_url}{endpoint}",
            json=payload,
            timeout=60
        )
        return response.json()

    def _build_tool_context(self, tools: List[Dict[str, Any]]) -> str:
        """Build a context string describing available tools."""
        tool_descriptions = []

        for tool in tools:
            name = tool['name']
            desc = tool.get('description', '')
            schema = tool.get('inputSchema', {})
            properties = schema.get('properties', {})
            required = schema.get('required', [])

            tool_desc = f"Tool: {name}\n"
            tool_desc += f"Description: {desc}\n"

            if properties:
                tool_desc += "Parameters:\n"
                for param_name, param_info in properties.items():
                    param_type = param_info.get('type', 'string')
                    param_desc = param_info.get('description', '')
                    is_required = param_name in required
                    default = param_info.get('default', None)

                    req_marker = " (REQUIRED)" if is_required else " (optional)"
                    tool_desc += f"  - {param_name} ({param_type}){req_marker}: {param_desc}\n"
                    if default is not None:
                        tool_desc += f"    Default: {default}\n"

            tool_descriptions.append(tool_desc)

        return "\n\n".join(tool_descriptions)

    def format_tool_call(
        self,
        query: str,
        tool_name: str,
        tool_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Use Mistral to extract and format parameters from a query for a specific tool.

        Args:
            query: User's natural language query
            tool_name: Name of the tool to call
            tool_metadata: Tool metadata including inputSchema

        Returns:
            Dictionary of properly formatted arguments
        """

        schema = tool_metadata.get('inputSchema', {})
        properties = schema.get('properties', {})
        required = schema.get('required', [])

        # Build prompt for Mistral
        prompt = f"""You are a parameter extraction expert. Extract and format parameters from the user query for a tool call.

Tool: {tool_name}
Description: {tool_metadata.get('description', '')}

Schema:
{json.dumps(schema, indent=2)}

User Query: "{query}"

Your task:
1. Extract relevant parameter values from the query
2. Format them according to the schema
3. Fill in sensible defaults for missing optional parameters
4. Return ONLY a valid JSON object with the parameters

IMPORTANT RULES:
- For file_name parameters: Extract database file names (often UPPERCASE words or words after "from", "in", "table")
- For record_id parameters: Extract the specific ID/key mentioned (e.g., "123", "ABC", "XYZ" from phrases like "record 123", "id ABC", "customer XYZ")
- For limit parameters: Extract numbers from phrases like "first 10", "limit 20", "top 5" (default: 10)
- For criteria parameters: Extract selection criteria from phrases like "WITH", "WHERE", conditions (default: "")
- For dict_fields/field_names (arrays): Extract field names mentioned in query as JSON array
- For command parameters: Use the entire query or relevant portion
- For empty/missing values: Use appropriate defaults based on type (empty string "", empty array [], 0, etc.)
- Return ONLY the JSON object, no explanations

Example outputs:
{{"file_name": "CUSTOMER", "limit": 10}}
{{"file_name": "PRODUCTS", "criteria": "WITH PRICE > 100", "limit": 20}}
{{"file_name": "ORDERS", "dict_fields": ["ORDER.DATE", "CUSTOMER.NAME", "TOTAL"]}}
{{"file_name": "CUSTOMER", "record_id": "123"}}
{{"file_name": "PRODUCTS", "record_id": "ABC123", "field_names": ["NAME", "PRICE"]}}

Now extract parameters from the user query and return the JSON object:"""

        try:
            # Call Mistral via Ollama
            response = self._post(
                "/api/generate",
                {
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.1,  # Low temperature for more deterministic output
                    "format": "json"  # Request JSON output
                }
            )

            generated_text = response.get("response", "").strip()

            # Try to extract JSON from the response
            # Sometimes the model wraps it in markdown or adds extra text
            json_match = re.search(r'\{.*\}', generated_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                arguments = json.loads(json_str)
            else:
                # Fallback: try to parse the whole response
                arguments = json.loads(generated_text)

            # Validate and ensure required parameters are present
            for req_param in required:
                if req_param not in arguments:
                    # Provide default based on type
                    param_type = properties.get(req_param, {}).get('type', 'string')
                    if param_type == 'string':
                        arguments[req_param] = ""
                    elif param_type in ['integer', 'number']:
                        arguments[req_param] = 0
                    elif param_type == 'array':
                        arguments[req_param] = []
                    elif param_type == 'object':
                        arguments[req_param] = {}
                    elif param_type == 'boolean':
                        arguments[req_param] = False

            return arguments

        except (json.JSONDecodeError, KeyError, requests.RequestException) as e:
            # Fallback to heuristic-based extraction if Mistral fails
            print(f"Mistral formatting failed: {e}. Falling back to heuristics.")
            return self._fallback_extract(query, tool_name, tool_metadata)

    def _fallback_extract(
        self,
        query: str,
        tool_name: str,
        tool_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Fallback heuristic-based parameter extraction.
        This is used if Mistral fails or is unavailable.
        """
        from typing import Optional

        schema = tool_metadata.get('inputSchema', {})
        properties = schema.get('properties', {})
        required = schema.get('required', [])
        arguments = {}

        # Helper functions
        def extract_file_name(q: str) -> Optional[str]:
            words = q.split()
            for word in words:
                clean = re.sub(r'[^\w]', '', word)
                if clean.isupper() and len(clean) > 2:
                    return clean

            patterns = [r'from\s+([A-Za-z0-9_]+)', r'in\s+([A-Za-z0-9_]+)',
                       r'table\s+([A-Za-z0-9_]+)', r'file\s+([A-Za-z0-9_]+)']
            for pattern in patterns:
                match = re.search(pattern, q.lower())
                if match:
                    return match.group(1).upper()
            return None

        def extract_limit(q: str) -> int:
            patterns = [r'limit\s+(\d+)', r'first\s+(\d+)', r'top\s+(\d+)', r'(\d+)\s+records']
            for pattern in patterns:
                match = re.search(pattern, q.lower())
                if match:
                    return int(match.group(1))
            return 10

        def extract_record_id(q: str) -> Optional[str]:
            """Extract record ID from queries like 'show record 123', 'get id ABC', 'record with id XYZ'"""
            patterns = [
                r'record\s+(?:id\s+)?["\']?([A-Za-z0-9_\-\.]+)["\']?',
                r'id\s+["\']?([A-Za-z0-9_\-\.]+)["\']?',
                r'with\s+id\s+["\']?([A-Za-z0-9_\-\.]+)["\']?',
                r'key\s+["\']?([A-Za-z0-9_\-\.]+)["\']?'
            ]
            for pattern in patterns:
                match = re.search(pattern, q.lower())
                if match:
                    return match.group(1)
            return None

        # Tool-specific extraction
        if tool_name == "list_files":
            return {}

        elif tool_name == "read_record":
            if 'file_name' in properties:
                arguments['file_name'] = extract_file_name(query) or ""
            if 'record_id' in properties:
                arguments['record_id'] = extract_record_id(query) or ""

        elif tool_name in ["get_dict_items", "select_records", "query_file"]:
            if 'file_name' in properties:
                arguments['file_name'] = extract_file_name(query) or ""
            if 'limit' in properties:
                arguments['limit'] = extract_limit(query)
            if 'criteria' in properties:
                arguments['criteria'] = ""

        elif tool_name == "query_with_dict_fields":
            if 'file_name' in properties:
                arguments['file_name'] = extract_file_name(query) or ""
            if 'dict_fields' in properties:
                arguments['dict_fields'] = []
            if 'limit' in properties:
                arguments['limit'] = extract_limit(query)
            if 'criteria' in properties:
                arguments['criteria'] = ""

        elif tool_name == "execute_command":
            if 'command' in properties:
                arguments['command'] = query

        else:
            # Generic handling
            for param_name, param_schema in properties.items():
                param_type = param_schema.get('type', 'string')
                if param_name in required:
                    if param_type == 'string':
                        arguments[param_name] = ""
                    elif param_type in ['integer', 'number']:
                        arguments[param_name] = 0
                    elif param_type == 'boolean':
                        arguments[param_name] = False
                    elif param_type == 'array':
                        arguments[param_name] = []
                    elif param_type == 'object':
                        arguments[param_name] = {}

        return arguments

    def select_tools_and_format(
        self,
        query: str,
        available_tools: List[Dict[str, Any]],
        max_tools: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Use Mistral to select the most relevant tools and format their parameters.

        Args:
            query: User's natural language query
            available_tools: List of available tool metadata
            max_tools: Maximum number of tools to select

        Returns:
            List of tool calls with formatted arguments [{"name": "tool_name", "arguments": {...}}, ...]
        """

        # Build tool context
        tool_context = self._build_tool_context(available_tools)

        # Build prompt for tool selection
        prompt = f"""You are a tool selection expert. Analyze the user query and select the most appropriate tool(s) to answer it.

Available Tools:
{tool_context}

User Query: "{query}"

Your task:
1. Identify which tool(s) would best answer this query
2. Select up to {max_tools} most relevant tools
3. Return ONLY a JSON array of tool names in order of relevance

IMPORTANT SELECTION RULES:
- If query mentions a specific record ID/key (e.g., "record 123", "id ABC", "customer XYZ"), use "read_record"
- If query asks for multiple records or uses criteria/conditions (e.g., "first 10", "all records", "where..."), use "select_records"
- If query asks for specific fields from a record with an ID, use "read_record_with_fields"
- If query asks to list files/tables, use "list_files"
- If query is a raw UniQuery command, use "execute_command"

FORMATTING:
- Return ONLY the JSON array, no explanations
- Use exact tool names from the list above
- Order tools by relevance (most relevant first)
- Maximum {max_tools} tools

Example outputs:
["read_record"]  (for "show me record 123 from CUSTOMER")
["select_records"]  (for "show me first 10 records from CUSTOMER")
["read_record_with_fields"]  (for "get NAME and ADDRESS fields from customer record 123")

Return the JSON array now:"""

        try:
            # Call Mistral for tool selection
            response = self._post(
                "/api/generate",
                {
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.1,
                    "format": "json"
                }
            )

            generated_text = response.get("response", "").strip()

            # Extract JSON array
            json_match = re.search(r'\[.*\]', generated_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                selected_tool_names = json.loads(json_str)
            else:
                selected_tool_names = json.loads(generated_text)

            # Format parameters for each selected tool
            tool_calls = []
            for tool_name in selected_tool_names[:max_tools]:
                # Find the tool metadata
                tool_meta = next((t for t in available_tools if t['name'] == tool_name), None)
                if tool_meta:
                    arguments = self.format_tool_call(query, tool_name, tool_meta)
                    tool_calls.append({
                        "name": tool_name,
                        "arguments": arguments
                    })

            return tool_calls

        except (json.JSONDecodeError, KeyError, requests.RequestException) as e:
            print(f"Mistral tool selection failed: {e}. Falling back to similarity search.")
            # Fallback to the existing similarity-based search
            return []
