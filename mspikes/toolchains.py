# -*- coding: utf-8 -*-
# -*- mode: python -*-
"""Predefined toolchains.

Copyright (C) 2013 Dan Meliza <dmeliza@gmail.com>
Created Wed Jun 19 09:55:10 2013
"""

view_raw = ("Inspect raw sampled data",
            "input = arf_reader()\n"
            "output = stream_sink(input)")

spk_extract = ("Extract spikes from raw neural recordings",
                 "input = file_reader()\n"
                 "hpass = highpass_filter((input, sampled))\n"
                 "spikes = spike_detect(hpass)\n"
                 "output = file_writer(spikes)")


# Variables:
# End:
