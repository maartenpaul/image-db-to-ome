#from crxReaderTime import crxreader
from CRXReader import CRXReader


if __name__ == '__main__':
    filename = 'data/TestData2/experiment.db'
    output_filename = 'test.zarr'

    #info = crxreader(filename, verbose=True)
    #im = crxreader(filename, well='B2', tile=1, save_as=output_filename, info=info)

    crx = CRXReader(filename, verbose=True)
    info = crx.read_experiment_info()
    print(info)
    crx.display_well_matrix()
    #crx.extract_data(output_filename, well_id='B1', tile_id=0)
    crx.export_to_zarr(output_filename)
