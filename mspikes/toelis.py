#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-
"""
module for processing toe_lis files

 CDM, 9/2006
 
"""
import numpy as n
from decorator import deprecated

class toelis(object):
    """
    A toelis object represents a collection of events. Each event is
    simply a scalar time offset.  Events can be associated with a particular
    unit or a particular repeat (i.e. for repeated presentations of an
    identical stimulus).  Frankly I think this is too much generality,
    but there's a lot of software that uses these things, so it's what
    I have to work with.
    """


    def __init__(self, data=None, nrepeats=1, nunits=1):
        """
        Constructs the toelis object. Events are stored in a list
        of lists, and these lists are indexed in a nrepeats x nunits
        array of integers.

        The object can be initialized empty or with data, which can be
        a list of lists.  The <nunits> and <nrepeats> parameters can
        be used to reshape the 1D data.  Data are coerced into numpy
        ndarrays; note that if the data are already in ndarrays the
        toelis will have a VIEW of the data and any modifications will
        affect the input data.
        """

        if data!=None:
            nitems = len(data)
            self.index = n.arange(nitems)
            if nunits==1 and nrepeats==1:
                nrepeats = nitems
            if not (nunits * nrepeats == len(data)):
                raise IndexError, "Number of units and repeats do not add up to data length (%d)" \
                      % len(data)
            
            self.index.shape = (nrepeats, nunits)
            if isinstance(data, self.__class__):
                self.events = data.events
            else:
                self.events = []
                for item in data:
                    if n.isscalar(item):
                        raise ValueError, "Input data cannot be a scalar"
                    self.events.append(n.asarray(item))
            
        else:
            nlists = nrepeats * nunits
            self.index = n.arange(nlists)
            self.index.shape = (nrepeats, nunits)
            self.events = [[] for i in range(nlists)]


    def __getitem__(self, index):
        """
        Retrieve an event list by index. If only a single index is
        given (integer or slice), the index refers to the internal
        list of events; if a pair of indices are supplied, retrieves
        event lists by repeat,unit.
        """
        if n.iterable(index):
            id = self.index[index]
            if n.iterable(id):
                return [self.events[i] for i in id]
            else:
                return self.events[id]
        else:
            return self.events[index]

    def __iter__(self):
        return self.events.__iter__()

    def offset(self, offset):
        """
        Adds a fixed offset to all the time values in the object.
        """
        if not n.isscalar(offset):
            raise TypeError, " can only add scalars to toelis events"
        for i in range(len(self.events)):
            self.events[i] = n.asarray(self.events[i]) + offset
 
    def __repr__(self):
        if self.nrepeats < 100:
            return "<%s %d reps, %d units, %d events>" % (self.__class__.__name__,
                                                          self.nrepeats,
                                                          self.nunits,
                                                          self.nevents)
        else:
            return "<%s %d reps, %d units>" % (self.__class__.__name__,
                                               self.nrepeats,
                                               self.nunits)


    def __len__(self):
        return len(self.events)

    @property
    def size(self):
        """
        Returns the size of the object (nrepeats * nunits)
        """
        return n.prod(self.index.shape)

    @property
    def nunits(self):
        return self.index.shape[1]
    
    @property
    def nrepeats(self):
        return self.index.shape[0]

    @property
    def nevents(self):
        return sum([len(x) for x in self])

    @property
    def range(self):
        """
        The range of event times in the toelis.
        """
        allevents = n.concatenate(self)
        if allevents.size == 0: return None,None
        return allevents.min(), allevents.max()

    def subrange(self, onset=None, offset=None, adjust=False):
        """
        Returns a new toelis object only containing events between onset and offset (inclusive).
        Default values are -Inf and +Inf.

        If <adjust> is True, set times relative to onset
        If <adjust> is a scalar, set times relative to <adjust>
        Default is to leave the times alone
        """
        mintime,maxtime = self.range
        if onset==None: onset = mintime
        if offset==None: offset = maxtime
        if adjust==True:
            adjust = onset
        elif adjust==False:
            adjust = 0
        return toelis([x[((x>=onset) & (x<=offset))] - adjust for x in self])

    @deprecated
    def tondarray(self):
        """
        Ensures that all the event lists are ndarray objects
        """
        for i in range(self.size):
            self.events[i] = n.asarray(self[i])

    def extend(self, newlis, dim=0):
        """
        Concatenates two toelis objects along a dimension. By default,
        the second toelis is treated as more repeats, but set <dim> to
        1 to treat them as additional units.
        """
        if not self.index.shape[(1 - dim)]==newlis.index.shape[(1 - dim)]:
            raise ValueError, "Dimensions do not match for merging along dim %d " % dim

        offset = len(self)
        self.index = n.concatenate((self.index, newlis.index + offset), axis=dim)
        self.events.extend(newlis.events)

    def merge(self, newlis, offset=0.0):
        """
        Merge two toelis objects by concatenating events in
        corresponding repeats.  For example, if tl1[0]= [1,2,3] and
        tl2[0]= [4,5,6], after tl1.merge(tl2), tl1[0] = [1,2,3,4,5,6].

        <offset> is added to all events in newlis
        """
        if not self.index.shape==newlis.index.shape:
            raise ValueError, "Repeat and unit dimensions must match"
        self.events = [n.concatenate([elist, newlis[i] + offset]) for i,elist in enumerate(self)]
            

    def unit(self, unit):
        """
        Retrieves a single unit from the toelis object (as a new toelis)
        """
        id = self.index[:,unit]
        return toelis(data=[self.events[i] for i in id])

    def repeats(self, repeats):
        """
        Retrieve particular repeats from the toelis object (as a new toelis)
        """
        id = self.index[repeats,:]
        return toelis(data=[self.events[i] for i in id])

    def __serializeunit(self, unit):
        """
        Generates a serialized representation of all the repeats in a unit.
        """
        output = []
        id = self.index[:,unit]
        for ri in range(len(id)):
            events = self.events[id[ri]]
            output.insert(ri, len(events))
            output.extend(events)
        return output
    # end serializeunit


    def writefile(self, filename):
        """
        Writes the data to a toe_lis file. This is (as I've expressed earlier in this file),
        a horribly kludgy format.  See toelis.loadfile() for a description of the format
        """
        # this is much easier to construct in memory
    
        output = []
        l_units = [0]
        for ui in range(self.nunits):
            serialized  = self.__serializeunit(ui)
            l_units.append(len(serialized))
            output.extend(serialized)

        output.insert(0, self.nunits)
        output.insert(1, self.nrepeats)
        for ui in range(self.nunits):
            output.insert(2+ui, 3 + self.nunits + sum(l_units[0:ui+1]))


        try:
            output = map(str, output)
            fp = open(filename, 'wt')
            fp.writelines("\n".join(output))
        finally:
            fp.close()
    # end writefile

    def rasterpoints(self, unit=0, reps=None):
        """
        Rasterizes the data from a unit as a collection of x,y points,
        with the x position determined by the event time and the y position
        determined by the repeat index. Returns a tuple of arrays, (x,y)

        unit - control which unit gets rasterized
        reps - control which repeats get included (slice or range)
        """
        x = self.unit(unit).events
        if reps != None:
            x = x[reps]
        
        y = n.concatenate([n.ones(x[i].shape) * i for i in range(len(x))])
        x = n.concatenate(x)
        return x,y



