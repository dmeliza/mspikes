#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-
# Copyright (C) Dan Meliza, 2006-2009 (dmeliza@uchicago.edu)
# Free for use under Creative Commons Attribution-Noncommercial-Share
# Alike 3.0 United States License
# (http://creativecommons.org/licenses/by-nc-sa/3.0/us/)
"""
mspike_group - Group clustered event times by stimulus and unit

Usage: mspike_group [OPTIONS] <sitefile.arf>

Specify one or more of the following flags to control output. If neither
is supplied, the data will be processed but with no output.

 -a:                 add event data to the ARF file. In each entry, a channel
                     is created for each unit (named unit_NNN)
 -t:                 create toelis files, organized by stimulus and unit

Options:

 --stimulus STIMS:   specify which stimuli to include in the grouping,
                     as a comma-delimited list of stimulus names. By
                     default all stimuli are processed.

 --units UNITS:      only extract specific units. Unit numbers start
                     with the first unit (1) in the first group and increase
                     numerically through each of the groups.

 --start TIME:       only output events occurring between specified times,
 --stop TIME:        in units of seconds (the same units used in klustakwik)

 -b BASENAME:        use the klusters data organized under BASENAME rather than
                     sitefile. By default this is assumed to be the same as
                     the basename of the ARf file.

 -n UNITNAME:        when adding spikes to the ARF file, use UNITNAME as the
                     base name (default 'unit')

"""
import os, sys, arf
from extractor import __version__, _spike_resamp, _default_samplerate, _dummy_writer

options = {
    'arf_add' : False,
    'toe_make' : False,
    'stimuli' : None,
    'units' : None,
    'start' : None,
    'stop' : None,
    'basename' : None,
    'unitname': 'unit',
    }

def episode_times(arfp):
    """ Get episode times from arf file, adjusted for resampling """
    from numpy import asarray, argsort
    etimes = asarray([long(x[1:])*_spike_resamp for x in arfp.entries])
    sortind = argsort(etimes)
    mintime = min(etimes)
    return etimes[sortind]-mintime, sortind

def count_units(sitename):
    """ Determine how many units are defined for a site """
    from glob import iglob
    from klustio import getclusters
    return tuple(len(getclusters(f)) for f in iglob("%s.clu.*" % sitename))


def sort_events(sitename, episode_times, log=_dummy_writer, units=None):
    """
    Read event times and cluster identity from *.fet.n and *.clu.n
    files and sort them by unit and episode.  The clu file
    contains the cluster assignments, and the fet file contains
    the event times, in units of samples.

    episode_times:  a sorted array of episode times, in the same
                    units as the event times.

    Returns a list of lists. Each element of the list corresponds to a
    unit; only valid units (i.e. excluding clusters 0 and 1 if there
    are higher numbered clusters) are returned.  Each subelement is a list
    of event times in each episode.
    """
    from glob import iglob
    from klustio import sort_unit_episode
    from klusters import klustersite
    current_unit = 1
    allevents = []
    groups = []
    log.write("Units in electrode groups:\n")
    for f in sorted(iglob("%s.clu.*" % sitename)):
        group = int(f.split('.')[-1])
        fname = klustersite._fettemplate % (sitename, group)
        cname = klustersite._clutemplate % (sitename, group)
        events = readclusters(fname, cname, episode_times, 20.0 * _spike_resamp)
        log.write("Group %d: %s\n" % (group, tuple(current_unit + i for i in xrange(len(events)))))
        current_unit += len(events)
        groups.extend((group,) * len(events))
        allevents.extend(events)
    if units:
        valid = xrange(len(groups))
        return [groups[i] for i in units if i in valid], [allevents[i] for i in units if i in valid]
    else:
        return groups, allevents

def group_events(arffile, log=_dummy_writer, **options):
    """
    Sort events by unit and stimulus

    arffile:  the file to analyze
    log:      if specified, output progress to this handle
    arf_add:  if True, add spike times to arf file
    toe_make: if True, generate toe_lis files organized by stimulus
    stimuli:  if not None, restrict toe_make output to stimuli in the list
    units:    if not None, restrict analysis to these units
    start:    if not None, only include episodes with times (in sec) after this
    stop:     if not None, only include episodes with times before this
    basename: specify the basename of the klusters file (default is based
              off arffile name
    unitname: basename for channels in ARF file
    """
    from collections import defaultdict
    from itertools import izip
    from arf.io import toelis
    from klusters import klustxml

    arf_add = options.get('arf_add',False)
    toe_make = options.get('toe_make',False)
    basename = options.get('basename',None) or os.path.splitext(arffile)[0]
    start, stop = options.get('start',None), options.get('stop',None)
    stimuli = options.get('stimuli',None)
    units = options.get('units',None)
    uname = options.get('unitname','unit') + '_%03d'
    
    log.write("* Loading events from %s\n" % basename)
    if len(count_units(basename))==0:
        raise IOError, "No klusters data defined for %s" % basename
    kxml = klustxml(basename + '.xml')
    source_channels = kxml.channels
    skipped_entries = kxml.skipped

    if arf_add:
        attributes = dict(datatype=arf.DataTypes.SPIKET, method='klusters', resamp=_spike_resamp,
                          mspikes_version=__version__,)
        arf_mode = 'a'
    else:
        arf_mode = 'r'

    with arf.arf(arffile,arf_mode) as arfp:
        sr = arfp.get_attributes(key='sampling_rate')
        if sr is None:
            sr = _default_samplerate
            log.write("warning: %s was not generated by arfxplog, assume samplerate %d\n" % \
                      (arffile,sr))
        eptimes,epnums = episode_times(arfp)
        groups, events = sort_events(basename, eptimes, log, units)
        if len(groups)==0:
            log.write("No valid units specified: exiting\n")
            return

        if units is None:
            units = range(len(groups))

        log.write("* Extracting data from units: %s\n" % [u+1 for u in units])
        tls = [defaultdict(toelis.toelis) for u in units]
        tlskipped = [[] for u in units]
        
        log.write("Sorting events: ")
        for i,spikes in enumerate(izip(*events)):
            etime = eptimes[i] * 1. / sr
            entry = arfp[epnums[i]]
            recid = entry.record['recid']
            stim = entry.record['protocol']
            if start and etime < start:
                log.write("S")
            elif stop and etime > stop:
                log.write("S")
            elif stimuli and stim not in stimuli:
                log.write("S")
            else:
                if arf_add:
                    chan_names = tuple(uname % x for x in range(len(spikes)))
                    entry.add_data(spikes, chan_names, replace=True, node_name='klusters_units',
                                   units=('ms',)*len(groups),
                                   source_channels=tuple(source_channels[g-1] for g in groups),
                                   was_skipped=tuple(recid in skipped_entries[g-1] for g in groups),
                                   **attributes)
                if toe_make:
                    # toe spikes are adjusted for stimulus onset
                    stimlist = entry.stimuli.read()
                    stimstart = stimlist[stimlist["name"]==stim]
                    spike_offset = 1000 * stimstart[0]["start"] if stimstart.size > 0 else 0.0
                    for j,elist in enumerate(spikes):
                        if recid in skipped_entries[groups[j]-1]:
                            tlskipped[j].append(recid)
                        else:
                            tls[j][stim].append(elist - spike_offset)
                log.write(".")
            log.flush()
        log.write(" done\n")

    if toe_make:
        log.write("* Saving toe_lis files:\n")
        for j,unit in enumerate(tls):
            unum = units[j] + 1
            tdir = "%s_%d" % (basename, unum)
            if not os.path.exists(tdir):
                os.mkdir(tdir)
            for stim,tl in unit.items():
                name = os.path.join(tdir, "%s_%d_%s.toe_lis" % (basename, unum, stim))
                toelis.toefile(name).write(tl)
            log.write("Unit %s (skip %d): %s\n" % (tdir, len(tlskipped[j]), " ".join(unit.keys())))

def main(argv=None):
    import getopt
    if argv==None: argv = sys.argv
    opts, args = getopt.getopt(argv[1:], "atphb:n:",
                               ["stimulus=","units=","start=","stop=","version","help"])

    for o,a in opts:
        if o in ('-h','--help'):
            print __doc__
            return 0
        elif o == '--version':
            print "%s version: %s" % (os.path.basename(argv[0]), __version__)
            return 0
        elif o == '-a':
            options['arf_add'] = True
        elif o == '-t':
            options['toe_make'] = True
        elif o == '--units':
            options['units'] = list(int(x)-1 for x in a.split(','))
        elif o == '--stimulus':
            options['stimuli'] = list(x.strip() for x in a.split(','))
        elif o == '--start':
            options['start'] = float(a)
        elif o == '--stop':
            options['stop'] = float(a)
        elif o == '-b':
            options['basename'] = a
        elif o == '-n':
            options['unitname'] = a

    if len(args) < 1:
        print "Error: no input file specified"
        return -1

    try:
        group_events(args[0], log=sys.stdout, **options)
        return 0
    except Exception, e:
        sys.stdout.write("Error: %s\n" % e)
        return -1

if __name__=="__main__":
    sys.exit(main())

# Variables:
# End:
