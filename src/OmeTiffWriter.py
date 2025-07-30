import logging
import os
from tifffile import tifffile

from src.OmeWriter import OmeWriter


class OmeTiffWriter(OmeWriter):
    def write(self, filename, source, well_id=None, tile_id=None, timepoint_id=None, level=0, tiff_compression=None):
        filepath, filename = os.path.split(filename)
        filetitle, ext = os.path.splitext(filename)

        filename = f"{filetitle}"
        if self.channel is not None:
            filename += f"_ch{self.channel}"
        filename += f"_{self.add_leading_zero(well_id)}"
        well_info = self._read_well_info(well_id)
        if self.imdata is None:
            self._assemble_image_data(well_info)
        imdata = self._extract_tile(tile_id).squeeze()
        if tile_id is not None and tile_id >= 0:
            filename += f"_{self.add_leading_zero(tile_id)}"
        if self.level > 0:
            filename += f"_level{self.level}"

        filename = os.path.join(filepath, filename + ext)
        if ext.lower() in ['.tif', '.tiff']:
            with tifffile.TiffWriter(filename) as tif:
                tif.write(imdata, compression=tiff_compression, dtype=self.dtype)

        logging.info(f"Image saved as {filename}")
