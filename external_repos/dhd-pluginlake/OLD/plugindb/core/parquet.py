import os
import polars as pl
from datetime import datetime
import uuid

def save_parquet_file(file_content: bytes, original_filename: str, directory: str) -> str:
    """
    Saves a Parquet file with a timestamp and UUID prepended to avoid overwriting.
    Returns the new filename.
    """
    # Generate unique filename
    timestamp = int(datetime.now().timestamp())
    unique_id = uuid.uuid4()
    new_filename = f"{timestamp}_{unique_id}_{original_filename}"
    file_path = os.path.join(directory, new_filename)
    
    # Write the file to disk
    with open(file_path, 'wb') as f:
        f.write(file_content)
    
    return new_filename

def list_files_and_folders(directory: str) -> dict:
    """
    Returns a dictionary representing the folder structure starting from 'directory'.
    """
    dir_structure = {}
    for root, dirs, files in os.walk(directory):
        # Build a nested dictionary structure
        path = root.replace(directory, '').strip(os.sep)
        levels = path.split(os.sep) if path else []
        subdir = dir_structure
        for level in levels:
            subdir = subdir.setdefault(level, {})
        subdir['files'] = files
    return dir_structure

def read_parquet_file(file_path: str) -> bytes:
    """
    Reads a Parquet file and returns its content as bytes.
    """
    with open(file_path, 'rb') as f:
        return f.read()