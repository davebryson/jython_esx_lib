#!/bin/sh -e


# It helps to set the 'python.path' setting in jython 'registry' to point to this directory

export CLASSPATH=$PWD/deps/jna.jar:$PWD/deps/vix.jar:$PWD/deps/dom4j-1.6.1.jar:$PWD/deps/jaxen-1.1.1.jar:$PWD/deps/vijava.jar


exec jython $*