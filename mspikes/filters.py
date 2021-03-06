# -*- coding: utf-8 -*-
# -*- mode: python -*-
"""Functions to filter data chunks. Filtering can be by tag or with a function.

Copyright (C) 2013 Dan Meliza <dmeliza@uchicago.edu>
Created Fri May 31 13:19:05 2013

"""

def all_tags(*tags):
    """Include if all tags are present"""
    def f(obj):
        return all(tag in obj.tags for tag in tags)
    return f

def any_tag(*tags):
    """Include if any tag is present"""
    def f(obj):
        return any(tag in obj.tags for tag in tags)
    return f

def _get(name):
    """Look up filter in this module.

    If 'name' starts with '_', it's interpreted as a tag lookup; otherwise, it's taken
    to refer to a function in this module or one registered with the
    org.meliza.mspikes.filters entry point.

    """
    if name.startswith('_') and len(name) > 1:
        f = all_tags(name[1:])
        f.__name__ = name
        return f
    else:
        filts = dict(_all())
        try:
            return filts[name]
        except KeyError:
            raise AttributeError("no such filter '%s'" % name)

def _all():
    import inspect
    return inspect.getmembers(inspect.getmodule(_all),
                              lambda x: inspect.isfunction(x) and not x.__name__.startswith('_'))

# Variables:
# End:
