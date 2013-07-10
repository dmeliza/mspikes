# -*- coding: utf-8 -*-
# -*- mode: python -*-
"""Functions and classes for reading and writing ARF files.

Copyright (C) 2013 Dan Meliza <dmeliza@uchicago.edu>
Created Wed May 29 14:50:02 2013
"""
import h5py
import numpy
import logging
import functools
import operator
from fractions import Fraction
from mspikes import util
from mspikes.types import DataBlock, Node, RandomAccessSource, tag_set

_log = logging.getLogger(__name__)

class arf_reader(RandomAccessSource):
    """Source data from an ARF/HDF5 file

    Produces data by iterating through entries of the file in temporal order,
    emitting chunks separately for each dataset in the entries. By default the
    timestamp of the entries is used to calculate offsets for the chunks, but
    for ARF files created by 'arfxplog' and 'jrecord' the sample clock can be
    used as well.

    emits: data blocks from ARF file (_events and _samples)
           entry start times (_structure)

    Note: using sample-based offsets with files that were recorded at different
    sampling rates or with different instances of the data collection program
    will lead to undefined behavior because the sample counts will not be
    consistent within the file.

    """
    blockchunks = 64               # number of hdf5 chunks to process at once

    @classmethod
    def options(cls, addopt_f, **defaults):
        addopt_f("filename",
                 help="the file to read")
        addopt_f("--channels",
                 help="names or regexps of channels to read (default all)",
                 metavar='CH',
                 nargs='+')
        addopt_f("--start",
                 help="time (in s) to start reading (default 0)",
                 type=float,
                 default=0,
                 metavar='FLOAT')
        addopt_f("--stop",
                 help="time (in s) to stop reading (default None)",
                 type=float,
                 metavar='FLOAT')
        addopt_f("--entries",
                 help="names or regexps of entries to read (default all)",
                 metavar='P',
                 nargs="+")
        addopt_f("--use-timestamp",
                 help="use entry timestamp for timebase and ignore other fields",
                 action='store_true')
        addopt_f("--ignore-xruns",
                 help="use entries with xruns or other errors (default is to skip)",
                 action='store_true')
        addopt_f("--skip-sort",
                 help="skip initial sort of entries",
                 action='store_true')


    def __init__(self, filename, **options):
        import re
        util.set_option_attributes(self, options,
                                   start=0, stop=None, use_timestamp=False, use_xruns=False)

        if isinstance(filename, h5py.File):
            self.file = filename
        else:
            self.file = h5py.File(filename, "r")
        _log.info("input file: %s", self.file.filename)

        channels = options.get("channels", None)
        if channels:
            rx = (re.compile(p).search for p in channels)
            self.chanp = util.chain_predicates(*rx)
        else:
            self.chanp = true_p

        entries = options.get("entries", None)
        if entries:
            rx = (re.compile(p).search for p in entries)
            self.entryp = util.chain_predicates(*rx)
        else:
            self.entryp = true_p

        self.entries = self._entry_table()
        self.sampling_rate = self._sampling_rate()
        if self.sampling_rate:
            _log.info("file sampling rate (nominal): %d Hz", self.sampling_rate)

    @property
    def creator(self):
        """The program that created the file, or None if unknown"""
        if self.file.attrs.get('program', None) == 'arfxplog':
            return 'arfxplog'
        elif "jill_log" in self.file:  # maybe check for jack_sample attribute?
            return "jill"
        else:
            return None

    def _entry_table(self):
        """ Generate a table of entries and start times """
        from arf import timestamp_to_float

        if self.use_timestamp or self.creator is None:
            keyname = "timestamp"
            keyiter = functools.partial(keyiter_attr, name='timestamp', fun=timestamp_to_float)
            if self.creator is None:
                _log.info("couldn't determine ARF file source, using default sort method")
        elif self.creator == 'arfxplog':
            keyname = "sample_count"
            keyiter = functools.partial(keyiter_attr, name=keyname)
        elif self.creator == 'jill':
            keyname = "jack_frame"
            keyiter = keyiter_jack_frame
        _log.info("sorting entries by '%s'", keyname)

        # filter by name and type
        entries = (entry for name, entry in self.file.iteritems()
                   if self.entryp(name) and isinstance(entry, h5py.Group))
        # keyiter extracts key, entry pairs; then we sort by key
        return sorted(keyiter(entries), key=operator.itemgetter(0))

    def _sampling_rate(self):
        """Infer sampling rate from file"""
        if self.use_timestamp or self.creator is None:
            return None
        elif self.creator == 'arfxplog':
            return self.file.attrs['sampling_rate']
        elif self.creator == 'jill':
            # returns sampling rate of first dataset
            def srate_visitor(name, obj):
                if isinstance(obj, h5py.Dataset):
                    # if None is returned the iteration will continue
                    return obj.attrs.get("sampling_rate", None)
            return self.file.visititems(srate_visitor)

    def iterdatasets(self):
        """Iterate through the datasets.

        yields DataBlocks with the data field referencing the dataset object

        Datasets that don't match the entry and dataset selectors are skipped,
        as are datasets that have timebases inconsistent with the rest of the
        file.

        """

        time_0 = self.entries[0][0]
        for entry_time, entry in self.entries:
            # check for marked errors
            if "jill_error" in entry.attrs:
                _log.warn("'%s' was marked with an error: '%s'%s", entry.name, entry.attrs['jill_error'],
                          " (skipping)" if not self.use_xruns else "")
                if not self.use_xruns:
                    continue

            # emit structure blocks to indicate entry onsets
            yield DataBlock(id=entry.name,
                            offset=data_offset(entry_time - time_0, self.sampling_rate),
                            dt=self.sampling_rate,
                            data=(),
                            tags=tag_set("structure"))

            for id, dset in entry.iteritems():
                if not self.chanp(id):
                    continue

                dset_dt = dset.attrs.get('sampling_rate', None)

                try:
                    dset_time = data_offset(entry_time - time_0, self.sampling_rate,
                                            dset.attrs.get('offset', 0), dset_dt)
                except ValueError:
                    _log.warn("'%s' sampling rate (%s) incompatible with file sampling rate (%d)",
                              dset.name, dset_dt, self.sampling_rate)
                    continue

                if "units" in dset.attrs and dset.attrs["units"] in ("s", "samples","ms"):
                    tag = "events"
                else:
                    tag = "samples"

                yield DataBlock(id=id, offset=dset_time, dt=dset_dt, data=dset, tags=tag_set(tag))

    def __iter__(self):
        """Iterate through the data in the file"""
        from collections import defaultdict

        dtype = type(self.entries[0][0])   # type of timebase
        # monitor the time in each channel to check for inconsistencies
        cp = self.channel_time = defaultdict(dtype)
        for dset in self.iterdatasets():

            if "events" in dset.tags:
                # point process data is sent in one chunk
                if self.start or self.stop:
                    # filter out events outside requested times
                    data_seconds = ((dset.data['start'] if dset.data.dtype.names else dset.data[:])
                                    * (dset.dt or 1.0) + dset_time)
                    idx = data_seconds >= self.start
                    if self.stop:
                        idx &= data_seconds <= self.stop
                    if idx.sum() > 0:
                        # only emit chunk if there's data
                        dset = dset._replace(data=dset.data[idx])
                Node.send(self, dset)
                yield dset

            elif "samples" in dset.tags:
                # check for overlap (within channel).
                if dset.offset < cp[dset.id]:
                    _log.warn("'%s' (start=%s) overlaps with previous dataset (end=%s)",
                              dset.data.name, dset.offset, cp[dset.id])

                # restrict by time
                nframes = dset.data.shape[0]
                blocksize = self.blockchunks * (dset.data.chunks[0] if dset.data.chunks else 1024)
                start, stop = time_series_offsets(dset.offset, dset.dt, self.start, self.stop, nframes)

                for i in xrange(start, stop, blocksize):
                    t = dset.offset + Fraction(i, int(dset.dt))
                    data = dset.data[slice(i, i + blocksize), ...]
                    chunk = dset._replace(offset=t, data=data)
                    Node.send(self, chunk)
                    yield chunk

                cp[dset.id] = data_offset(dset.offset, self.sampling_rate, nframes, dset.dt)

            else:
                # pass on structure and other non-data chunks
                Node.send(self, dset)
                yield dset


