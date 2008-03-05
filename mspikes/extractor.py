#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-
"""
extracts spikes from a series of associated pcm_seq2 files
"""

import numpy as nx
import _pcmseqio
from utils import cov, pcasvd
from scipy import weave


_dtype = nx.int16

def get_nentries(fps):
    """
    Returns the number of entries in the pcmfiles.
    Raises a ValueError if all the pcmfile objects don't have the same # of entries
    """
    nentries = 0
    for f in fps:
        if not nentries:
            nentries = f.nentries
        else:
            if nentries != f.nentries:
                raise ValueError, "All files must have the same number of entries"                

    return nentries

def find_spikes(fp, **kwargs):
    """
    Extracts spike data from raw pcm data.  A spike occurs when
    the signal crosses a threshold.  This threshold can be defined
    in absolute terms, or relative to the RMS of the signal.

    fp - list of pcmfile objects. Needs to support nentries property,
         seek(int), and read()

    Optional arguments:
    rms_thres  = 4.5  - factor by which the signal must exceed the
                        rms of the whole file
    abs_thresh        - absolute threshold spikes must cross. if this is
                        defined, the rms_thresh value is ignored

    refrac            - the closest two events can be (in samples)
    window            - the number of points on each side of the spike peak to be
                        extract

    Returns a tuple of three arrays: (spikes, entries, events)

    If N events are detected, spikes has dimension (window*2 x N),
    entries has dimension (N) and events has dimension (N)
    """
    if kwargs.has_key('abs_thresh'):
        fac = False;
        abs_thresh = kwargs['abs_thresh']
    else:
        fac = True;
        rms_fac = kwargs.get('rms_thresh',4.5)

    nchan = len(fp)

    # some sanity checks
    nentries = get_nentries(fp)
    
    spikes = []
    events = []
    for i in range(1,nentries+1):
        signal = combine_channels(fp, i)
        dcoff = signal.mean(0)
        if not fac:
            thresh = dcoff + abs_thresh
        else:
            rms = nx.sqrt(signal.var(0))
            thresh = dcoff + rms_fac * rms

        ev = thresh_spikes(signal, thresh, **kwargs)
        spikes.append(extract_spikes(signal, ev, **kwargs))
        events.append(ev)

    spikes = nx.concatenate(spikes, axis=0)
    return (spikes, events)


def extract_spikes(S, events, **kwargs):
    """
    Extracts spike waveforms from raw signal data. For each
    offset in <events>, a window of samples around the event
    time is extracted.  Returns a 3D array, (sample, event, channel)

    Optional arguments:
    <window> - specify the (total) size of the spike window (default 30 ms)
    """

    window = kwargs.get('window',30)
    nsamples, nchans = S.shape
    nevents = len(events)
    spikes = nx.zeros((nevents, 2*window, nchans), _dtype)

    for i in range(nevents):
        toe = events[i]
        if toe + window > nsamples or toe - window < 0: continue
        spikes[i,:,:] = S[toe-window:toe+window,:]

    return spikes


def get_projections(spikes, **kwargs):
    """
    Calculates the projections of the spikes onto the features
    Returns a 3D array, (events, dims, chans)

    spikes - 3D array, dimensions (events, values, channels)

    Optional Arguments:
    ndims - the number of principal components to use in calculating projections
            (default 3)    
    peaktrough - if true, include peak and trough calculations as features
    """

    nevents,nsamp,nchans = spikes.shape
    ndims = kwargs.get('ndims',3)

    if kwargs.get('peaktrough',True):
        nfeats = ndims + 3
    else:
        nfeats = ndims
        
    proj = nx.zeros((nevents,nchans,nfeats),'d')

    for i in range(nchans):
        proj[:,i,:ndims] = pcasvd(spikes[:,:,i], ndims)[0]

    if kwargs.get('peaktrough',True):
        # spikes should be aligned
        peak_ind = spikes[0,:,0].argmax()
        proj[:,:,ndims+0] = spikes[:,:,:].max(1)
        proj[:,:,ndims+1] = spikes[:,0:peak_ind,:].min(1)
        proj[:,:,ndims+2] = spikes[:,peak_ind:,:].min(1)

    return proj


def thresh_spikes(S, thresh, **kwargs):
    """
    Analyzes a signal matrix for threshold crossings. Whenever
    any one of the channels crosses its threshold, the peak of
    that signal is detected, and the time of the event is recorded.
    Returns the times of the events.

    <S> - the signal. Can be a vector or, for multiple channels,
          a matrix in which each column is a channel
    <thresh> - the crossing point(s) for the discriminator. Needs
               to be a 
    
    Optional arguments:
    <window> - the number of points to search ahead for the peak (in samples)
    <refrac> - the minimum distance between spikes (in samples)
    """

    window = kwargs.get('window',30)
    refrac = kwargs.get('refrac',window)

    if not isinstance(S, nx.ndarray):
        raise TypeError, "Input must be an ndarray"
    if S.ndim==1:
        S.shape = (S.size,1)
        
    nsamp, nchan = S.shape

    if nx.isscalar(thresh):
        thresh = nx.array([thresh] * nchan)
    elif not isinstance(thresh, nx.ndarray):
        raise TypeError, "Threshold must be a scalar or an array of values"
    elif thresh.ndim > 1 or thresh.size != nchan:
        raise ValueError, "Threshold array length must equal number of channels"

    events = []

    code = """
          #line 193 "extractor.py"
    
          for (int samp = 0; samp < nsamp; samp++) {
               for (int chan = 0; chan < nchan; chan++) {
                    if (S(samp, chan) > thresh(chan)) {
                         int   peak_ind = samp;
                         short peak_val = S(samp,chan);
                         for (int j = samp; j < samp + window; j++) {
                              if (S(j,chan) > peak_val) {
                                  peak_val = S(j,chan);
                                  peak_ind = j;
                              }
                         }
                         if (peak_ind > window && peak_ind + window < nsamp)
                              events.append(peak_ind);
                         samp = peak_ind + refrac - 1;
                         break;
                    }
                }
          }
    """
    weave.inline(code,['S','thresh','window','refrac','nchan','nsamp','events'],
                 type_converters=weave.converters.blitz)

    return nx.asarray(events)


