#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-
# Copyright (C) Dan Meliza, 2006-2009 (dmeliza@uchicago.edu)
# Free for use under Creative Commons Attribution-Noncommercial-Share
# Alike 3.0 United States License
# (http://creativecommons.org/licenses/by-nc-sa/3.0/us/)
"""
spike_view - inspect waveforms and statistics of pcm spike data

Usage:

spike_view [-h|-v]: Display help or version information

spike_view -p <pen> -s <site> [--chan=""] [--units=<clufile>] <explog.h5>

     Plots raw waveform data for episodes in a pen/site

     --chan: specify which channels to plot (single number, or comma-delimited
     list)

     --units: specify a Klusters .clu file to annotate the data with spike times
     (only works when a single channel is specified)

spike_view --stats -p <pen> -s <site> [--chan=""] <explog.h5>

     Plots the RMS of each episode as a time series.  Useful for determining when
     episodes are corrupted by movement artefacts, etc.  If you plan to use
     the -t flag in spike_extract, make sure you specify the channels you plan to
     extract from, since RMS can vary considerably across channels.

Note that the explog must be preprocessed prior to using this command;
see spike_extract

C. Daniel Meliza, 2008
"""

import os, sys, getopt
from mspikes import __version__


def sitestats(elog, channels=None, pen=None, site=None):
    """
    Calculates the first and second moments for each entry.
    Returns 2 NxP arrays, where N is the number of episodes
    and P is the number of channels; and a 1xN vector with
    the episode abstimes

    channels - restrict analysis to particular channels
    """
    oldsite = elog.site
    if pen!=None and site!=None:
        elog.site = (pen,site)
    files = elog.getfiles()
    files.sort(order=('abstime','channel'))

    # restrict to specified channels
    if channels!=None:
        ind = nx.asarray([(x in channels) for x in files['channel']])
        if ind.sum()==0:
            raise ValueError, "Channels argument does not specify any valid channels"
        files = files[ind]

    chanid = nx.unique(files['channel'])
    nchan = chanid.size
    chanidx = nx.zeros(chanid.max()+1,dtype='i')    # we know these are integers
    for ind,id in enumerate(chanid): chanidx[id] = ind

    neps = len(files) / nchan

    mu = nx.zeros((neps,nchan))
    rms = nx.zeros((neps,nchan))
    fcache = filecache()
    fcache.handler = _pcmseqio.pcmfile
    for i,file in enumerate(files):
        pfp = fcache[file['filebase']]
        pfp.entry = file['entry']
        stats = signalstats(pfp.read())
        col = chanidx[file['channel']]
        row = i / nchan
        mu[row,col] = stats[0]
        rms[row,col] = stats[1]

    elog.site = oldsite
    return mu, rms, nx.unique(files['abstime'])


### Check options before loading modules, which are pretty heavy
if __name__=="__main__":

    if len(sys.argv)<2:
        print __doc__
        sys.exit(-1)
    opts, args = getopt.getopt(sys.argv[1:], "p:s:hv",
                               ["stats", "chan=","units=","help","version",])
    opts = dict(opts)
    if opts.has_key('-h') or opts.has_key('--help'):
            print __doc__
            sys.exit(-1)
    if opts.has_key('-v') or opts.has_key('--version'):
        print "%s version: %s" % (os.path.basename(sys.argv[0]), __version__)
        sys.exit(0)
###

import numpy as nx
from mspikes import explog, _pcmseqio, klusters
from mspikes.utils import signalstats, filecache
from pylab import figure, setp, connect, show, ioff, draw

# cache handles to files
_fcache = filecache()
_fcache.handler = _pcmseqio.pcmfile


# colors used in labelling spikes
_manycolors = ['b','g','r','#00eeee','m','y',
               'teal',  'maroon', 'olive', 'orange', 'steelblue', 'darkviolet',
               'burlywood','darkgreen','sienna','crimson',
               ]

def colorcycle(ind=None, colors=_manycolors):
    """
    Returns the color cycle, or a color cycle, for manually advancing
    line colors.
    """
    if ind != None:
        return colors[ind % len(colors)]
    else:
        return colors


