# TODO: requires proper implementation

import logging
import os
from tifffile import tifffile

from src.OmeWriter import OmeWriter
from src.util import *


class OmeTiffWriter(OmeWriter):
    def write(self, filename, source, well_id=None, field_id=None, tiff_compression=None):
        filepath, filename = os.path.split(filename)
        filetitle, ext = os.path.splitext(filename)

        filename = f"{filetitle}"
        filename += f"_{add_leading_zero(well_id)}"
        if field_id is not None and field_id >= 0:
            filename += f"_{add_leading_zero(field_id)}"

        filename = os.path.join(filepath, filename + ext)

        source.select_well(well_id)
        data = source.get_image(field_id)

        if ext.lower() in ['.tif', '.tiff']:
            with tifffile.TiffWriter(filename) as tif:
                tif.write(data, compression=tiff_compression, dtype=source.metadata['dtype'])

        logging.info(f"Image saved as {filename}")