def true_p(*args):
    return True


def attritemgetter(name):
    """Return a function that extracts arg.attr['name']"""
    return lambda arg: arg.attrs[name]


def keyiter_attr(entries, name, fun=None):
    """Iterate entries producing (key, entry) pairs.

    key is entry.attrs['name'], or if fun is defined, fun(entry.attrs['name'])

    Skips entries with no 'name' attribute

    """
    keyfun = attritemgetter(name)
    if fun is not None:
        keyfun = util.compose(fun, keyfun)
    for entry in entries:
        try:
            yield keyfun(entry), entry
        except KeyError:
            _log.info("'%s' skipped (missing '%s' attribute)", entry.name, name)


def keyiter_jack_frame(entries):
    """Iterate entries producing (key, entry), with key = jack_frame

    jack_frame values are converted from uint32 values (which may overflow) to
    uint64 values

    """
    from operator import itemgetter
    from numpy import uint64, seterr
    orig = seterr(over='ignore')   # ignore overflow warning

    # first sort by jack_usec, a uint64
    usec_sorted = sorted(keyiter_attr(entries, "jack_usec"), key=itemgetter(0))

    # then convert the jack_frame uint32's to uint64's by incrementing. this may
    # not be very efficient, and won't work if there's a gap longer than the
    # size of the frame counter; could potentially do some kind of arithmetic
    # with the usec variable and the sample rate.
    _, entry = usec_sorted[0]
    last = entry.attrs['jack_frame']
    frame = uint64(0)
    yield (frame, entry)
    for _, entry in usec_sorted[1:]:
        current = entry.attrs['jack_frame']
        frame += current - last
        last = current
        yield (frame, entry)

    seterr(**orig)              # restore numpy error settings


