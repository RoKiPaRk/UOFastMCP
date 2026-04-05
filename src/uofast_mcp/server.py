"""
U2 Unidata MCP Server
=====================

An MCP (Model Context Protocol) server that provides tools for connecting to
and querying U2 Unidata databases.

Features:
- Automatic connection management with configuration
- Connection pooling and caching
- List available files in the account
- Execute SELECT queries on files
- Read individual records
- Execute custom UniQuery commands

Prerequisites:
    pip install mcp uopy

Usage:
    Configure in your MCP client (e.g., Claude Desktop) with connection parameters
    in the environment or config.
"""

import asyncio
import json
import logging
from typing import Any

from mcp.server import Server
from mcp.types import Tool, TextContent

from .core.connection_manager import ConnectionManager
from .core.uopy_operations import UnidataOperations
from .utils.config_loader import ConfigLoader
from .security.middleware import get_current_user_from_context, require_tool_permission
from .security.audit import audit_logger
from .security.database import AsyncSessionLocal

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uofast-mcp.server")

# Global instances
connection_manager: ConnectionManager = None
config_loader: ConfigLoader = None


def initialize_server():
    """Initialize the server with configuration and connections."""
    global connection_manager, config_loader

    logger.info("Starting Unidata MCP Server")
    logger.info("=" * 80)

    # Initialize config loader
    config_loader = ConfigLoader()

    # Priority 1: Try to load from INI config file
    config = config_loader.load_config_file()
    connections_loaded = False

    # Default settings (env vars override INI values)
    import os as _os
    min_connections = int(_os.getenv("UNIDATA_MIN_CONNECTIONS", "0"))
    max_connections = int(_os.getenv("UNIDATA_MAX_CONNECTIONS", "0"))
    default_connection_name = "default"
    log_level = "INFO"

    if config:
        try:
            # Get server settings
            settings = config_loader.get_server_settings(config)
            # Env vars take precedence; fall back to INI values only when env not set
            if not _os.getenv("UNIDATA_MIN_CONNECTIONS"):
                min_connections = settings["min_connections"]
            if not _os.getenv("UNIDATA_MAX_CONNECTIONS"):
                max_connections = settings["max_connections"]
            default_connection_name = settings["default_connection"]
            log_level = settings["log_level"]

            # Setup logging
            config_loader.setup_logging(log_level)

            logger.info(f"Min connections: {min_connections}")
            logger.info(f"Max connections: {max_connections}")
            logger.info(f"Default connection: {default_connection_name}")

            # Initialize connection manager
            connection_manager = ConnectionManager(
                default_connection_name=default_connection_name,
                min_connections=min_connections,
                max_connections=max_connections,
            )

            # Load all connection definitions from config file
            connection_configs = config_loader.load_connections_from_config(config)

            if connection_configs:
                logger.info(f"Found {len(connection_configs)} connection(s) in config file")

                # Auto-connect to connections marked with auto_connect=true
                for conn_name, conn_config in connection_configs.items():
                    if conn_config.get("auto_connect", False):
                        try:
                            logger.info(f"Auto-connecting to '{conn_name}'...")
                            connection_manager.get_or_create_connection(conn_name, conn_config)
                            logger.info(f"Successfully connected to '{conn_name}'")
                            connections_loaded = True
                        except Exception as e:
                            logger.error(f"Failed to auto-connect to '{conn_name}': {e}")
                    else:
                        # Register config so the connection can be created on demand
                        connection_manager.register_config(conn_name, conn_config)
                        logger.info(f"Connection '{conn_name}' registered (auto_connect=false)")

            else:
                logger.info("Config file found but no connections defined")

        except Exception as e:
            logger.error(f"Error loading connections from config file: {e}")

    # Initialize connection manager if not already done
    if connection_manager is None:
        connection_manager = ConnectionManager(
            default_connection_name=default_connection_name,
            min_connections=min_connections,
            max_connections=max_connections,
        )

    # Priority 2: If no config file connections, try environment variables
    if not connections_loaded:
        try:
            env_config = config_loader.load_connection_from_env()
            if env_config:
                logger.info("Found connection parameters in environment variables")
                connection_manager.get_or_create_connection(
                    connection_manager.default_connection_name,
                    env_config
                )
                logger.info("Default connection established from environment")
                connections_loaded = True
            else:
                logger.info("No environment variables set")
        except Exception as e:
            logger.warning(f"Could not auto-connect from environment: {e}")

    # Summary
    if not connections_loaded:
        logger.info("No auto-connections established - connections will be created on demand")
    else:
        logger.info(f"Ready with {connection_manager.connection_count()} active connection(s)")

    # Warn if active connections fall below the configured minimum
    pool = connection_manager.check_pool_health()
    if pool["below_minimum"]:
        logger.warning(
            f"Active connections ({pool['active']}) below min_connections "
            f"({pool['min_connections']}). Check auto_connect settings."
        )

    logger.info("=" * 80)


# Create the MCP server
app = Server("unidata-mcp-server")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="list_files",
            description="List available files in the current Unidata account",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="select_records",
            description="SELECT data from a Unidata file and return matching record IDs.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_name": {
                        "type": "string",
                        "description": "Name of the file to select from"
                    },
                    "criteria": {
                        "type": "string",
                        "description": "Optional selection criteria (e.g., 'WITH STATUS = \"ACTIVE\"')",
                        "default": ""
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of records to return (use SAMPLE)",
                        "default": 100
                    }
                },
                "required": ["file_name"]
            }
        ),
        Tool(
            name="read_record",
            description="Read a specific record from a Unidata file by its ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_name": {
                        "type": "string",
                        "description": "Name of the file to read from"
                    },
                    "record_id": {
                        "type": "string",
                        "description": "ID of the record to read"
                    }
                },
                "required": ["file_name", "record_id"]
            }
        ),
        Tool(
            name="execute_command",
            description="Execute a Unidata command (e.g., LIST, COUNT, SELECT, etc.).",
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The UniQuery command to execute"
                    }
                },
                "required": ["command"]
            }
        ),
        Tool(
            name="query_file",
            description="Query a file with SELECT criteria and return the actual record data (not just IDs).",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_name": {
                        "type": "string",
                        "description": "Name of the file to query"
                    },
                    "criteria": {
                        "type": "string",
                        "description": "Optional selection criteria (e.g., 'WITH STATUS = \"ACTIVE\"')",
                        "default": ""
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of records to return",
                        "default": 10
                    }
                },
                "required": ["file_name"]
            }
        ),
        Tool(
            name="add_connection",
            description="Add a new named connection to the connection cache for later use.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name for this connection (e.g., 'production', 'test')"
                    },
                    "host": {
                        "type": "string",
                        "description": "Unidata server hostname or IP address"
                    },
                    "port": {
                        "type": "integer",
                        "description": "Unidata server port (typically 31438)",
                        "default": 31438
                    },
                    "username": {
                        "type": "string",
                        "description": "Username for authentication"
                    },
                    "password": {
                        "type": "string",
                        "description": "Password for authentication"
                    },
                    "account": {
                        "type": "string",
                        "description": "Full path to the Unidata account (e.g., C:\\U2\\UD83\\DEMO)"
                    },
                    "service": {
                        "type": "string",
                        "description": "UniRPC service name",
                        "default": "udcs"
                    }
                },
                "required": ["name", "host", "username", "password", "account"]
            }
        ),
        Tool(
            name="get_dict_items",
            description="Get DICT items for a file, optionally filtered by type (D for data fields, V for virtual fields). This shows available field definitions.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_name": {
                        "type": "string",
                        "description": "Name of the file to get DICT items for"
                    },
                    "dict_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of DICT types to filter (e.g., [\"D\", \"V\"]). If not specified, returns all DICT items.",
                        "default": ["D", "V"]
                    }
                },
                "required": ["file_name"]
            }
        ),
        Tool(
            name="query_with_dict_fields",
            description="Query a file and return data for specific DICT fields. First use get_dict_items to discover available fields, then use this tool to query with selected fields.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_name": {
                        "type": "string",
                        "description": "Name of the file to query"
                    },
                    "dict_fields": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of DICT field names to include in the output (e.g., [\"CUSTOMER.NAME\", \"ADDRESS\", \"PHONE\"])"
                    },
                    "criteria": {
                        "type": "string",
                        "description": "Optional selection criteria (e.g., 'STATUS EQ \"ACTIVE\"')",
                        "default": ""
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of records to return",
                        "default": 10
                    }
                },
                "required": ["file_name", "dict_fields"]
            }
        ),
        Tool(
            name="list_connections",
            description="List all active cached connections.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="close_connection",
            description="Close and remove a specific connection from the cache.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name of the connection to close",
                        "default": "default"
                    }
                }
            }
        ),
        Tool(
            name="read_dict_item",
            description="Read a specific DICT item from a file's dictionary. DICT items define field attributes like type, field number, conversion, etc.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_name": {
                        "type": "string",
                        "description": "Name of the file whose DICT to read from"
                    },
                    "dict_item_name": {
                        "type": "string",
                        "description": "Name of the DICT item to read"
                    }
                },
                "required": ["file_name", "dict_item_name"]
            }
        ),
        Tool(
            name="write_dict_item",
            description="Write or update a DICT item in a file's dictionary. This creates a new DICT item or updates an existing one. Data should be a list of attribute values following U2 DICT structure.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_name": {
                        "type": "string",
                        "description": "Name of the file whose DICT to write to"
                    },
                    "dict_item_name": {
                        "type": "string",
                        "description": "Name of the DICT item to create/update"
                    },
                    "data": {
                        "description": "DICT item data as a list of attribute values. Typical structure: [type, field_number, conversion, column_heading, format, association]",
                        "oneOf": [
                            {"type": "array", "items": {"type": "string"}},
                            {"type": "string"}
                        ]
                    }
                },
                "required": ["file_name", "dict_item_name", "data"]
            }
        ),
        Tool(
            name="update_dict_item",
            description="Update an existing DICT item. This is an alias for write_dict_item - it reads the existing item, then writes the updated data.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_name": {
                        "type": "string",
                        "description": "Name of the file whose DICT to update"
                    },
                    "dict_item_name": {
                        "type": "string",
                        "description": "Name of the DICT item to update"
                    },
                    "data": {
                        "description": "Updated DICT item data as a list of attribute values",
                        "oneOf": [
                            {"type": "array", "items": {"type": "string"}},
                            {"type": "string"}
                        ]
                    }
                },
                "required": ["file_name", "dict_item_name", "data"]
            }
        ),
        Tool(
            name="delete_dict_item",
            description="Delete a DICT item from a file's dictionary. This permanently removes the field definition.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_name": {
                        "type": "string",
                        "description": "Name of the file whose DICT to delete from"
                    },
                    "dict_item_name": {
                        "type": "string",
                        "description": "Name of the DICT item to delete"
                    }
                },
                "required": ["file_name", "dict_item_name"]
            }
        ),
        Tool(
            name="read_record_with_fields",
            description="Read specific DICT fields from a record using field names. This returns only the requested fields as a dictionary, making it easier to work with structured data.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_name": {
                        "type": "string",
                        "description": "Name of the file to read from"
                    },
                    "record_id": {
                        "type": "string",
                        "description": "ID of the record to read"
                    },
                    "field_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of DICT field names to retrieve (e.g., [\"CUSTOMER.NAME\", \"ADDRESS\", \"PHONE\"])"
                    }
                },
                "required": ["file_name", "record_id", "field_names"]
            }
        ),
        Tool(
            name="write_record_with_fields",
            description="Write specific DICT fields to a record using field names. This allows updating only specific fields without affecting other fields in the record.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_name": {
                        "type": "string",
                        "description": "Name of the file to write to"
                    },
                    "record_id": {
                        "type": "string",
                        "description": "ID of the record to write"
                    },
                    "field_data": {
                        "type": "object",
                        "description": "Dictionary mapping field names to their values (e.g., {\"CUSTOMER.NAME\": \"John Doe\", \"PHONE\": \"555-1234\"})"
                    }
                },
                "required": ["file_name", "record_id", "field_data"]
            }
        ),
        Tool(
            name="read_bp_program",
            description="Read source code from a UniData BP (Basic Program) file. Returns the program source as text.",
            inputSchema={
                "type": "object",
                "properties": {
                    "bp_file": {
                        "type": "string",
                        "description": "Name of the BP file (e.g., 'BP', 'BP.UTILS')",
                        "default": "BP"
                    },
                    "program_name": {
                        "type": "string",
                        "description": "Name of the program to read"
                    }
                },
                "required": ["program_name"]
            }
        ),
        Tool(
            name="write_bp_program",
            description="Write source code to a UniData BP (Basic Program) file. Creates or overwrites the program.",
            inputSchema={
                "type": "object",
                "properties": {
                    "bp_file": {
                        "type": "string",
                        "description": "Name of the BP file (e.g., 'BP', 'BP.UTILS')",
                        "default": "BP"
                    },
                    "program_name": {
                        "type": "string",
                        "description": "Name of the program to write"
                    },
                    "source_code": {
                        "type": "string",
                        "description": "The UniBasic source code to write"
                    }
                },
                "required": ["program_name", "source_code"]
            }
        ),
        Tool(
            name="compile_bp_program",
            description="Compile a UniData BP (Basic Program) using the BASIC command. Returns compilation output including any errors.",
            inputSchema={
                "type": "object",
                "properties": {
                    "bp_file": {
                        "type": "string",
                        "description": "Name of the BP file (e.g., 'BP', 'BP.UTILS')",
                        "default": "BP"
                    },
                    "program_name": {
                        "type": "string",
                        "description": "Name of the program to compile"
                    }
                },
                "required": ["program_name"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls."""
    global connection_manager
    logger.debug("Tool called: %s", name)

    # --- Authentication & Authorization ---
    user = get_current_user_from_context()
    if user is not None:
        async with AsyncSessionLocal() as _db:
            await require_tool_permission(name, user, _db)
        audit_logger.log_event(
            user_id=user.id,
            tool_name=name,
            action="call",
            params=arguments or {},
            result_status="success",
        )

    try:
        if name == "add_connection":
            conn_name = arguments["name"]
            config = {
                "host": arguments["host"],
                "port": arguments.get("port", 31438),
                "username": arguments["username"],
                "password": arguments["password"],
                "account": arguments["account"],
                "service": arguments.get("service", "udcs")
            }

            # Create and cache the connection
            connection_manager.get_or_create_connection(conn_name, config)

            return [TextContent(
                type="text",
                text=f"Connection '{conn_name}' created successfully.\n"
                     f"Host: {config['host']}:{config['port']}\n"
                     f"Account: {config['account']}\n"
                     f"Status: Connected"
            )]

        elif name == "list_connections":
            if connection_manager.connection_count() == 0:
                return [TextContent(
                    type="text",
                    text="No active connections.\n\n"
                         "Connections will be created automatically from environment variables "
                         "or you can add them using the add_connection tool."
                )]

            conn_info_dict = connection_manager.list_connections()
            conn_info = []
            for conn_name, info in conn_info_dict.items():
                conn_info.append(
                    f"- {conn_name}: {info['host']}:{info['port']} "
                    f"({info['account']}) - {info['status']} "
                    f"[pool: {info['pool_available']}/{info['pool_total']} available]"
                )

            return [TextContent(
                type="text",
                text="Active connections:\n" + "\n".join(conn_info)
            )]

        elif name == "close_connection":
            conn_name = arguments.get("name", connection_manager.default_connection_name)

            if connection_manager.close_connection(conn_name):
                return [TextContent(
                    type="text",
                    text=f"Connection '{conn_name}' closed and removed from cache."
                )]
            else:
                return [TextContent(
                    type="text",
                    text=f"Connection '{conn_name}' not found in cache."
                )]

        # All other operations require a pooled session
        async with connection_manager.session() as session:
            ops = UnidataOperations(session)

            if name == "list_files":
                output = ops.list_files()
                return [TextContent(
                    type="text",
                    text=f"Available files in account:\n\n{output}"
                )]

            elif name == "select_records":
                file_name = arguments["file_name"]
                criteria = arguments.get("criteria", "")
                limit = arguments.get("limit", 100)

                result = ops.select_records(file_name, criteria, limit)

                return [TextContent(
                    type="text",
                    text=f"Query: {result['command']}\n\n"
                         f"Found {result['count']} records\n\n"
                         f"Record IDs: {json.dumps(result['record_ids'], indent=2)}"
                )]

            elif name == "read_record":
                file_name = arguments["file_name"]
                record_id = arguments["record_id"]

                record = ops.read_record(file_name, record_id)

                return [TextContent(
                    type="text",
                    text=f"Record ID: {record_id}\n"
                         f"File: {file_name}\n\n"
                         f"Data:\n{json.dumps(record, indent=2)}"
                )]

            elif name == "execute_command":
                command = arguments["command"]
                output = ops.execute_command(command)

                return [TextContent(
                    type="text",
                    text=f"Command: {command}\n"
                         f"Output:  {output}\n"
                )]

            elif name == "query_file":
                file_name = arguments["file_name"]
                criteria = arguments.get("criteria", "")
                limit = arguments.get("limit", 10)

                records = ops.query_file(file_name, criteria, limit)

                if not records:
                    return [TextContent(
                        type="text",
                        text=f"No records found"
                    )]

                # Build SELECT command for display
                if criteria:
                    select_cmd = f"SELECT {file_name} {criteria} SAMPLE {limit}"
                else:
                    select_cmd = f"SELECT {file_name} SAMPLE {limit}"

                return [TextContent(
                    type="text",
                    text=f"Query: {select_cmd}\n\n"
                         f"Found {len(records)} records\n\n"
                         f"Records:\n{json.dumps(records, indent=2)}"
                )]

            elif name == "get_dict_items":
                file_name = arguments["file_name"]
                dict_types = arguments.get("dict_types")

                result = ops.get_dict_items(file_name, dict_types)

                type_filter = ""
                if dict_types:
                    type_filter = f" (filtered by types: {', '.join(dict_types)})"

                return [TextContent(
                    type="text",
                    text=f"DICT items for {file_name}{type_filter}\n\n"
                         f"Command: {result['command']}\n"
                         f"Found {result['count']} DICT items\n\n"
                         f"Available DICT fields:\n{json.dumps(result['dict_items'], indent=2)}\n\n"
                         f"Use these field names with query_with_dict_fields to retrieve specific field data."
                )]

            elif name == "query_with_dict_fields":
                file_name = arguments["file_name"]
                dict_fields = arguments["dict_fields"]
                criteria = arguments.get("criteria", "")
                limit = arguments.get("limit", 10)

                records = ops.query_with_dict_fields(file_name, dict_fields, criteria, limit)

                if not records:
                    return [TextContent(
                        type="text",
                        text=f"No records found"
                    )]

                # Build description
                fields_str = ", ".join(dict_fields)
                criteria_str = f" with criteria: {criteria}" if criteria else ""

                return [TextContent(
                    type="text",
                    text=f"Query: {file_name}{criteria_str}\n"
                         f"Fields: {fields_str}\n"
                         f"Found {len(records)} records\n\n"
                         f"Records:\n{json.dumps(records, indent=2)}"
                )]

            elif name == "read_dict_item":
                file_name = arguments["file_name"]
                dict_item_name = arguments["dict_item_name"]

                dict_item = ops.read_dict_item(file_name, dict_item_name)

                return [TextContent(
                    type="text",
                    text=f"DICT Item: {dict_item_name}\n"
                         f"File: {file_name}\n\n"
                         f"Data:\n{json.dumps(dict_item, indent=2)}"
                )]

            elif name == "write_dict_item" or name == "update_dict_item":
                file_name = arguments["file_name"]
                dict_item_name = arguments["dict_item_name"]
                data = arguments["data"]

                # Handle both array and string data
                if isinstance(data, str):
                    dict_data = data
                else:
                    dict_data = data

                ops.write_dict_item(file_name, dict_item_name, dict_data)

                action = "updated" if name == "update_dict_item" else "written"
                return [TextContent(
                    type="text",
                    text=f"DICT item '{dict_item_name}' successfully {action} in {file_name}\n\n"
                         f"Data: {json.dumps(dict_data, indent=2)}"
                )]

            elif name == "delete_dict_item":
                file_name = arguments["file_name"]
                dict_item_name = arguments["dict_item_name"]

                ops.delete_dict_item(file_name, dict_item_name)

                return [TextContent(
                    type="text",
                    text=f"DICT item '{dict_item_name}' successfully deleted from {file_name}"
                )]

            elif name == "read_record_with_fields":
                file_name = arguments["file_name"]
                record_id = arguments["record_id"]
                field_names = arguments["field_names"]

                record_data = ops.read_record_with_named_fields(file_name, record_id, field_names)

                return [TextContent(
                    type="text",
                    text=f"Record ID: {record_id}\n"
                         f"File: {file_name}\n"
                         f"Fields: {', '.join(field_names)}\n\n"
                         f"Data:\n{json.dumps(record_data, indent=2)}"
                )]

            elif name == "write_record_with_fields":
                file_name = arguments["file_name"]
                record_id = arguments["record_id"]
                field_data = arguments["field_data"]

                ops.write_record_with_named_fields(file_name, record_id, field_data)

                field_names = list(field_data.keys())
                return [TextContent(
                    type="text",
                    text=f"Record '{record_id}' successfully updated in {file_name}\n\n"
                         f"Updated fields: {', '.join(field_names)}\n"
                         f"Data:\n{json.dumps(field_data, indent=2)}"
                )]

            elif name == "read_bp_program":
                bp_file = arguments.get("bp_file", "BP")
                program_name = arguments["program_name"]

                source_code = ops.read_bp_program(bp_file, program_name)

                return [TextContent(
                    type="text",
                    text=f"Program: {program_name}\n"
                         f"File: {bp_file}\n\n"
                         f"Source Code:\n{source_code}"
                )]

            elif name == "write_bp_program":
                bp_file = arguments.get("bp_file", "BP")
                program_name = arguments["program_name"]
                source_code = arguments["source_code"]

                ops.write_bp_program(bp_file, program_name, source_code)

                line_count = len(source_code.split("\n"))
                return [TextContent(
                    type="text",
                    text=f"Program '{program_name}' successfully written to {bp_file}\n\n"
                         f"Lines written: {line_count}"
                )]

            elif name == "compile_bp_program":
                bp_file = arguments.get("bp_file", "BP")
                program_name = arguments["program_name"]

                result = ops.compile_bp_program(bp_file, program_name)

                return [TextContent(
                    type="text",
                    text=f"Compilation: {result['command']}\n"
                         f"Status: {result['status']}\n\n"
                         f"Output:\n{result['response']}"
                )]

            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        logger.error(f"Error in {name}: {str(e)}", exc_info=True)
        user = get_current_user_from_context()
        if user is not None:
            audit_logger.log_event(
                user_id=user.id,
                tool_name=name,
                action="call",
                params=arguments or {},
                result_status="error",
                error_message=str(e),
            )
        return [TextContent(
            type="text",
            text=f"Error: {str(e)}"
        )]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
# The server is started via the FastAPI app in src/uofast_mcp/app.py:
#
#   uvicorn src.uofast_mcp.app:app --host 0.0.0.0 --port 8000
#
# app.py handles lifecycle (init_db, initialize_server, shutdown) and
# mounts this MCP Server (app) over HTTP/SSE transport with auth middleware.
# ---------------------------------------------------------------------------
