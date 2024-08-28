#!/bin/bash
old_IFS=$IFS
IFS=':'
new_PATH=''

# Filters the PATH variable, removing entries that are not directories
for dir in $PATH; do
  if [ -d "$dir" ]; then
    if [ -z "$new_PATH" ]; then
      new_PATH="$dir"
    else
      new_PATH="$new_PATH:$dir"
    fi
  fi
done

IFS=$old_IFS

export PATH="$new_PATH"
