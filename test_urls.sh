#!/bin/bash

# Test all URLs from urls.txt
rm -rf test_results
mkdir -p test_results

tail -n +2 urls.txt | while IFS= read -r url; do
    if [ -n "$url" ]; then
        echo "Testing: $url"
        PYTHONPATH=/Users/mtekula/Dev/inputer/src python3 src/inputer/testing/test_runner.py "$url" element_scan priority 2 || echo "Failed: $url"
        sleep 2
    fi
done

echo ""
echo "All tests complete. Results in test_results/"
