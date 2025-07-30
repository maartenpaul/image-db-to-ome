import logging
import os

from src.ImageDbSource import ImageDbSource
from src.OmeZarrWriter import OmeZarrWriter


def init_logging(log_filename):
    basepath = os.path.dirname(log_filename)
    if basepath and not os.path.exists(basepath):
        os.makedirs(basepath)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s',
                        handlers=[logging.StreamHandler(), logging.FileHandler(log_filename, encoding='utf-8')],
                        encoding='utf-8')


def print_dict(items, tab=0):
    if isinstance(items, dict):
        for key, value in items.items():
            if isinstance(value, dict):
                print(key + ':')
                print_dict(value, tab+1)
            else:
                print('\t' * tab + f'{key}: {value}')


if __name__ == '__main__':
    filename = 'D:/slides/DB/TestData1/experiment.db'
    output_filename = 'D:/slides/DB/test.zarr'

    init_logging('db_to_zarr.log')

    writer = OmeZarrWriter()
    source = ImageDbSource(filename)
    print_dict(source.read_experiment_info())
    source.display_well_matrix()
    writer.write(output_filename, source)
    source.close()