def plotentry(k, entry, channels=None, eventlist=None, fig=None):
    atime = k.getentrytimes(entry)
    stim = k.getstimulus(atime)['name']
    files = k.getfiles(atime)
    files.sort(order='channel')
    pfp = []
    for f in files:
        fp = _fcache[f['filebase'].tostring()]
        fp.entry = f['entry']
        pfp.append(fp)
    if channels==None:
        channels = files['channel'].tolist()

    nplots = len(channels)
    # clear the figure and create subplots if needed
    if fig==None:
        fig = figure()

    ax = fig.get_axes()

    if len(ax) != nplots:
        fig.clf()
        ax = []
        for i in range(nplots):
            ax.append(fig.add_subplot(nplots,1,i+1))
        fig.subplots_adjust(hspace=0.)

    for i in range(nplots):
        s = pfp[channels[i]].read()
        t = nx.linspace(0,s.shape[0]/k.samplerate,s.shape[0])
        mu,rms = signalstats(s)
        y = (s - mu)/rms

        ax[i].cla()
        ax[i].hold(True)
        ax[i].plot(t,y,'k')
        ax[i].set_ylabel("%d" % channels[i])
        if eventlist!=None:
            plotevents(ax[i], t, y, entry, eventlist)

    # fiddle with the plots a little to make them pretty
    for i in range(len(ax)-1):
        setp(ax[i].get_xticklabels(),visible=False)

    ax[0].set_title('site_%d_%d (%d) %s' % (k.site + (entry,stim)))
    ax[-1].set_xlabel('Time (ms)')
    draw()
    return fig


def plotevents(ax, t, y, entry, eventlist):
    for j in range(len(eventlist)):
        idx = nx.asarray(eventlist[j][entry],dtype='i')
        times = t[idx]
        values = y[idx]
        p = ax.plot(times, values,'o')
        p[0].set_markerfacecolor(colorcycle(j))


def extractevents(unitfile, elog, Fs=1.0):
    # this might fail if the clu file has a funny name
    ffields = unitfile.split('.')
    assert len(ffields) > 2, "The specified cluster file '%s' does not have the right format" % unitfile
    cfile = ".".join(ffields[:-2] + ["clu",ffields[-1]])
    ffile = ".".join(ffields[:-2] + ["fet",ffields[-1]])
    assert os.path.exists(cfile), "The specified cluster file '%s' does not exist" % cfile
    assert os.path.exists(ffile), "The specified feature file '%s' does not exist" % ffile

    atimes = elog.getentrytimes().tolist()
    atimes.sort()
    return klusters._readklu.readclusters(ffile, cfile, atimes, Fs)


####  SCRIPT
if __name__=="__main__":

    assert len(args) == 1, "Error: specify a parsed explog file."
    infile = args[0]
    assert os.path.splitext(infile)[-1], "Error: input file must be an hdf5 file (parsed explog)"

    ### all drawing is offscreen
    ioff()

    ### all other modes require pen and site
    if opts.has_key('-p'):
        pen = int(opts['-p'])
    else:
        print "Error: must specify pen/site"
        sys.exit(-1)
    if opts.has_key('-s'):
        site = int(opts['-s'])
    else:
        print "Error: must specify pen/site"
        sys.exit(-1)

    # open the kluster.site object
    k = explog.explog(infile)
    k.site = (pen,site)

    # process channel argument
    if opts.has_key('--chan'):
        exec "chans = [%s]" % opts['--chan']
    else:
        chans = None

    ### STATS:
    if opts.has_key('--stats'):
        # stats mode computes statistics for the site
        m,rms,t = klusters.sitestats(k, channels=chans)
        if rms.ndim > 1:
            rms = rms.mean(1)
        # plot them
        fig = figure()
        ax = fig.add_subplot(111)
        ax.plot(rms,'o')
        ax.set_xlabel('Entry')
        ax.set_ylabel('RMS')
        show()

    ### INSPECT:
    else:

        if opts.has_key('--units') and (k.nchannels==1 or (chans != None and len(chans)==1)):
            events = extractevents(opts['--units'], k)
        else:
            events = None

        def keypress(event):
            if event.key in ('+', '='):
                keypress.currententry += 1
                plotentry(k, keypress.currententry, channels=chans, eventlist=events, fig=fig)
            elif event.key in ('-', '_'):
                keypress.currententry -= 1
                plotentry(k, keypress.currententry, channels=chans, eventlist=events, fig=fig)

        keypress.currententry = int(opts.get('-e','0'))
        fig = plotentry(k, keypress.currententry, channels=chans, eventlist=events)
        connect('key_press_event',keypress)
        show()


    del(k)