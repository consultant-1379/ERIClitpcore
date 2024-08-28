#!/usr/bin/env python

import os
import sys

currentDir = os.getcwd()
sourceDir = '../doc/sphinx/source/'
buildDir = 'target/site/'
sphinxPath = 'target/sphinx/'


def setupPythonPath(*paths):
    p = []
    for path in paths:
        sphinxAbsPath = os.path.abspath(os.path.join(currentDir, path))
        p.append(sphinxAbsPath)
    sys.path[:0] = p

if __name__ == '__main__':

    if len(sys.argv) != 3:
        print 'Error: Please specify the documentation version'
        print 'usage:', sys.argv[0], '<Drop version>', '<Project version>'
        sys.exit(1)
    else:
        release = 'release=' + sys.argv[1]
        version = 'version=' + sys.argv[2]

    setupPythonPath(sphinxPath)

    from sphinx import cmdline
    cmdline.main([sys.argv[0], '-a', '-D', release, '-D', version,
                  os.path.abspath(os.path.join(currentDir, sourceDir)),
                  os.path.abspath(os.path.join(currentDir, buildDir))])
