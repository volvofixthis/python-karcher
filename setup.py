try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

setup(
    name="karcher-home",
    packages=["karcher"],
    include_package_data=True,
    version="0.5.2",
    license="MIT",
    description="Kärcher Home Robots client",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Lauris BH",
    author_email="lauris@nix.lv",
    url="https://github.com/lafriks/python-karcher",
    platforms="any",
    install_requires=[
        "click",
        "aiohttp",
        "paho-mqtt>=2.1.0",
        "cryptography",
        "protobuf",
    ],
    entry_points="""
        [console_scripts]
        karcher-home=karcher.cli:safe_cli
    """,
)
