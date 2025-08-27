from ome_zarr.io import parse_url
from ome_zarr.reader import Reader
import os
import pytest
import tempfile

from ImageDbSource import ImageDbSource
from converter import init_logging, convert
from src.Timer import Timer
from util import splitall, print_dict


class TestConvert:
    #basedir = 'C:/Project/slides/DB/'
    basedir = 'D:/slides/DB/'

    filename = 'TestData1'
    #filename = '2ChannelPlusTL'
    #filename = 'PicoData16ProcCoverag'
    #filename = '241209 - TC1 TC9 test MSP MUB'
    #filename = '20220714_TKI_482'
    #filename = 'Cells'

    input_filename = basedir + filename + '/experiment.db'

    @pytest.mark.parametrize(
        "input_filename, output_format",
        [
            (
                input_filename,
                'omezarr2',
            ),
            (
                input_filename,
                'omezarr3',
            ),
        ],
    )
    def test_convert(self, tmp_path, input_filename, output_format):
        init_logging('log/db_to_zarr.log')
        with Timer(f'convert {input_filename} to {output_format}'):
            convert(input_filename, tmp_path, output_format=output_format)

        source = ImageDbSource(input_filename)
        metadata = source.init_metadata()
        #print(print_dict(metadata))
        source_pixel_size = source.get_pixel_size_um()
        source_wells = source.get_wells()

        output_path = os.path.join(tmp_path, source.get_name() + '.ome.zarr')
        reader = Reader(parse_url(output_path))

        if '2' in output_format:
            assert float(reader.zarr.version) == 0.4
        elif '3' in output_format:
            assert float(reader.zarr.version) >= 0.5

        for node in reader():
            metadata = node.metadata
            #print(print_dict(metadata))
            axes = [axis['name'] for axis in metadata['axes']]
            pixel_sizes = [transform for transform in metadata['coordinateTransformations'][0] if transform['type'] == 'scale'][0]['scale']
            pixel_size_dict = {axis: pixel_size for axis, pixel_size in zip(axes, pixel_sizes)}
            wells = [well['path'].replace('/', '') for well in metadata['metadata']['plate']['wells']]
            #for data in node.data:
            #    print('shape', data.shape)

            if '2' in output_format:
                assert float(node.zarr.version) == 0.4
            elif '3' in output_format:
                assert float(node.zarr.version) >= 0.5

            assert pixel_size_dict['x'] == source_pixel_size['x']
            assert pixel_size_dict['y'] == source_pixel_size['y']
            assert wells == source_wells


if __name__ == '__main__':
    # Emulate pytest / fixtures
    from pathlib import Path

    test = TestConvert()
    input_filename = test.input_filename
    test.test_convert(Path(tempfile.TemporaryDirectory().name), input_filename, 'omezarr2')
    test.test_convert(Path(tempfile.TemporaryDirectory().name), input_filename, 'omezarr3')
