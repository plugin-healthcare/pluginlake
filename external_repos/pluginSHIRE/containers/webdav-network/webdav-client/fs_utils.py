"""Utility functions for the WebdavFileSystem using fsspec."""

import os

from webdav4.fsspec import WebdavFileSystem


def get_wd_fs(url, credentials: tuple[str, str] | None = None):
    """Get a WebdavFileSystem object."""
    return WebdavFileSystem(base_url=url, auth=credentials)


def listdir(path: str, fs: WebdavFileSystem, detail: bool | None = False):
    """List the files in the given path."""
    files = fs.ls(path, detail=detail)
    return files


def read_file(path: str, fs: WebdavFileSystem) -> str:
    """Read the content of the file in the given path."""
    with fs.open(path, "r") as f:
        return f.read()


def remove_file(path: str, fs: WebdavFileSystem) -> bool:
    """Remove the file in the given path."""
    print(fs.ls(os.path.dirname(path), detail=False))
    if path.lstrip("/") in fs.ls(os.path.dirname(path), detail=False):
        fs.rm(path)
        return path.lstrip("/") not in fs.ls(os.path.dirname(path), detail=False)
    print(f"File {path} not found, cannot remove.")
    return False


def write_file(path: str, content: str, fs: WebdavFileSystem) -> bool:
    """Write the content to the file in the given path."""
    with fs.open(path, "w") as f:
        f.write(content)
    return read_file(path, fs) == content
