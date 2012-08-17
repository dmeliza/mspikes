#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) Dan Meliza, 2006-2012 (dmeliza@uchicago.edu)
# Free for use under Creative Commons Attribution-Noncommercial-Share
# Alike 3.0 United States License
# (http://creativecommons.org/licenses/by-nc-sa/3.0/us/)
"""
mspike_spikeshapes: get mean spike shapes for all units at a site.

Usage: mspike_spikeshapes [OPTIONS] <sitefile.arf>

Options:

-w:       window size (in samples; default 30)
-r:       resample spikes after extraction (default 3x)
-u UNITS: restrict to specific units (by name, comma delimited)

Uses spike time data stored in the ARF file (i.e. generated by
mspike_extract --simple or mspike_group -a).  Iterates through the
entries in <sitefile.arf> and extracts the spike waveforms associated
with the units in each entry.  Specific units can be extracted using
the -u flag.  The waveforms are extracted from the first channel
associated with a spike.

Output (to stdout): mean spikes in long tabular format, with columns unit, time,
and value
"""
import os, sys, arf
from arf.constants import DataTypes
from .extractor import _dummy_writer
from .version import version

options = {
    'window_start' : 0.5,
    'window_stop' : 1.5,
    'units' : None,
    'resamp' : 3
    }

def extract_spikes(arffile, log=_dummy_writer, **options):
    """
    For each unit defined in a site, extract the spike waveforms from
    the first channel associated with that unit.

    window:   size of the window to extract
    units:    restrict to specific units (by name)

    Returns dict of numpy arrays (nevents x nsamples), indexed by unit name,
            dict of sampling rates, indexed by unit name
    """
    from collections import defaultdict
    from .spikes import extract_spikes
    from .extractor import resample_and_align
    from numpy import row_stack
    units = options.get('units',None)
    resamp = options.get('resamp',3)
    window_start = options.get('window_start',0.5)
    window_stop = options.get('window_stop',1.5)

    out = defaultdict(list)
    src_chans = dict()
    Fs = dict()
    log.write('* Extracting spike waveforms from %s: ' % arffile)
    with arf.file(arffile,'r') as arfp:
        for entryname in arfp:
            entry = arfp[entryname]
            for channame in entry:
                if units is not None and channame not in units: continue
                chan = entry[channame]
                if chan.attrs['datatype'] != DataTypes.SPIKET: continue
                src_chans[channame] = chan.attrs['source_channels'][0]
                src_chan = entry[src_chans[channame]]
                data = src_chan[:]
                # this will produce some undefined results if sampling rate changes
                Fs[channame] = src_chan.attrs['sampling_rate'] / 1000
                if entry[channame].shape[0] != 0:
                    spiket = (entry[channame][:] * Fs[channame]).astype('i')
                    spikes = extract_spikes(data, spiket, window_start * Fs[channame], window_stop * Fs[channame])
                    out[channame].append(spikes)
            log.write('.')
            log.flush()
    log.write(' done\n')
    log.write('* Resampling and aligning spikes:\n')
    for k in sorted(out.keys()):
        v = out[k]
        spikes = row_stack(v)
        log.write('** %s -> %s: %d spikes @ %.1f kHz' % (src_chans[k], k, spikes.shape[0], Fs[k]))
        log.flush()
        out[k] = resample_and_align(spikes, window_start * Fs[k], resamp)[0]
        Fs[k] *= resamp
        log.write(' -> %.1f kHz\n' % Fs[k])
    return out, Fs

def write_spikes(sitename, spikes, **options):
    from numpy import linspace
    from itertools import izip
    fname = os.path.splitext(sitename)[0] + '.spikes'

    with open(fname,'wt') as fp:
        fp.write("# program: mspikes_shape\n")
        fp.write("# version: %s\n" % version)
        fp.write("# site file: %s\n" % sitename)
        fp.write("# window start: %.1f\n" % options['window_start'])
        fp.write("# window stop: %.1f\n" % options['window_stop'])
        fp.write("# resampling factor: %d\n" % options['resamp'])
        fp.write("# number of units: %d\n" % len(spikes))
        fp.write("unit\ttime\tvalue\n")
        for unit,spike in spikes.items():
            mspike = spike.mean(0)
            time = linspace(-options['window_start'], options['window_stop'], mspike.size)
            for t,v in izip(time,mspike):
                fp.write("%s\t%.2f\t%.5g\n" % (unit, t, v))


def main(argv=None):
    import getopt
    if argv==None: argv = sys.argv
    print "* Program: %s" % os.path.split(argv[0])[-1]
    print "* Version: %s" % version

    opts, args = getopt.getopt(argv[1:], "b:e:r:u:hv",
                               ["help","version"])
    try:
        for o,a in opts:
            if o in ('-h','--help'):
                print __doc__
                return 0
            elif o in ('-v','--version'):
                return 0
            elif o == '-b':
                options['window_start'] = float(a)
            elif o == '-e':
                options['window_stop'] = float(a)
            elif o == '-r':
                options['resamp'] = int(a)
            elif o == '-u':
                options['units'] = a.split(',')
    except ValueError, e:
        print "* Error: can't parse %s option (%s): %s" % (o,a,e)
        return -1

    if len(args) < 1:
        print "* Error: no input file specified"
        return -1

    spikes,Fs = extract_spikes(args[0], log=sys.stdout, **options)
    write_spikes(args[0], spikes, **options)


if __name__=="__main__":
    sys.exit(main())

# Variables:
# End:

