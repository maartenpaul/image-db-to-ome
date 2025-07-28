#from crxReaderTime import crxreader
from CRXReader import CRXReader


def print_dict(items, tab=0):
    if isinstance(items, dict):
        for key, value in items.items():
            if isinstance(value, dict):
                print(key + ':')
                print_dict(value, tab+1)
            else:
                print('\t' * tab + f'{key}: {value}')


if __name__ == '__main__':
    filename = 'data/TestData1/experiment.db'
    output_filename = 'test.zarr'

    #info = crxreader(filename, verbose=True)
    #im = crxreader(filename, well='B2', tile=1, save_as=output_filename, info=info)

    crx = CRXReader(filename, verbose=True)
    print_dict(crx.read_experiment_info())
    crx.display_well_matrix()
    #crx.extract_data(output_filename, well_id='B1', tile_id=0)
    crx.export_to_zarr()
    crx.close()
