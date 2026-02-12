from codecs import open
from os import path

from setuptools import find_packages, setup

# we're using a README.md, if you do not have this in your folder, simply
# replace this with a string.
here = path.abspath(path.dirname(__file__))
with open(path.join(here, "README.md"), encoding="utf-8") as f:
    long_description = f.read()

# Here you specify the meta-data of your package. The `name` argument is
# needed in some other steps.
setup(
    name="http-folder-test",
    version="1.0.0",
    description="container to test read write from local files through local http server",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=["vantage6-algorithm-tools", "pandas", "aiohttp", "requests", "fsspec", "webdav4"],
)
