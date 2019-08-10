#!/bin/bash

files=$(find . -type f | grep -e '\.py$')

pylint $files
