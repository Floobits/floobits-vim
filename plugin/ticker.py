#!/usr/bin/env python

import subprocess
import time
import sys
args = ['mvim', '--servername', 'VIM2', '--remote-expr', 'g:floobits_global_tick()']
while True:
    # TODO: learn to speak vim or something :(
    proc = subprocess.Popen(args,
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE)
    (stdoutdata, stderrdata) = proc.communicate()
    # # yes, this is stupid...
    if stdoutdata.strip() != '0':
        sys.stderr.write(stderrdata)
        sys.exit(1)
    time.sleep(0.2)
