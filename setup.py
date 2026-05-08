"""Setup configuration for agent-swarm-task-delegation package."""

from setuptools import setup, find_packages

setup(
    name="agent-swarm-task-delegation",
    version="0.1.0",
    description="Intelligent Agent Swarm for Task Delegation",
    author="Mani",
    author_email="myfamily9006@gmail.com",
    packages=find_packages(include=["src", "src.*"]),
    python_requires=">=3.10",
    install_requires=[
        "click>=8.1.0",
        "rich>=13.0.0",
        "pydantic>=2.0.0",
        "structlog>=23.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.1.0",
            "black>=23.0.0",
            "mypy>=1.5.0",
            "flake8>=6.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "agent-swarm=src.cli:main",
        ],
    },
)
