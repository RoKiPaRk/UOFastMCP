"""
Maps each MCP tool name to its required permission key.
Permission keys follow the pattern: unidata.<resource>.<action>
"""

TOOL_PERMISSIONS: dict[str, str] = {
    # Connection management
    "add_connection":             "unidata.connection.manage",
    "list_connections":           "unidata.connection.read",
    "close_connection":           "unidata.connection.manage",

    # File & query operations
    "list_files":                 "unidata.files.read",
    "select_records":             "unidata.record.read",
    "read_record":                "unidata.record.read",
    "query_file":                 "unidata.record.read",
    "execute_command":            "unidata.command.execute",

    # Dictionary (DICT) operations
    "get_dict_items":             "unidata.dict.read",
    "query_with_dict_fields":     "unidata.dict.read",
    "read_dict_item":             "unidata.dict.read",
    "write_dict_item":            "unidata.dict.write",
    "update_dict_item":           "unidata.dict.write",
    "delete_dict_item":           "unidata.dict.delete",

    # Record field operations
    "read_record_with_fields":    "unidata.record.read",
    "write_record_with_fields":   "unidata.record.write",

    # Basic Program (BP) operations
    "read_bp_program":            "unidata.bp.read",
    "write_bp_program":           "unidata.bp.write",
    "compile_bp_program":         "unidata.bp.compile",
}

# All unique permission keys in the system
ALL_PERMISSIONS: set[str] = set(TOOL_PERMISSIONS.values())

# Role → set of permission keys (used for seeding defaults)
DEFAULT_ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": ALL_PERMISSIONS,
    "developer": {
        "unidata.connection.read",
        "unidata.connection.manage",
        "unidata.files.read",
        "unidata.record.read",
        "unidata.record.write",
        "unidata.command.execute",
        "unidata.dict.read",
        "unidata.dict.write",
        "unidata.dict.delete",
        "unidata.bp.read",
        "unidata.bp.write",
        "unidata.bp.compile",
    },
    "analyst": {
        "unidata.connection.read",
        "unidata.files.read",
        "unidata.record.read",
        "unidata.command.execute",
        "unidata.dict.read",
    },
    "readonly": {
        "unidata.connection.read",
        "unidata.files.read",
        "unidata.record.read",
        "unidata.dict.read",
    },
    "service_account": {
        "unidata.connection.read",
        "unidata.files.read",
        "unidata.record.read",
        "unidata.dict.read",
    },
}

# Human-readable descriptions for each permission key
PERMISSION_DESCRIPTIONS: dict[str, tuple[str, str]] = {
    # permission_key: (tool_name, description)
    "unidata.connection.read":    ("list_connections",    "List active database connections"),
    "unidata.connection.manage":  ("add_connection",      "Add or close database connections"),
    "unidata.files.read":         ("list_files",          "List files in the database account"),
    "unidata.record.read":        ("read_record",         "Read records and query files"),
    "unidata.record.write":       ("write_record_with_fields", "Write or update record fields"),
    "unidata.command.execute":    ("execute_command",     "Execute arbitrary UniQuery commands"),
    "unidata.dict.read":          ("read_dict_item",      "Read DICT item definitions"),
    "unidata.dict.write":         ("write_dict_item",     "Create or update DICT items"),
    "unidata.dict.delete":        ("delete_dict_item",    "Delete DICT items"),
    "unidata.bp.read":            ("read_bp_program",     "Read UniBasic source programs"),
    "unidata.bp.write":           ("write_bp_program",    "Write UniBasic source programs"),
    "unidata.bp.compile":         ("compile_bp_program",  "Compile UniBasic programs"),
}
