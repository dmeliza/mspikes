# -*- coding: utf-8 -*-
# -*- mode: python -*-
"""Module-level register for data chunk ids

Data sources should register chunk ids as follows:

add_id(id, **properties)

Check whether an id already exists:

Copyright (C) 2013 Dan Meliza <dmeliza@gmail.com>
"""
import logging

_register = {}
_log = logging.getLogger('mspikes.register')


def add_id(id, **properties):
    """Adds an identity to the register.

    Raises a NameError if the id has already been registered. If 'uuid' is a
    keyword argument and the value is None, a random uuid is generated.

    """
    from uuid import uuid4
    if has_id(id):
        raise NameError("'%s' has already been registered" % id)
    if 'uuid' in properties:
        if properties['uuid'] is None:
            properties['uuid'] = str(uuid4())
    else:
        _log.warn("warning: '%s' does not have a uuid", id)
    _register[id] = properties
    _log.debug("'%s' properties: %s", id, properties)


def has_id(id):
    """Returns True if id has been registered"""
    return id in _register


def get_properties(id):
    """Returns properties for id. If id has not been registered, returns an empty dict"""
    try:
        return _register[id]
    except KeyError:
        return {}
