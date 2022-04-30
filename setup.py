#!/usr/bin/env python3

from pathlib import Path

from setuptools import setup

readme = Path("README.md").read_text()

setup(
    name="checkcorruptedimages",
    packages=["checkcorruptedimages"],
    version="0.3",
    license="MIT",
    description="Python3 module to check for corrupted images using "
            '"identify" from ImageMagick as underlying mechanism.',
    long_description=readme,
    long_description_content_type="text/markdown",
    author="Carlos A. Planchón",
    author_email="bubbledoloresuruguay2@gmail.com",
    url="https://github.com/carlosplanchon/checkcorruptedimages",
    download_url="https://github.com/carlosplanchon/"
        "checkcorruptedimages/archive/v0.3.tar.gz",
    keywords=["check", "corrupted", "images"],
    classifiers=[
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Build Tools",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.10",
    ],
)
