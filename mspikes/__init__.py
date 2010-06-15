#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-
"""
mspikes extracts spike times and waveforms from extracellular data
stored in ARF files.  The main entry points are in spike_extract,
which does the thresholding, realignment, and PCA calculations, and in
group_events, which generates toe_lis files with trials grouped by
unit and stimulus.

Component modules
===============================
extractor - functions for detecting and processing spike events
klusters -  read and write klusters/klustakwik file formats


"""

__version__ = "2.0a1"
__all__ = ['extractor','klusters']
