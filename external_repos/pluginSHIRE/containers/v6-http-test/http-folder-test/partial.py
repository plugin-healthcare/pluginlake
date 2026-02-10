"""
This file contains all partial algorithm functions, that are normally executed
on all nodes for which the algorithm is executed.

The results in a return statement are sent to the vantage6 server (after
encryption if that is enabled). From there, they are sent to the partial task
or directly to the user (if they requested partial results).
"""
from typing import Any, Tuple, Optional
import fsspec
import os
import requests
import time
from webdav4.fsspec import WebdavFileSystem
from vantage6.algorithm.tools.util import info


def get_wd_fs(url, credentials: Optional[Tuple[str, str]] = None):
    """Get a WebdavFileSystem object."""
    return WebdavFileSystem(base_url=url, auth=credentials) 


def listdir(path: str, fs: WebdavFileSystem, detail: Optional[bool] = False):
    """List the files in the given path."""
    files = fs.ls(path, detail=detail)
    return files


def read_file(path: str, fs: WebdavFileSystem) -> str:
    """Read the content of the file in the given path."""
    with fs.open(path, "r") as f:
        return f.read()

def remove_file(path: str, fs: WebdavFileSystem) -> bool:
    """Remove the file in the given path."""
    fs.rm(path)
    return path not in listdir(fs)

def write_file(path: str, content: str, fs: WebdavFileSystem) -> bool:
    """Write the content to the file in the given path."""
    with fs.open(path, "w") as f:
        f.write(content)
    return read_file(path, fs) == content

def http_folders_test(http_folder: str) -> Any:

    info("Testing webdav local file server 🚀")
    try:
        fs = get_wd_fs(url=http_folder)
        info(listdir("/data", fs))

    except Exception as e:
        print("webdav listdir request unsuccesful 😒")
        print(e)

    return listdir("/data", fs)
