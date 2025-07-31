import json
import logging
import os
import shutil

from src.ImageDbSource import ImageDbSource
from src.OmeTiffWriter import OmeTiffWriter
from src.OmeZarrWriter import OmeZarrWriter
from src.util import splitall, print_dict, print_hbytes


def init_logging(log_filename):
    basepath = os.path.dirname(log_filename)
    if basepath and not os.path.exists(basepath):
        os.makedirs(basepath)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s',
                        handlers=[logging.StreamHandler(), logging.FileHandler(log_filename, encoding='utf-8')],
                        encoding='utf-8')


def convert(input_filename, output_folder, alt_output_folder=None,
            output_format='omezarr2', show_progress=False, verbose=False):

    input_ext = os.path.splitext(input_filename)[1].lower()
    if input_ext != '.db':
        raise ValueError(f'Unsupported input file format: {input_ext}. Expected .db')

    if 'zar' in output_format:
        if '3' in output_format:
            zarr_version = 3
            ome_version = '0.5'
        else:
            zarr_version = 2
            ome_version = '0.4'
        writer = OmeZarrWriter(zarr_version=zarr_version, ome_version=ome_version, verbose=verbose)
        ext = '.ome.zarr'
    elif 'tif' in output_format:
        writer = OmeTiffWriter(verbose=verbose)
        ext = '.ome.tiff'
    else:
        raise ValueError(f'Unsupported output format: {output_format}')

    output_filename = splitall(os.path.splitext(input_filename)[0])[-2]
    output_path = os.path.join(output_folder, output_filename + ext)

    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    if show_progress:
        print(f'Converting {input_filename} to {output_path}')

    logging.info(f'Importing {input_filename}')
    source = ImageDbSource(input_filename)
    metadata = source.init_metadata()
    if verbose:
        print(print_dict(metadata))
        print()
        print(source.print_well_matrix())
        print(source.print_timepoint_well_matrix())
        print(f'Total data size:    {print_hbytes(source.get_total_data_size())}')
    writer.write(output_path, source)
    source.close()

    message = f'Exported  {output_path}'
    result = {'name': output_filename, 'full_path': output_path}
    if alt_output_folder:
        if not os.path.exists(alt_output_folder):
            os.makedirs(alt_output_folder)
        alt_output_path = os.path.join(alt_output_folder, output_filename + ext)
        if 'zar' in output_format:
            shutil.copytree(output_path, alt_output_path)
        else:
            shutil.copy(output_path, alt_output_path)
        result['alt_full_path'] = alt_output_path
        message += f' and {alt_output_path}'

    logging.info(message)
    if show_progress:
        print(message)

    return json.dumps(result)


if __name__ == '__main__':
    basedir = 'C:/Project/slides/DB/'
    #basedir = 'D:/slides/DB/'

    #filename = 'TestData2'
    filename = '2ChannelPlusTL'
    #filename = 'PicoData16ProcCoverag'
    #filename = '241209 - TC1 TC9 test MSP MUB'

    output_folder = basedir

    init_logging('db_to_zarr.log')
    convert(basedir + filename + '/experiment.db', output_folder, show_progress=True, verbose=True)
