#!/usr/bin/env python3

from setuptools import setup


with open("README.md", "r") as f:
    readme = f.read()

setup(
    name="checkcorruptedimages",
    packages=["checkcorruptedimages"],
    version="0.1",
    license="GPL3",
    description="Python3 module to check for corrupted images using "
            '"identify" from ImageMagick as underlying mechanism.',
    long_description=readme,
    long_description_content_type="text/markdown",
    author="Carlos A. Planchón",
    author_email="bubbledoloresuruguay2@gmail.com",
    url="https://github.com/carlosplanchon/checkcorruptedimages",
    download_url="https://github.com/carlosplanchon/"
        "checkcorruptedimages/archive/v0.1.tar.gz",
    keywords=["check", "corrupted", "images"],
    classifiers=[
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Build Tools",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.4",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
    ],
)