def corrected_sampling_rate(keyed_entries):
    """Calculate the sampling rate relative to the system clock"""
    from arf import timestamp_to_float
    kf = attritemgetter('timestamp')
    entries = (keyed_entries[0], keyed_entries[-1])
    (s1, t1), (s2, t2) = ((s,timestamp_to_float(kf(e))) for s, e in entries)
    return (s2 - s1) / (t2 - t1)


def data_offset(entry_time, entry_dt, dset_time=0, dset_dt=None):
    """Return offset of a dataset in seconds, as either a float or a Fraction"""
    dtype = type(entry_time)

    if dset_dt is not None:
        dset_time = Fraction(int(dset_time), int(dset_dt))

    if entry_dt is None:
        # converts to float
        return entry_time + dset_time
    else:
        entry_time = Fraction(long(entry_time), long(entry_dt))
        if dset_dt is None:
            # find nearest sample
            return entry_time + Fraction(int(round(dset_time * entry_dt)), int(entry_dt))
        else:
            val = entry_time + dset_time
            if (val * entry_dt).denominator != 1:
                raise ValueError("dataset timebase is incompatible with entry timebase")
            return val


def time_series_offsets(dset_time, dset_dt, start_time, stop_time, nframes):
    """Calculate indices of start and stop times in a time series.

    For an array of nframes that begins at data_time (samples) with timebase
    offset_dt (samples/sec) and has samples spaced at dset_dt (samples/sec),
    returns the range of valid indices into the array, restricted between start_time
    and stop_time (in seconds).

    """
    start_idx = max(0, (start_time - dset_time) * dset_dt) if start_time else 0
    stop_idx = min(nframes, (stop_time - dset_time) * dset_dt) if stop_time else nframes

    return int(start_idx), int(stop_idx)

# Variables:
# End:
