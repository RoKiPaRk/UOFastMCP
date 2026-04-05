# UOFast MCP Server - Complete Documentation

> **Model Context Protocol server for U2 Unidata databases**
> Connect Claude and other MCP clients to query and manage U2 Unidata via natural language.

---

## 📑 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [Configuration](#configuration)
- [Available Tools](#available-tools)
- [Usage Examples](#usage-examples)
- [Project Structure](#project-structure)
- [Architecture](#architecture)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [Changelog](#changelog)

---

## Overview

The UOFast MCP Server enables Claude Desktop and other MCP-compatible clients to interact with U2 Unidata databases through natural language. It implements the Model Context Protocol (MCP) to provide a standardized interface for database operations.

### What You Can Do

- **Query databases** using natural language
- **List and explore** available files and schemas
- **Read and write** data and DICT items
- **Execute** custom UniQuery commands
- **Manage** multiple database connections simultaneously
- **Automate** database operations through AI assistants

---

## Features

### Core Capabilities

#### 1. Automatic Connection Management
- Auto-connect from environment variables or config files on startup
- Persistent connections across tool calls
- Automatic reconnection if connection drops
- Support for multiple named connections to different accounts
- Configurable connection limits

#### 2. Database Operations
- **File Operations**: List files, get DICT items, query with field names
- **Record Operations**: Read, write, delete records
- **DICT Management**: Read, create, update, delete DICT items
- **Named Field Access**: Read/write specific fields by name
- **Custom Commands**: Execute any UniQuery command

#### 3. Configuration System
Priority-based configuration loading:
1. **INI Configuration Files** (highest priority)
   - Define multiple connections in one place
   - Control auto-connect behavior
   - Set server-wide settings (max connections, logging)

2. **Environment Variables** (fallback)
   - Simple single-connection setup
   - No config file needed

3. **Manual Tools** (on-demand)
   - Add connections dynamically via tools

#### 4. Connection Caching & Pooling
- Connections persist across multiple tool calls
- No reconnection overhead
- Configurable maximum connection limit
- Named connections for multiple accounts
- Connection health tracking

### Enhanced Features

- 🔒 **Security**: Credential management, resource protection
- ⚡ **Performance**: Connection pooling, auto-reconnection
- 📊 **Monitoring**: Configurable logging, connection tracking
- 🔌 **Extensibility**: Modular architecture, easy to extend
- ✅ **Production Ready**: Error handling, cleanup on shutdown

---

## Quick Start

### Prerequisites

```bash
pip install uopy mcp
```

### 5-Minute Setup

#### Option 1: With Claude Desktop (Recommended)

1. **Create `unidata_config.ini`** in project root:
```ini
[server]
max_connections = 10
log_level = INFO
default_connection = default

[connection:default]
host = 192.168.2.232
port = 31438
username = uofast
password = uofast
account = C:\U2\UD83\DEMO
service = udcs
auto_connect = true
```

2. **Configure Claude Desktop** (`%APPDATA%\Claude\claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "unidata": {
      "command": "python",
      "args": ["c:\\U2\\AIProjects\\UOFast-NewMCP\\main.py"]
    }
  }
}
```

3. **Restart Claude Desktop**

4. **Start chatting**:
```
List all files in my Unidata account
Query the CUSTOMERS file and show me 10 sample records
```

#### Option 2: With Environment Variables

Configure Claude Desktop with connection details:
```json
{
  "mcpServers": {
    "unidata": {
      "command": "python",
      "args": ["c:\\U2\\AIProjects\\UOFast-NewMCP\\main.py"],
      "env": {
        "UNIDATA_HOST": "192.168.2.232",
        "UNIDATA_PORT": "31438",
        "UNIDATA_USERNAME": "uofast",
        "UNIDATA_PASSWORD": "uofast",
        "UNIDATA_ACCOUNT": "C:\\U2\\UD83\\DEMO",
        "UNIDATA_SERVICE": "udcs"
      }
    }
  }
}
```

---

## Installation

### Standard Installation

```bash
# Clone or download the repository
cd UOFast-NewMCP

# Install dependencies
pip install -r requirements.txt
```

### Development Installation

```bash
# Install in editable mode
pip install -e .
```

### From Package (after installation)

```bash
# Use the console command
uofast-mcp
```

---

## Configuration

### INI Configuration File

The server searches for `unidata_config.ini` in this order:
1. Path in `UNIDATA_CONFIG_FILE` environment variable
2. `./unidata_config.ini` (current directory)
3. `<script_dir>/unidata_config.ini` (where server is located)
4. `~/.unidata_config.ini` (user home directory)

#### Complete Configuration Example

```ini
[server]
# Maximum number of concurrent connections (0 = unlimited)
max_connections = 10

# Logging level: DEBUG, INFO, WARNING, ERROR
log_level = INFO

# Default connection name when not specified
default_connection = production

[connection:production]
host = 192.168.2.232
port = 31438
username = uofast
password = uofast
account = C:\U2\UD83\DEMO
service = udcs
# Auto-connect on server startup
auto_connect = true

[connection:test]
host = 192.168.2.233
port = 31438
username = testuser
password = testpass
account = C:\U2\UD83\TEST
service = udcs
auto_connect = false

[connection:development]
host = localhost
port = 31438
username = devuser
password = devpass
account = C:\U2\UD83\DEV
service = udcs
auto_connect = true
```

### Environment Variables

If no INI file is found:
- `UNIDATA_HOST` (required)
- `UNIDATA_PORT` (default: 31438)
- `UNIDATA_USERNAME` (required)
- `UNIDATA_PASSWORD` (required)
- `UNIDATA_ACCOUNT` (required)
- `UNIDATA_SERVICE` (default: udcs)

---

## Available Tools

### Connection Management

#### 1. add_connection
Add a new named connection to the cache.

**Parameters:**
- `name` (string, required): Connection name
- `host` (string, required): Server hostname/IP
- `port` (integer, default: 31438): Server port
- `username` (string, required): Username
- `password` (string, required): Password
- `account` (string, required): Full account path
- `service` (string, default: "udcs"): UniRPC service

#### 2. list_connections
List all active cached connections and their status.

#### 3. close_connection
Close and remove a connection from cache.

**Parameters:**
- `name` (string, default: "default"): Connection to close

### File Operations

#### 4. list_files
List all available files in the account.

#### 5. get_dict_items
Get DICT items for a file, optionally filtered by type.

**Parameters:**
- `file_name` (string, required): File name
- `dict_types` (array, default: ["D", "V"]): Types to filter

#### 6. query_with_dict_fields
Query a file and return data for specific DICT fields.

**Parameters:**
- `file_name` (string, required): File name
- `dict_fields` (array, required): Field names to include
- `criteria` (string, optional): Selection criteria
- `limit` (integer, default: 10): Max records

### Record Operations

#### 7. read_record
Read a specific record by ID.

**Parameters:**
- `file_name` (string, required): File name
- `record_id` (string, required): Record ID

#### 8. select_records
Execute SELECT query and return matching record IDs.

**Parameters:**
- `file_name` (string, required): File name
- `criteria` (string, optional): Selection criteria
- `limit` (integer, default: 100): Max records

#### 9. query_file
Query a file and return full record data.

**Parameters:**
- `file_name` (string, required): File name
- `criteria` (string, optional): Selection criteria
- `limit` (integer, default: 10): Max records

### DICT Operations

#### 10. read_dict_item
Read a specific DICT item from a file's dictionary.

**Parameters:**
- `file_name` (string, required): File name
- `dict_item_name` (string, required): DICT item name

#### 11. write_dict_item / update_dict_item
Write or update a DICT item.

**Parameters:**
- `file_name` (string, required): File name
- `dict_item_name` (string, required): DICT item name
- `data` (array/string, required): DICT item data

**Data Structure:** `[type, field_number, conversion, column_heading, format, association]`

#### 12. delete_dict_item
Delete a DICT item from a file's dictionary.

**Parameters:**
- `file_name` (string, required): File name
- `dict_item_name` (string, required): DICT item name

### Named Field Operations

#### 13. read_record_with_fields
Read specific DICT fields from a record using field names.

**Parameters:**
- `file_name` (string, required): File name
- `record_id` (string, required): Record ID
- `field_names` (array, required): Field names to retrieve

**Returns:** Dictionary mapping field names to values

#### 14. write_record_with_fields
Write specific DICT fields to a record using field names.

**Parameters:**
- `file_name` (string, required): File name
- `record_id` (string, required): Record ID
- `field_data` (object, required): Field name to value mapping

**Benefits:**
- Update only specific fields without affecting others
- Work with field names instead of raw positions
- Cleaner API than raw attribute access

### Command Execution

#### 15. execute_command
Execute a custom UniQuery command.

**Parameters:**
- `command` (string, required): UniQuery command

---

## Usage Examples

### With Claude Desktop

#### Basic Queries
```
List all files in my Unidata account
Query the CLIENTS file and show me 10 sample records
Find all clients where status is ACTIVE
Execute the command: COUNT CLIENTS
```

#### Schema Exploration
```
Show me the fields in the CUSTOMERS file
What DICT items are available for ORDERS?
Read the DICT item CUSTOMER.NAME from CUSTOMERS
```

#### Data Operations
```
Read record 12345 from CLIENTS
Show me NAME, EMAIL, and PHONE fields for customer 12345
Update the EMAIL field for customer 12345 to newemail@example.com
```

#### DICT Management
```
Create a new DICT item NEW.FIELD in CUSTOMERS
Update the CUSTOMER.NAME DICT item definition
Delete the OLD.FIELD DICT item from CUSTOMERS
```

### Multiple Connections
```
Add a connection named "production" to 192.168.1.100
Add a connection named "test" to 192.168.1.200
List all active connections
Query CLIENTS in the production connection
Query CLIENTS in the test connection
Compare data between production and test
```

---

## Project Structure

```
UOFast-NewMCP/
├── src/                          # Source code package
│   └── uofast_mcp/              # Main package
│       ├── __init__.py          # Package initialization
│       ├── server.py            # MCP server implementation
│       ├── core/                # Core modules
│       │   ├── connection_manager.py    # Connection management
│       │   └── uopy_operations.py       # Database operations
│       └── utils/               # Utility modules
│           └── config_loader.py         # Configuration loading
│
├── main.py                      # Main entry point
├── setup.py                     # Package setup
├── pyproject.toml              # Project configuration
├── requirements.txt            # Dependencies
├── unidata_config.ini         # Configuration file
│
├── README.md                   # Project documentation
├── MCP_SERVER_README.md       # This file (consolidated docs)
├── CHANGELOG.md               # Version history
├── FEATURES.md                # Feature documentation
├── PROJECT_STRUCTURE.md       # Structure guide
└── ARCHITECTURE.md            # Architecture overview
```

### Module Descriptions

#### src/uofast_mcp/server.py
- MCP server implementation
- Tool definitions and handlers
- Async server lifecycle management

#### src/uofast_mcp/core/connection_manager.py
- `UnidataConnection`: Individual connection management
- `ConnectionManager`: Connection pooling and caching
- Connection lifecycle and health checks

#### src/uofast_mcp/core/uopy_operations.py
- `UnidataOperations`: All database operations
- File, record, DICT, and command operations
- Clean separation of database logic

#### src/uofast_mcp/utils/config_loader.py
- `ConfigLoader`: Configuration loading and parsing
- Environment variable and INI file support
- Server settings management

---

## Architecture

### System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     MCP Client (Claude)                      │
│                                                              │
│  Uses tools: list_files, query_file, read_record, etc.     │
└──────────────────────┬───────────────────────────────────────┘
                       │ MCP Protocol (stdio)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    server.py (MCP Server)                    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Tool Definitions & Request Routing                   │   │
│  │ - list_tools() - Advertise available tools          │   │
│  │ - call_tool() - Route requests to handlers          │   │
│  └─────────────────────────────────────────────────────┘   │
└───────────┬──────────────────────────────┬──────────────────┘
            │                              │
            │ Uses                         │ Uses
            ▼                              ▼
┌──────────────────────────┐  ┌──────────────────────────────┐
│  ConnectionManager       │  │  UnidataOperations           │
│  (connection_manager.py) │  │  (uopy_operations.py)        │
│                          │  │                              │
│  ┌────────────────────┐ │  │  ┌────────────────────────┐ │
│  │ Connection Pool    │ │  │  │ Database Operations    │ │
│  │ - Cache conns      │ │  │  │ - list_files()         │ │
│  │ - Lifecycle mgmt   │ │  │  │ - read_record()        │ │
│  │ - Health checks    │ │  │  │ - query_file()         │ │
│  └────────────────────┘ │  │  │ - execute_command()    │ │
│                          │  │  │ - DICT operations      │ │
│  Returns: uopy.Session   │  │  │ - Named field access   │ │
└──────────┬───────────────┘  └───────────┬──────────────────┘
           │                              │
           │ Provides Session             │ Uses
           └──────────────────────────────┘
                       │
                       ▼
            ┌──────────────────────┐
            │   uopy Library       │
            │   (U2 Python API)    │
            └──────────┬───────────┘
                       │ UniRPC Protocol
                       ▼
            ┌──────────────────────┐
            │   U2 Unidata Server  │
            │   (Database)         │
            └──────────────────────┘
```

### Data Flow

#### Tool Request Flow
```
MCP Client
  └─> Tool request (e.g., "list_files")
       └─> server.call_tool()
            ├─> ConnectionManager.ensure_connection()
            │    └─> Returns cached uopy.Session
            │
            ├─> UnidataOperations(session)
            │    └─> Creates operations instance
            │
            └─> ops.list_files()
                 └─> uopy.Command("LISTF").run()
                      └─> U2 Server executes
                           └─> Returns file list
                                └─> Formatted response
                                     └─> Sent to MCP Client
```

### Configuration Priority
```
1. INI Config File
   ├─ UNIDATA_CONFIG_FILE env var → specific path
   ├─ ./unidata_config.ini → current directory
   ├─ <script>/unidata_config.ini → script directory
   └─ ~/.unidata_config.ini → home directory

2. Environment Variables
   └─ UNIDATA_HOST, USERNAME, PASSWORD, ACCOUNT, etc.

3. On-Demand via Tools
   └─ add_connection tool
```

---

## Troubleshooting

### Connection Issues
**Problem:** Cannot connect to database

**Solutions:**
- Verify Unidata server is running and accessible
- Check network connectivity and firewall settings
- Ensure credentials in `unidata_config.ini` are correct
- Verify account path exists and is accessible
- Test with: `python -c "import uopy; print(uopy.__version__)"`

### Import Errors
**Problem:** `ModuleNotFoundError: No module named 'uopy'` or `'mcp'`

**Solutions:**
```bash
pip install uopy mcp
# or
pip install -r requirements.txt
```

### Tool Errors
**Problem:** Tools fail with database errors

**Solutions:**
- Check file names match exactly (case-sensitive on some systems)
- Verify UniQuery syntax for SELECT criteria
- Use `execute_command` tool to test queries manually
- Check MCP server logs for detailed errors

### Claude Desktop Connection
**Problem:** Server not appearing in Claude Desktop

**Solutions:**
- Verify JSON syntax in `claude_desktop_config.json`
- Use double backslashes in Windows paths
- Check absolute paths are correct
- Restart Claude Desktop after config changes
- Look for errors in Claude Desktop logs

### Performance Issues
**Problem:** Slow queries or timeouts

**Solutions:**
- Reduce query limits
- Use specific file selection instead of "all files"
- Enable connection caching in config
- Check network latency to database server
- Review Unidata server performance

---

## Development

### Adding New Operations

1. **Add method to `UnidataOperations`** in `core/uopy_operations.py`:
```python
def my_new_operation(self, param1, param2):
    """My new database operation."""
    # Implementation using uopy
    result = uopy.Command("MY COMMAND").run()
    return convert_to_json_serializable(result)
```

2. **Add tool definition** in `server.py` `list_tools()`:
```python
Tool(
    name="my_new_tool",
    description="Description of what it does",
    inputSchema={
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "..."},
            "param2": {"type": "integer", "description": "..."}
        },
        "required": ["param1"]
    }
)
```

3. **Add handler** in `server.py` `call_tool()`:
```python
elif name == "my_new_tool":
    param1 = arguments["param1"]
    param2 = arguments.get("param2", default_value)

    result = ops.my_new_operation(param1, param2)

    return [TextContent(
        type="text",
        text=f"Result: {json.dumps(result, indent=2)}"
    )]
```

4. **Test** with Claude Desktop or MCP Inspector

### Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# With coverage
pytest --cov=uofast_mcp
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new features
5. Ensure all tests pass
6. Submit a pull request

---

## Changelog

### Version 2.0 - Enhanced DICT Operations & Named Fields

#### New Features
- **DICT Operations**: Read, write, update, delete DICT items
- **Named Field Access**: Read/write specific fields by name using `read_named_fields` and `write_named_fields`
- **Enhanced Tools**: 6 new tools for DICT and named field operations

#### Improvements
- Better type conversion for JSON serialization
- Enhanced error handling and logging
- Improved documentation with examples

### Version 1.1 - INI Configuration Support

#### Major Features
- **INI Configuration Files**: Define multiple connections
- **Auto-Connect**: Connections marked with `auto_connect=true`
- **Connection Pooling**: Persistent connections across tool calls
- **Multiple Named Connections**: Support for different accounts simultaneously
- **Max Connections Limit**: Configurable resource management

#### Configuration Priority System
1. INI File (highest priority)
2. Environment Variables (fallback)
3. Manual via Tools (on-demand)

#### New Tools
- `add_connection` - Add named connections
- `list_connections` - Show active connections
- `close_connection` - Close specific connection

#### Enhanced Tools
All query tools now accept optional `connection` parameter

#### Breaking Changes
None - fully backwards compatible

### Version 1.0 - Initial Release
- Basic MCP server for U2 Unidata
- Environment variable configuration
- 7 basic tools for querying
- Connection via uopy library

---

## Security Notes

- Store credentials securely (use INI files with proper permissions)
- Use restricted accounts with appropriate database permissions
- Be cautious with `execute_command` - it can run any UniQuery command
- Consider implementing query limits and timeouts for production
- Keep passwords in `.gitignore`d config files
- Use connection limits to prevent resource exhaustion

---

## License

This is a sample implementation for educational and development purposes.

---

## Support

For issues with:
- **uopy**: See [uopy documentation](https://pypi.org/project/uopy/)
- **MCP**: See [Model Context Protocol docs](https://modelcontextprotocol.io/)
- **U2 Unidata**: Consult Rocket Software documentation

---

## Additional Resources

- **Model Context Protocol**: [https://modelcontextprotocol.io/](https://modelcontextprotocol.io/)
- **Claude Desktop**: [https://claude.ai/](https://claude.ai/)
- **U2 Unidata**: [https://www.rocketsoftware.com/products/rocket-unidata](https://www.rocketsoftware.com/products/rocket-unidata)
- **uopy Library**: [https://pypi.org/project/uopy/](https://pypi.org/project/uopy/)

---

**Built with love for the U2 community** ❤️
