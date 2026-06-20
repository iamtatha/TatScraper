#!/bin/bash

# Go to action_api directory (optional if already inside)
cd action_api || exit

echo "Starting all server files..."

for file in *_server.py; do
    echo "Starting $file ..."
    
    nohup python "$file" > "${file%.py}.log" 2>&1 &
done

echo "All servers started in background."