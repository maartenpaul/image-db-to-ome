from CRXReader import CRXReader
#from crxReaderTime import crxreader


if __name__ == '__main__':
    filename = 'data/TestData1/experiment.db'
    output_filename = 'test.tif'

    #info = crxreader(filename, verbose=True)
    #im = crxreader(filename, well='B2', tile=1, save_as=output_filename, info=info)

    crx = CRXReader(verbose=True)
    info = crx.read_experiment_info(filename)
    print(info)
    crx.extract_data(output_filename, well_id='B2', tile_id=1)
