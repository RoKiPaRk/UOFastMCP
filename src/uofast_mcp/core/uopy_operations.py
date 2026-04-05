"""
U2 Unidata Operations Module
=============================

This module contains all the uopy database operations used by the MCP server.
It provides a clean separation of database logic from server logic.
"""

import json
import logging
from typing import Dict, List, Optional, Any

import uopy

logger = logging.getLogger("uofast-mcp.operations")


def convert_to_json_serializable(data: Any) -> Any:
    """
    Convert uopy data types (including DynArray) to JSON-serializable formats.

    Args:
        data: Data to convert (can be DynArray, list, dict, or primitive)

    Returns:
        JSON-serializable version of the data
    """
    # Check if it's a DynArray
    if hasattr(data, '__class__') and 'DynArray' in data.__class__.__name__:
        # Convert DynArray to list
        try:
            # DynArray can be converted to list
            return list(data)
        except:
            # If conversion fails, try to extract as string
            try:
                return str(data)
            except:
                return None

    # If it's a list, recursively convert each item
    elif isinstance(data, list):
        return [convert_to_json_serializable(item) for item in data]

    # If it's a dict, recursively convert each value
    elif isinstance(data, dict):
        return {key: convert_to_json_serializable(value) for key, value in data.items()}

    # If it's already a primitive type, return as-is
    elif isinstance(data, (str, int, float, bool, type(None))):
        return data

    # For any other type, try to convert to string
    else:
        try:
            return str(data)
        except:
            return None


