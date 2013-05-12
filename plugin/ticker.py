#!/usr/bin/env python

import subprocess
import time

args = ['mvim', '--servername', 'VIM', '--remote-expr', 'g:global_tick()']
while True:
    proc = subprocess.Popen(args,
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE)
    proc.communicate()
    time.sleep(.2)
