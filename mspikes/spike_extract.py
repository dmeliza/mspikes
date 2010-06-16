#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-
# Copyright (C) Dan Meliza, 2006-2009 (dmeliza@uchicago.edu)
# Free for use under Creative Commons Attribution-Noncommercial-Share
# Alike 3.0 United States License
# (http://creativecommons.org/licenses/by-nc-sa/3.0/us/)
"""
spike_extract - extracts spike times and features from extracellular data

Usage: spike_extract [OPTIONS] <sitefile.arf>

Options:

 --chan CHANNELS : specify which channels to analyze, multiple channels
                   as a list, i.e. --chan='1,5,7' will extract spikes from channels
                   1,5, and 7.  Channel groups are currently not supported.

 -r/-a THRESHS:    specify dynamic/absolute thresholds for spike
                   extraction.  Either one value for all channels, or
                   a quoted, comma delimited list, like '6.5,6.5,5'

 -t    RMS:        limit analysis to episodes where the total rms is less
                   than RMS.  Specify one value for all channels, or
                   comma-delimited list to specify per channel.

 -i [CHANS]:       invert data from specific channels (all if unspecified)

 -f NFEATS:        how many principal components and their
                   projections to calculate (default 3 per channel).
 -R:               include raw features

 -w WINDOW:        number of points on either side of the spike
                   to analyze (default 20)

 --kkwik:          run KlustaKwik on each group after it's extracted

 Outputs a number of files that can be used with Klusters or KlustaKwik.
   <sitefile>.spk.<g> - the spike file
   <sitefile>.fet.<g> - the feature file
   <sitefile>.clu.<g> - the cluster file (all spikes assigned to one cluster)
   <sitefile>.xml - the control file used by Klusters

 To do simple thresholding, use the following flag:
 --simple:         extract spike times directly to arf file. Ignores -f,-w,
                   and --kkwik flags

"""

# docstring for tetrode grouping
#If recording from tetrodes, grouping can be done with parentheses: e.g. --chan='(1,2,3,4),(5,6,7,8)'

import os
import arf
import extractor, klusters


options = {
    'thresholds' : [4.5],
    'abs_thresh' : False,
    'max_rms' : [None],
    'nfeats' : 3,
    'measurements' : (),
    'window' : 20,
    'channels' : [0],
    'inverted' : (),
    'kkwik': False,
    'simple' : False,
    'resamp' : extractor._spike_resamp,
    }

def simple_extraction(arffile, log=None, **options):
    """
    For each channel, run through all the entries in the arf file,
    extract the spike times based on simple thresholding, and create a
    new channel with the spike times.

    arffile: the file to analyze. opened in append mode, so be careful
             about accessing it before this function terminates
    """
    channels = options.get('channels')
    threshs = options.get('thresholds')
    rmsthreshs = options.get('max_rms')
    with arf.arf(arffile,'a') as arfp:
        for channel,thresh,maxrms in zip(channels,threshs,rmsthreshs):
            attributes = dict(units='ms', datatype=arf.DataTypes.SPIKET,
                               method='threshold', threshold=thresh, window=options['window'],
                               inverted=channel in options['inverted'], resamp=options['resamp'],
                               mspikes_version=extractor.__version__,)
            for entry, times, spikes, Fs in extractor.extract_spikes(arfp, channel, thresh, maxrms, log, **options):
                if times.size > 0:
                    chan_name = entry.get_record(channel)['name'] + '_thresh'
                    entry.add_data((times * 1000. / Fs,), chan_name, replace=True, **attributes)


