# https://ome-zarr.readthedocs.io/en/stable/python.html#writing-hcs-datasets-to-ome-ngff

import logging
from ome_zarr.io import parse_url
from ome_zarr.scale import Scaler
from ome_zarr.writer import write_plate_metadata, write_well_metadata, write_image
import zarr

from src.OmeWriter import OmeWriter
from src.ome_zarr_util import *
from src.util import split_well_name


class OmeZarrWriter(OmeWriter):
    def write(self, filename, source, zarr_version=2, ome_version='0.4'):
        self.source = source
        if ome_version == '0.5':
            from ome_zarr.format import FormatV05
            ome_format = FormatV05()
        else:
            from ome_zarr.format import FormatV04
            ome_format = FormatV04()

        zarr_root = zarr.open_group(store=parse_url(filename, mode="w").store, mode="w", zarr_version=zarr_version)

        row_names = source.metadata['well_info']['rows']
        col_names = source.metadata['well_info']['columns']
        well_paths = ['/'.join(split_well_name(info)) for info in source.metadata['wells']]
        field_paths = source.metadata['well_info']['fields']

        scaler = Scaler()

        axes = create_axes_metadata(source.get_dim_order())

        acquisitions = []
        for index, acq in enumerate(source.metadata.get('acquisitions', [])):
            acquisitions.append({
                'id': index,
                'name': acq['Name'],
                'description': acq['Description'],
                'date_created': acq['DateCreated'].isoformat(),
                'date_modified': acq['DateModified'].isoformat()
            })

        write_plate_metadata(zarr_root, row_names, col_names, well_paths, acquisitions=acquisitions)
        for well_id in source.metadata['wells']:
            row, col = split_well_name(well_id)
            row_group = zarr_root.require_group(str(row))
            well_group = row_group.require_group(str(col))
            write_well_metadata(well_group, field_paths)
            source.select_well(well_id)

            pixel_size_scales = []
            scale = 1
            for i in range(scaler.max_layer + 1):
                pixel_size_scales.append(
                    create_transformation_metadata(source.get_dim_order(), source.get_pixel_size_um(),
                                                   scale, source.get_well_coords_um(well_id)))
                scale /= scaler.downscale

            for field_index, field in enumerate(field_paths):
                image_group = well_group.require_group(str(field))
                data = self.source.get_image(field_index)
                write_image(image=data, group=image_group, axes=axes, coordinate_transformations=pixel_size_scales,
                            scaler=scaler, fmt=ome_format)

        dtype = source.get_dtype()
        channels = source.metadata['channels']
        nchannels = max(len(channels), 1)
        zarr_root.attrs['omero'] = create_channel_metadata(dtype, channels, nchannels, ome_version)

        logging.info(f"Exported as {filename}")
