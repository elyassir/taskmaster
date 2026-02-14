#!/bin/bash
echo "Current umask: $(umask)"
TESTFILE="/tmp/umask_test_file_$$"
touch "$TESTFILE"
echo "Created file permissions:"
ls -la "$TESTFILE"
rm "$TESTFILE"