class UnidataOperations:
    """Handles all Unidata database operations using uopy."""

    def __init__(self, session: uopy.Session):
        """
        Initialize UnidataOperations with a session.

        Args:
            session: Active uopy Session object
        """
        self.session = session

    def list_files(self) -> str:
        """
        Execute LISTF command to get available files.

        Returns:
            String output from LIST.FILES command
        """
        logger.debug("Executing LISTF command")
        cmd = uopy.Command("LISTF", session=self.session)
        cmd.run()
        #output = cmd.response
        if cmd.status == uopy.EXEC_COMPLETE or cmd.status == uopy.EXEC_WARNING: # type: ignore
            output = cmd.response
        else:
            logger.error(f"LISTF command failed with status {cmd.status}: {cmd.response}")
            output = "" 
        return output

    def select_records(
        self,
        file_name: str,
        criteria: str = "",
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Execute a SELECT command and return matching record IDs.

        Args:
            file_name: Name of the file to select from
            criteria: Optional selection criteria
            limit: Maximum number of records to return

        Returns:
            Dictionary with command, count, and record_ids
        """
        # Build SELECT command
        if criteria:
            select_cmd = f"SELECT {file_name} WITH {criteria} SAMPLE {limit}"
        else:
            select_cmd = f"SELECT {file_name} SAMPLE {limit}"
        print(f"Select Command: {select_cmd}")
        logger.debug(f"Executing: {select_cmd}")

        # Execute SELECT
        uopy.Command(select_cmd, session=self.session).run()

        # Get selected record IDs
        select_list = uopy.List(0, session=self.session).read_list()
        print("Selected Records:", len(select_list))
        dict_records = []
        # Open DICT file and read records        
        with uopy.File(file_name,dict_flag=1, session=self.session) as file_obj:
            for dict_id in select_list:
                record = file_obj.read(dict_id)
                dict_records.append(record)
                 
        result = convert_to_json_serializable(dict_records)
    
        return result

    def read_record(self, file_name: str, record_id: str) -> Any:
        """
        Read a specific record from a file.

        Args:
            file_name: Name of the file to read from
            record_id: ID of the record to read

        Returns:
            Record data (JSON-serializable)
        """
        logger.debug(f"Reading record {record_id} from {file_name}")

        # Open file and read record
        file_obj = uopy.File(file_name, session=self.session)
        try:
            record = file_obj.read(record_id)
            # Convert DynArray and other uopy types to JSON-serializable format
            return convert_to_json_serializable(record)
        finally:
            file_obj.close()

    def execute_command(self, command: str) -> str:
        """
        Execute a custom UniQuery command.

        Args:
            command: The UniQuery command to execute

        Returns:
            Command output
        """
        logger.debug(f"Executing command: {command}")
        output=''
        cmd = uopy.Command(command, session=self.session)
        cmd.run()
        if cmd.status == uopy.EXEC_COMPLETE or cmd.status == uopy.EXEC_WARNING:
           output = cmd.response
        else:
            logger.error(f"Command execution failed with status {cmd.status}: {cmd.response}")
        return output

    def query_file(
        self,
        file_name: str,
        criteria: str = "",
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Query a file with SELECT criteria and return actual record data.

        Args:
            file_name: Name of the file to query
            criteria: Optional selection criteria
            limit: Maximum number of records to return

        Returns:
            List of dictionaries with id and data for each record (JSON-serializable)
        """
        # Build SELECT command
        if criteria:
            select_cmd = f"SELECT {file_name} {criteria} SAMPLE {limit}"
        else:
            select_cmd = f"SELECT {file_name} SAMPLE {limit}"

        logger.debug(f"Executing query: {select_cmd}")

        # Execute SELECT
        uopy.Command(select_cmd, session=self.session).run()

        # Get selected record IDs
        select_list = uopy.List(0, session=self.session).read_list()

        if not select_list:
            return []

        # Open file
        file_obj = uopy.File(file_name, session=self.session)

        # Read records
        records = []
        try:
            for record_id in select_list[:limit]:
                record_data = file_obj.read(record_id)
                # Convert DynArray and other uopy types to JSON-serializable format
                records.append({
                    "id": record_id,
                    "data": convert_to_json_serializable(record_data)
                })
        finally:
            file_obj.close()

        return records

    def write_record(self, file_name: str, record_id: str, data: Any) -> bool:
        """
        Write a record to a file.

        Args:
            file_name: Name of the file to write to
            record_id: ID of the record to write
            data: Data to write

        Returns:
            True if successful
        """
        logger.debug(f"Writing record {record_id} to {file_name}")

        file_obj = uopy.File(file_name, session=self.session)
        try:
            file_obj.write(record_id, data)
            return True
        finally:
            file_obj.close()

    def delete_record(self, file_name: str, record_id: str) -> bool:
        """
        Delete a record from a file.

        Args:
            file_name: Name of the file
            record_id: ID of the record to delete

        Returns:
            True if successful
        """
        logger.debug(f"Deleting record {record_id} from {file_name}")

        file_obj = uopy.File(file_name, session=self.session)
        try:
            file_obj.delete(record_id)
            return True
        finally:
            file_obj.close()

    def get_dict_items(
        self,
        file_name: str,
        dict_types: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Get DICT items for a file, filtering by type if specified.

        Args:
            file_name: Name of the file to get DICT items for
            dict_types: List of DICT types to filter (e.g., ["D", "V"])
                       If None, gets all DICT items

        Returns:
            Dictionary with command, count, and dict_items list
        """
        # Build SELECT command for DICT
        if dict_types:
            # Create OR condition for multiple types
            type_conditions = " OR ".join([f'TYPE EQ "{dt}"' for dt in dict_types])
            select_cmd = f"SELECT DICT {file_name} WITH {type_conditions}"
        else:
            select_cmd = f"SELECT DICT {file_name} WITH TYPE = \"V\"\"D\""

        logger.debug(f"Executing: {select_cmd}")

        # Execute SELECT
        uopy.Command(select_cmd, session=self.session).run()

        # Get selected DICT item IDs
        select_list = uopy.List(0, session=self.session).read_list()

        result = {
            "command": select_cmd,
            "count": len(select_list) if select_list else 0,
            "dict_items": select_list if select_list else []
        }

        logger.info(f"Found {result['count']} DICT items for {file_name}")
        return convert_to_json_serializable(result)

    def query_with_dict_fields(
        self,
        file_name: str,
        dict_fields: List[str],
        criteria: str = "",
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Query a file and return data with specific DICT fields.

        Args:
            file_name: Name of the file to query
            dict_fields: List of DICT field names to include in output
            criteria: Optional selection criteria
            limit: Maximum number of records to return

        Returns:
            List of dictionaries with id and field data for each record (JSON-serializable)
        """
        # Build SELECT command
        if criteria:
            select_cmd = f"SELECT {file_name} WITH {criteria} SAMPLE {limit}"
        else:
            select_cmd = f"SELECT {file_name} SAMPLE {limit}"

        logger.debug(f"Executing query: {select_cmd}")

        # Execute SELECT
        uopy.Command(select_cmd, session=self.session).run()

        # Get selected record IDs
        select_list = uopy.List(0, session=self.session).read_list()

        if not select_list:
            return []

        # Build LIST command with specific fields
        field_list = " ".join(dict_fields)
        list_cmd = f"LIST {file_name} {field_list}"

        logger.debug(f"Building field list with: {field_list}")

        # Open file to read records
        file_obj = uopy.File(file_name, session=self.session)

        # Read records with field extraction
        records = []
        try:
            for record_id in select_list[:limit]:
                record_data = file_obj.read_named_fields(record_id, dict_fields)

                # Convert record_data to JSON-serializable format first
                record_data = convert_to_json_serializable(record_data)

                records.append(record_data)
        finally:
            file_obj.close()

        return {"select_cmd": select_cmd, "records": records}

    def read_dict_item(self, file_name: str, dict_item_name: str) -> Any:
        """
        Read a specific DICT item from a file's dictionary.

        Args:
            file_name: Name of the file whose DICT to read from
            dict_item_name: Name of the DICT item to read

        Returns:
            DICT item data (JSON-serializable)
        """
        logger.debug(f"Reading DICT item {dict_item_name} from {file_name}")

        # Open DICT file (dict_flag=1)
        file_obj = uopy.File(file_name, dict_flag=1, session=self.session)
        try:
            record = file_obj.read(dict_item_name)
            # Convert DynArray and other uopy types to JSON-serializable format
            return convert_to_json_serializable(record)
        finally:
            file_obj.close()

    def write_dict_item(self, file_name: str, dict_item_name: str, data: Any) -> bool:
        """
        Write or update a DICT item in a file's dictionary.

        Args:
            file_name: Name of the file whose DICT to write to
            dict_item_name: Name of the DICT item to write/update
            data: Data to write (can be a list of attribute values)

        Returns:
            True if successful
        """
        logger.debug(f"Writing DICT item {dict_item_name} to {file_name}")

        # Open DICT file (dict_flag=1)
        file_obj = uopy.File(file_name, dict_flag=1, session=self.session)
        try:
            file_obj.write(dict_item_name, data)
            return True
        finally:
            file_obj.close()

    def delete_dict_item(self, file_name: str, dict_item_name: str) -> bool:
        """
        Delete a DICT item from a file's dictionary.

        Args:
            file_name: Name of the file whose DICT to delete from
            dict_item_name: Name of the DICT item to delete

        Returns:
            True if successful
        """
        logger.debug(f"Deleting DICT item {dict_item_name} from {file_name}")

        # Open DICT file (dict_flag=1)
        file_obj = uopy.File(file_name, dict_flag=1, session=self.session)
        try:
            file_obj.delete(dict_item_name)
            return True
        finally:
            file_obj.close()

    def read_record_with_named_fields(
        self,
        file_name: str,
        record_id: str,
        field_names: List[str]
    ) -> Dict[str, Any]:
        """
        Read specific DICT fields from a record using field names.

        Args:
            file_name: Name of the file to read from
            record_id: ID of the record to read
            field_names: List of DICT field names to retrieve

        Returns:
            Dictionary mapping field names to their values (JSON-serializable)
        """
        logger.debug(f"Reading record {record_id} from {file_name} with fields: {field_names}")

        file_obj = uopy.File(file_name, session=self.session)
        try:
            # read_named_fields returns a dictionary with field names as keys
            
            '''
            Docstring for read_record_with_named_fields
            
            :param self: Description
            :param file_name: Description
            :type file_name: str
            :param record_id: Description
            :type record_id: str
            :param field_names: Description
            :type field_names: List[str]
            :return: Description
            :rtype: Dict[str, Any]

            Examples:
            >>> with File("RENTAL_DETAILS") as test_file:
            >>>     field_list = ["FULL_NAME", "ACTUAL_RETURN_DATE", "BALANCE_DUE"]
            >>>     id_list = ['1084', '1307', '1976']
            >>>     read_rs = test_file.read_named_fields(id_list, field_list)
            >>>     for l in read_rs:
            >>>         print(l)
            ['0', '0', '0']
            ['0', '0', '0']
            ['1084', '1307', '1976']
            [['Karen McGlone', ['03/29/2010', '03/30/2010', '03/31/2010', '03/30/2010'], '3.50'],
            ['Jamie Klink', ['05/05/2010', '05/07/2010', '05/05/2010', '05/07/2010', '05/05/2010'], '4.82'],
            ['Mo Evans', ['08/23/2010', '08/20/2010', '08/26/2010', '08/22/2010', '08/25/2010', '08/22/2010'], '19.04']]
            
            '''

            
            record_data = file_obj.read_named_fields(record_id, field_names)
            # Convert DynArray and other uopy types to JSON-serializable format
            
            
            return convert_to_json_serializable(record_data)
        finally:
            file_obj.close()
        

    def write_record_with_named_fields(
        self,
        file_name: str,
        record_id: str,
        field_data: Dict[str, Any]
    ) -> bool:
        """
        Write specific DICT fields to a record using field names.

        Args:
            file_name: Name of the file to write to
            record_id: ID of the record to write
            field_data: Dictionary mapping field names to their values

        Returns:
            True if successful
        """
        logger.debug(f"Writing record {record_id} to {file_name} with fields: {list(field_data.keys())}")

        file_obj = uopy.File(file_name, session=self.session)
        try:
            # write_named_fields takes a dictionary with field names as keys
            file_obj.write_named_fields(record_id, field_data)
            return True
        finally:
            file_obj.close()

    def read_bp_program(self, bp_file: str, program_name: str) -> str:
        """
        Read source code from a BP file using SequentialFile.

        Args:
            bp_file: Name of the BP directory file (e.g., 'BP', 'BP.UTILS')
            program_name: Name of the program to read

        Returns:
            The program source code as a string
        """
        logger.debug(f"Reading BP program {program_name} from {bp_file}")

        with uopy.SequentialFile(bp_file, program_name, create_flag=False, session=self.session) as seq_file:
            lines = []
            while True:
                line = seq_file.read_line()
                if seq_file.status == 1:  # EOF reached
                    break
                lines.append(line)
            return "\n".join(lines)

    def write_bp_program(self, bp_file: str, program_name: str, source_code: str) -> bool:
        """
        Write source code to a BP file using SequentialFile.

        Args:
            bp_file: Name of the BP directory file (e.g., 'BP', 'BP.UTILS')
            program_name: Name of the program to write
            source_code: The UniBasic source code to write

        Returns:
            True if successful
        """
        logger.debug(f"Writing BP program {program_name} to {bp_file}")

        with uopy.SequentialFile(bp_file, program_name, create_flag=True, session=self.session) as seq_file:
            for line in source_code.split("\n"):
                seq_file.write_line(line)
            seq_file.write_eof()
        return True

    def compile_bp_program(self, bp_file: str, program_name: str) -> Dict[str, Any]:
        """
        Compile a BP program using the BASIC command.

        Args:
            bp_file: Name of the BP directory file (e.g., 'BP', 'BP.UTILS')
            program_name: Name of the program to compile

        Returns:
            Dictionary with command, status, and response
        """
        logger.debug(f"Compiling BP program {program_name} from {bp_file}")

        command = f"BASIC {bp_file} {program_name}"
        cmd = uopy.Command(command, session=self.session)
        cmd.run()

        return {
            "command": command,
            "status": "success" if cmd.status == uopy.EXEC_COMPLETE or cmd.status == uopy.EXEC_WARNING else "error",
            "response": cmd.response
        }