# end toelis

def readfile(filename):
    """
    Constructs a toelis object by reading in a toe_lis file. The
    format of this file is kludgy to say the least.
    # line 1 - number of units (nunits)
    # line 2 - total number of repeats per unit (nreps)
    # line 3:(3+nunits) - starting lines for each unit, i.e. pointers
    # to locations in the file where unit data is. Advance to that line
    # and scan in nreps lines, which give the number of events per repeat.

    Did I mention how stupid it is to have both line number pointers AND
    length values in the header data?
    """
    fp = open(filename,'rt')
    linenum = 0
    n_units = None
    n_repeats = None
    p_units = []
    p_repeats = []
    current_unit = None
    current_repeat = None
    for line in fp:
        linenum += 1
        if not n_units:
            n_units = int(line)
            #print "n_units: %d" % n_units
        elif not n_repeats:
            n_repeats = int(line)
            #print "n_repeats: %d" % n_repeats
            # once we know n_units and n_repeats, initialize the output object
            out = toelis(None, nunits=n_units, nrepeats=n_repeats)
            #print "initialized toelis: %s" % out
        elif len(p_units) < n_units:
            # scan in pointers to unit starts until we have n_units
            p_units.append(int(line))
            #print "unit pointers: %s" % p_units
        elif linenum in p_units:
            # if the line number matches a unit pointer, set the current_unit
            current_unit = p_units.index(linenum)
            #print "Start unit %d at line %d" % (current_unit, linenum)
            # and reset the repeat pointer list. Note that the read values
            # are lengths, so we have to convert to pointers
            p_repeats = [linenum + n_repeats]
            l_repeats = [int(line)]
            #print "repeat pointers: %s" % p_repeats
        elif len(p_repeats) < n_repeats:
            # if we don't have enough repeat pointers, read in integers
            # the pointer is p_repeats[-1] + l_repeats[-1]
            p_repeats.append(p_repeats[-1] + l_repeats[-1])
            l_repeats.append(int(line))
            #print "repeat pointers: %s" % p_repeats            
        elif linenum in p_repeats:
            # now set the current_repeat index and read in a float
            current_repeat = p_repeats.index(linenum)
            #print "Start unit %d, repeat %d data at line %d" % (current_unit, current_repeat, linenum)
            out[current_repeat, current_unit].append(float(line))
        else:
            out[current_repeat, current_unit].append(float(line))

    fp.close()
    # make all the event lists arrays
    out.tondarray()
    return out
# end readfile

