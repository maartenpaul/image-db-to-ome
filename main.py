from converter import convert, init_logging
import sys
import argparse

parser = argparse.ArgumentParser(description='Convert file to ome format')
parser.add_argument('input', help='input file')
parser.add_argument('output', help='output directory')
parser.add_argument('--altoutput', help='alternative output directory')
parser.add_argument('--showprogress', action='store_true')
parser.add_argument('--verbose', action='store_true')
args = parser.parse_args()

init_logging('db_to_zarr.log')

result = convert(
    args.input,
    args.output,
    alt_output_folder = args.altoutput,
    show_progress = args.showprogress,
    verbose = args.verbose
)

if result and result != '{}':
    print(result)
    sys.exit(0)
else:
    print('Error')
    sys.exit(1)
