from ez_setup import use_setuptools
use_setuptools()
from setuptools import setup, find_packages

from distutils.core import Extension
from distutils.sysconfig import get_python_lib
import os,sys

nxdir = os.path.join(get_python_lib(plat_specific=1), 'numpy/core/include')

_pcmseqio = Extension('_pcmseqio',
                    include_dirs = [nxdir],
                    sources = ['src/pcmseqio.c','src/pcmio.c']
                    )
_readklu = Extension('_readklu',
                     sources = ['src/readklu.cc'],
                     )

	
setup(name = "mspikes",
      version = "1.1.2",
      packages = find_packages(),
      scripts = ['spike_view','spike_extract','groupevents'],
      
      description = """ Python scripts and modules for processing
      spike data from SABER, a data acquisition program that stores
      data in pcm_seq2 format and writes metadata to a flat 'explog'
      text file.  The spike_extract script is used to read the explog
      file and extract spike times and features from the pcm data,
      exporting to files readable by the Klusters spike-sorting
      software; the groupevents script reads sorted cluster files
      generated by Klusters and outputs toe_lis data. """,

      install_requires = ["numpy>=1.0.3", "scipy>=0.5", "tables>=2.0"],
      
      maintainer = "CD Meliza",
      maintainer_email = "dmeliza@uchicago.edu",
      ext_package = 'mspikes',
      ext_modules = [ _pcmseqio, _readklu ]
      )
