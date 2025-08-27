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

    logging.getLogger('ome_zarr').setLevel(logging.WARNING)     # mute verbose ome_zarr logging


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

    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    logging.info(f'Importing {input_filename}')
    source = ImageDbSource(input_filename)
    metadata = source.init_metadata()
    if verbose:
        print(print_dict(metadata))
        print()
        print(source.print_well_matrix())
        print(source.print_timepoint_well_matrix())
        print(f'Total data size:    {print_hbytes(source.get_total_data_size())}')

    name = source.get_name()
    output_path = os.path.join(output_folder, name + ext)
    writer.write(output_path, source, name=name)
    source.close()

    if show_progress:
        print(f'Converting {input_filename} to {output_path}')

    message = f'Exported  {output_path}'
    result = {'name': name, 'full_path': output_path}
    if alt_output_folder:
        if not os.path.exists(alt_output_folder):
            os.makedirs(alt_output_folder)
        alt_output_path = os.path.join(alt_output_folder, name + ext)
        if 'zar' in output_format:
            shutil.copytree(output_path, alt_output_path, dirs_exist_ok=True)
        else:
            shutil.copy2(output_path, alt_output_path)
        result['alt_path'] = alt_output_path
        message += f' and {alt_output_path}'

    logging.info(message)
    if show_progress:
        print(message)

    return json.dumps(result)
