PoseHarvest-and-Normalize

A tiny command-line prototype that fetches simple sources (CSV, HTML table, embedded JSON) and normalizes module pose/time records into a consistent CSV and JSON schema. Includes a validator that flags missing timestamps and mixed orientation conventions.

Usage (Python 3, no deps):

  python main.py --source-type csv --source-path examples/example.csv
  python main.py --source-type html --source-path examples/example.html
  python main.py --source-type json --source-path examples/example_embedded.json

Outputs: normalized.csv, normalized.json, provenance.json

This is a compact prototype for researchers to extend. It performs no network calls by default; provide file paths or redirect fetched content into files.
