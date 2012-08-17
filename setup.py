from distribute_setup import use_setuptools
use_setuptools()
from setuptools import setup, find_packages

from numpy.distutils.core import setup,Extension
import os

VERSION = '2.2.1b1'
cls_txt = \
"""
Development Status :: 5 - Production/Stable
Intended Audience :: Science/Research
License :: Creative Commons Attribution 3.0
Programming Language :: Python
Topic :: Scientific/Engineering
Operating System :: Unix
Operating System :: POSIX :: Linux
Operating System :: MacOS :: MacOS X
Natural Language :: English
"""
short_desc = "Extracellular spike extraction and feature calculation"
long_desc = \
"""
Python scripts and modules for processing spike data from SABER, a
data acquisition program that stores data in pcm_seq2 format and
writes metadata to a flat 'explog' text file.  The spike_extract
script is used to read the explog file and extract spike times and
features from the pcm data, exporting to files readable by the
Klusters spike-sorting software; the groupevents script reads sorted
cluster files generated by Klusters and outputs toe_lis data.
"""

_readklu = Extension('klustio', sources = ['src/klustio.cc'] )
_spikes = Extension('spikes', sources = ['src/spikes.pyf','src/spikes.c'])

setup(name = "mspikes",
      version = VERSION,
      description = short_desc,
      long_description = long_desc,
      classifiers = [x for x in cls_txt.split("\n") if x],
      author = 'C Daniel Meliza',
      author_email = '"dan" at the domain "meliza.org"',
      maintainer = 'C Daniel Meliza',
      maintainer_email = '"dan" at the domain "meliza.org"',
      packages = find_packages(),
      entry_points = {'console_scripts': ['mspike_extract = mspikes.mspike_extract:main',
                                          'mspike_group = mspikes.mspike_group:main',
                                          'mspike_view = mspikes.mspike_view:main',
                                          'mspike_shape = mspikes.mspike_shape:main',
                                          'mspike_merge = mspikes.mspike_merge:main']},


      install_requires = ["numpy>=1.3", "scipy>=0.7", "arf>=1.1.0"],

      ext_package = 'mspikes',
      ext_modules = [ _readklu, _spikes ]
      )