def klusters_extraction(arffile, log=None, **options):
    """
    For each channel, run through all the entries in the arf
    file. Extract the spike waveforms and compute principal components
    and any other measurements. Creates the files used by
    klusters/klustakwik for spike sorting.

    arffile: the file to analyze
    """
    # commented lines in this function downsample the spike times to
    # the original sampling rate. This fixes an issue with klusters
    # where certain sampling rates cause horrible crashes, but throws
    # away the sub-sampling-interval precision of spike times.
    from numpy import concatenate, column_stack
    channels = options.get('channels')
    threshs = options.get('thresholds')
    rmsthreshs = options.get('max_rms')
    basename = os.path.splitext(arffile)[0]

    kkwik_pool = []
    with klusters.klustersite(basename, **options) as ks:
        with arf.arf(arffile,'r') as arfp:
            tstamp_offset = min(long(x[1:]) for x in arfp._get_catalog().cols.name[:]) * options['resamp']
            #tstamp_offset = min(long(x[1:]) for x in arfp._get_catalog().cols.name[:])
            for channel,thresh,maxrms in zip(channels,threshs,rmsthreshs):
                alltimes = []
                allspikes = []
                for entry, times, spikes, Fs in extractor.extract_spikes(arfp, channel, thresh, maxrms, log, **options):
                    times += long(entry.record['name'][1:])*options['resamp'] - tstamp_offset
                    #times /= options['resamp']
                    #times += long(entry.record['name'][1:]) - tstamp_offset
                    alltimes.append(times)
                    allspikes.append(spikes)
                    lastt = times[-1]
                if sum(x.size for x in alltimes) == 0:
                    if log: log.write("Skipping channel\n")
                else:
                    alltimes = concatenate(alltimes)
                    klusters.check_times(alltimes)
                    if log: log.write("Aligning spikes\n")
                    spikes_aligned = extractor.align_spikes(concatenate(allspikes,axis=0), **options)
                    if log: log.write("Calculating features\n")
                    spike_projections = extractor.projections(spikes_aligned, **options)[0]
                    spike_measurements = extractor.measurements(spikes_aligned, **options)
                    if spike_measurements is not None:
                        spike_features = column_stack((spike_projections, spike_measurements, alltimes))
                    else:
                        spike_features = column_stack((spike_projections, alltimes))
                    ks.addevents(spikes_aligned, spike_features)
                    if log: log.write("Wrote data to klusters group %s.%d\n" % (basename, ks.group+1))
                    if options.get('kkwik',False):
                        if log: log.write("Starting KlustaKwik\n")
                        kkwik_pool.append(ks.run_klustakwik())

                ks.group += 1
        for i,job in enumerate(kkwik_pool):
            if log:
                log.write("Waiting for KlustaKwik job %d to finish..." % i)
                log.flush()
            job.wait()
            if log:
                log.write("done\n")


def channel_options(options):
    """
    Validate channel-related option, making sure any options that are
    defined on a per-channel basis have the appropriate length.
    Modifies options in place.
    """
    channels = options.get('channels')
    thresh = options.get('thresholds')
    maxrms = options.get('max_rms')
    if not all(isinstance(x,int) for x in channels):
        raise ValueError, "Channels must be integers"  # fix this when we support groups

    if len(thresh)==1:
        thresh *= len(channels)
    if len(thresh) != len(channels):
        raise ValueError, "Channels and thresholds not the same length"
    options['thresholds'] = thresh

    if len(maxrms)==1:
        maxrms *= len(channels)
    if len(maxrms) != len(channels):
        raise ValueError, "Channels and RMS thresholds not the same length"
    options['max_rms'] = maxrms

def main():
    import sys, getopt
    try:
        opts, args = getopt.getopt(sys.argv[1:], "c:r:a:t:i:f:Rw:h",
                                   ["chan=","simple","help","kkwik","version"])
    except getopt.GetoptError, e:
        print "Error: %s" % e
        sys.exit(-1)

    for o,a in opts:
        if o in ('-h','--help'):
            print __doc__
            sys.exit(0)
        elif o == '--version':
            print "%s version: %s" % (os.path.basename(sys.argv[0]), extractor.__version__)
            sys.exit(0)
        elif o in ('-c','--chan'):
            #exec "chans = [%s]" % a
            options['channels'] = tuple(int(x) for x in a.split(','))
        elif o in ('-r','-a'):
            options['thresholds'] = tuple(float(x) for x in a.split(','))
            if o == '-a': options['abs_thresh'] = True
        elif o == '-t':
            options['max_rms'] = tuple(float(x) for x in a.split(','))
        elif o == '-i':
            options['inverted'] = tuple(int(x) for x in a.split(','))
        elif o == '-f':
            options['nfeats'] = int(a)
        elif o == '-R':
            options['measurements'] = extractor._default_measurements
        elif o == '-w':
            options['window'] = int(a)
        elif o == '--kkwik':
            options['kkwik'] = True
        elif o == '--simple':
            options['simple'] = True

    if len(args) != 1:
        print "Error: no input file specified"
        sys.exit(-1)

    channel_options(options)
    if options['simple']:
        simple_extraction(args[0], log=sys.stdout, **options)
    else:
        klusters_extraction(args[0], log=sys.stdout, **options)


if __name__=="__main__":
    main()


# Variables:
# End:
