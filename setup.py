"""Setup script for Minder."""

from setuptools import setup, find_packages

setup(
    name="minder",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "pydantic>=2.5.0",
        "rich>=13.7.0",
        "prompt-toolkit>=3.0.43",
        "httpx>=0.26.0",
        "gitpython>=3.1.40",
        "python-dotenv>=1.0.0",
        "tiktoken>=0.5.2",
    ],
    entry_points={
        "console_scripts": [
            "minder=minder.cli:main",
        ],
    },
    python_requires=">=3.9",
)
