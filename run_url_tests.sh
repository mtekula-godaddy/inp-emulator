#!/bin/bash

# Run INP tests on all URLs from urls.txt
# Usage: ./run_url_tests.sh [interactions_per_url] [--include-header|--skip-header]
#
# Examples:
#   ./run_url_tests.sh                    # 2 elements, skip header (default)
#   ./run_url_tests.sh 5                  # 5 elements, skip header
#   ./run_url_tests.sh 2 --include-header # 2 elements, include header
#   ./run_url_tests.sh 5 --include-header # 5 elements, include header

INTERACTIONS=${1:-2}  # Default to 2 interactions per URL
HEADER_FLAG=${2:-""}  # Optional header flag

if [ "$HEADER_FLAG" = "--include-header" ]; then
    echo "Testing URLs with $INTERACTIONS interactions each (including header elements)..."
elif [ "$HEADER_FLAG" = "--skip-header" ]; then
    echo "Testing URLs with $INTERACTIONS interactions each (skipping header elements)..."
else
    echo "Testing URLs with $INTERACTIONS interactions each (skipping header elements by default)..."
fi
echo ""

# Clean up
rm -rf test_results
mkdir -p test_results

# Read URLs (skip header line)
URLS=$(tail -n +2 urls.txt)

# Test each URL
for url in $URLS; do
    if [ -n "$url" ]; then
        echo "Testing: $url"
        PYTHONPATH=/Users/mtekula/Dev/inputer/src python3 src/inputer/testing/test_runner.py "$url" element_scan priority $INTERACTIONS $HEADER_FLAG
        sleep 1
    fi
done

# Combine results
echo ""
echo "Combining results..."
cd test_results
head -1 $(ls -t inputer_report_*.csv | tail -1) > combined_results.csv
tail -n +2 -q inputer_report_*.csv >> combined_results.csv
cd ..

echo ""
echo "✅ All tests complete!"
echo "📊 Results: test_results/combined_results.csv"
echo ""
echo "View results:"
echo "  cat test_results/combined_results.csv"