def realign(spikes, **kwargs):
    """
    Realigns spike waveforms based on peak time. The peak of a linearly
    interpolated sample can be off by at least one sample, which
    has severe negative effects on later compression with PCA. This
    function uses a sinc interpolator to upsample spike waveforms, which
    are then realigned to peak time.

    If the spikes are from more than one electrode, the mean across electrode
    is used to determine spike peak

    axis        = the axis to perform the analysis on (default 1)
    resamp_rate = integer indicating the upsampling factor (default 3)
    max_shift   = maximum amount peaks can be shifted (in samples, default 4)
    downsamp    = if true, the data are downsampled back to the original
                  sampling rate after peak realignment
    """
    from dlab.signalproc import fftresample
    
    ax = kwargs.get('axis',1)
    resamp_rate = kwargs.get('resamp_rate',3)
    max_shift = kwargs.get('max_shift',4) * resamp_rate

    np = spikes.shape[1] * resamp_rate
    upsamp = fftresample(spikes,np,axis=1)

    # now find peaks
    if upsamp.ndim>2:
        peaks = upsamp.mean(2).argmax(axis=ax)
    else:
        peaks  = upsamp.argmax(axis=ax)
    shift  = (peaks - nx.median(peaks)).astype('i')
    
    goodpeaks = nx.absolute(shift)<=(max_shift)
    nbadpeaks = shift.size - goodpeaks.sum()
    # this line will leave artefacts alone
    # shift[nx.absolute(shift)>(max_shift)] = 0
    # and this will remove spikes that can't be shifted
    if nbadpeaks > 0:
        print "Dropping %d unalignable trials" % nbadpeaks
        shift = shift[goodpeaks]
        upsamp = upsamp[goodpeaks,:,:]
    else:
        goodpeaks = None
    
    shape = list(upsamp.shape)
    start = -shift.min()
    stop  = upsamp.shape[1]-shift.max()
    shape[ax] = stop - start

    shifted = nx.zeros(shape, dtype=upsamp.dtype)
    for i in range(upsamp.shape[0]):
        d = upsamp[i,start+shift[i]:stop+shift[i]]
        shifted[i] = d

    if kwargs.get('downsamp',False):
        npoints = (stop - start) / resamp_rate
        dnsamp = fftresample(shifted, npoints, axis=1)
        return dnsamp,goodpeaks
    else:
        return shifted,goodpeaks
    

def signalstats(pcmfiles):
    """
    Computes the dc offset and covariance of the signal in each entry. Accepts
    multiple pcmfiles, but they have to have the same number of entries.

    Returns a dictionary of statistics (in case we want to add some more)
    """
    if isinstance(pcmfiles, _pcmseqio.pcmfile):
        pcmfiles = [pcmfiles]
        
    nentries = get_nentries(pcmfiles)
    nchans = len(pcmfiles)

    dcoff = nx.zeros((nentries, nchans))
    A = nx.zeros((nentries,nchans,nchans))
    for i in range(nentries):
        nsamp = pcmfiles[0].nframes
        S = nx.empty((nsamp,nchans),_dtype)
        for j in range(nchans):
            pcmfiles[j].seek(i+1)
            s = pcmfiles[j].read()            
            S[:,j] = pcmfiles[j].read()
            dcoff[i,j] = s.mean()

        A[i,:,:] = cov(S,rowvar=0)

    return {'dcoff': dcoff.squeeze(),
            'cov' : A.squeeze()}


def combine_channels(fp, entry):
    """
    Combines data from a collection of channels into a single
    array.

    fp - list of pcmfile objects
    entry - the entry to extract from the pcm files. Must be
            a scalar or a list equal in length to fp
    """
    if isinstance(entry,int):
        entry = [entry] * len(fp)

    [fp[chan].seek(entry[chan]) for chan in range(len(fp))]
    nsamples = fp[0].nframes
    signal = nx.zeros((nsamples, len(fp)), _dtype)
    for chan in range(len(fp)):
        signal[:,chan] = fp[chan].read()
        
    return signal


if __name__=="__main__":

    import os
    basedir = '/z1/users/dmeliza/acute_data/st323/20071212/site_5_6'
    pattern = "st323_%d_20071212o.pcm_seq2"
    
    #pcmfiles = [basedir + pattern % d for d in range(1,17)]
    pcmfiles = [os.path.join(basedir, pattern % d) for d in range(9,10)]

    # open files
    print "---> Open test files"
    pfp = [_pcmseqio.pcmfile(fname) for fname in pcmfiles]

    print "---> Get signal statistics"
    stats = signalstats(pfp)

    print "---> Extract raw data from files"
    signal = combine_channels(pfp, 2)

    print "---> Finding spikes..."
    spikes,events = find_spikes(pfp)
    
    print "---> Aligning spikes..."
    rspikes,kept_events = realign(spikes, downsamp=False)
    
    print "---> Calculating feature projections..."
    proj = get_projections(rspikes, ndims=3)
