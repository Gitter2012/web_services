#!/bin/bash
find . -name "*.pyc" -type f -delete
find . -type d -name "__pycache__" -exec rm -rf {} +

