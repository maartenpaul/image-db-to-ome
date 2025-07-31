# https://ome-zarr.readthedocs.io/en/stable/python.html#writing-hcs-datasets-to-ome-ngff

import logging
from ome_zarr.io import parse_url
from ome_zarr.scale import Scaler
from ome_zarr.writer import write_plate_metadata, write_well_metadata, write_image
import zarr

from src.ImageSource import ImageSource
from src.OmeWriter import OmeWriter
from src.ome_zarr_util import *
from src.util import split_well_name, print_hbytes


class OmeZarrWriter(OmeWriter):
    def __init__(self, zarr_version=2, ome_version='0.4', verbose=False):
        super().__init__()
        self.zarr_version = zarr_version
        self.ome_version = ome_version
        if ome_version == '0.5':
            from ome_zarr.format import FormatV05
            self.ome_format = FormatV05()
        else:
            from ome_zarr.format import FormatV04
            self.ome_format = FormatV04()
        self.verbose = verbose

    def write(self, filename, source: ImageSource, **kwargs):
        zarr_root = zarr.open_group(store=parse_url(filename, mode='w').store, mode='w', zarr_version=self.zarr_version)

        dtype = source.get_dtype()
        channels = source.get_channels()
        nchannels = source.get_nchannels()

        row_names = source.get_rows()
        col_names = source.get_columns()
        wells = source.get_wells()
        well_paths = ['/'.join(split_well_name(well)) for well in wells]
        field_paths = source.get_fields()

        axes = create_axes_metadata(source.get_dim_order())
        acquisitions = source.get_acquisitions()

        write_plate_metadata(zarr_root, row_names, col_names, well_paths, acquisitions=acquisitions,
                             fmt=self.ome_format)
        total_size = 0
        for well_id in wells:
            row, col = split_well_name(well_id)
            row_group = zarr_root.require_group(str(row))
            well_group = row_group.require_group(str(col))
            write_well_metadata(well_group, field_paths, fmt=self.ome_format)
            source.select_well(well_id)

            scaler = Scaler()
            pixel_size_scales = []
            scale = 1
            for i in range(scaler.max_layer + 1):
                pixel_size_scales.append(
                    create_transformation_metadata(source.get_dim_order(), source.get_pixel_size_um(),
                                                   scale, source.get_well_coords_um(well_id)))
                scale /= scaler.downscale

            for field_index, field in enumerate(field_paths):
                image_group = well_group.require_group(str(field))
                data = source.get_image(field_index)
                write_image(image=data, group=image_group, axes=axes, coordinate_transformations=pixel_size_scales,
                            scaler=scaler, fmt=self.ome_format)
                total_size += data.size * dtype.itemsize

        if self.verbose:
            print(f'Total written: {print_hbytes(total_size)}')

        zarr_root.attrs['omero'] = create_channel_metadata(dtype, channels, nchannels, self.ome_version)
