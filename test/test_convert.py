from ome_zarr.io import parse_url
from ome_zarr.reader import Reader
import os

from converter import init_logging, convert
from src.Timer import Timer
from util import splitall, print_dict


def test_convert(filename, output_folder, output_format):
    init_logging('log/db_to_zarr.log')
    with Timer(f'convert {filename} to zarr'):
        convert(filename + '/experiment.db', output_folder, output_format=output_format,
                show_progress=True, verbose=True)

    output_filename = splitall(os.path.splitext(filename)[0])[-1]
    output_path = os.path.join(output_folder, output_filename + '.ome.zarr')
    reader = Reader(parse_url(output_path))
    for node in reader():
        print(print_dict(node.metadata))
        for data in node.data:
            print('shape', data.shape)


if __name__ == '__main__':
    basedir = 'C:/Project/slides/DB/'
    #basedir = 'D:/slides/DB/'

    filename = 'TestData1'
    #filename = '2ChannelPlusTL'
    #filename = 'PicoData16ProcCoverag'
    #filename = '241209 - TC1 TC9 test MSP MUB'
    #filename = '20220714_TKI_482'
    #filename = 'Cells'

    output_format = 'omezarr2'
    #output_format = 'omezarr3'

    output_folder = basedir

    test_convert(basedir + filename, output_folder, output_format)
