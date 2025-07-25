# based on https://github.com/Cellular-Imaging-Amsterdam-UMC/crxReader-Python
# which is based on https://www.mathworks.com/matlabcentral/fileexchange/154556-crxreader

from datetime import datetime, timedelta
import numpy as np
from ome_zarr.format import FormatV04
from ome_zarr.io import parse_url
from ome_zarr.writer import write_image
from ome_zarr_util import create_axes_metadata
import os
import sqlite3
import tifffile
import zarr


class CRXReader:
    def __init__(self, experiment_file, channel=None, level=0, time_point=0, dype=np.uint16, verbose=True):
        self.experiment_file = experiment_file

        if not os.path.isfile(self.experiment_file):
            raise ValueError('Experimenter file not found!')

        self.verbose = verbose
        self.channel = channel
        self.level = level
        self.time_point = time_point
        self.dtype = dype
        self.info = None
        self.imdata = None

    def read_experiment_info(self):
        self.info = {'experiment_file': self.experiment_file, 'images_file': None}

        self.log('Reading Info from CellReporterXpress experiment.db file')
        try:
            filepath = os.path.dirname(self.experiment_file)
            with sqlite3.connect(self.experiment_file) as conn:
                conn.row_factory = self.dict_factory
                cur = conn.cursor()
                self._fetch_time_series_info(cur, filepath)
                self._fetch_experiment_metadata(cur)
                self._fetch_well_info(cur)
        except sqlite3.Error as e:
            self.log(f'Error Reading Info: {e}')
            return None

        return self.info

    def _fetch_time_series_info(self, cur, filepath):
        cur.execute("SELECT DISTINCT TimeSeriesElementId FROM SourceImageBase")
        time_series_ids = [list(row.values())[0] for row in cur.fetchall()]

        if len(time_series_ids) == 1 and time_series_ids[0] == 0:
            self.time_point = 0
        elif self.time_point not in time_series_ids:
            raise ValueError(f"Invalid TimePoint: {self.time_point}. Available values: {time_series_ids}")
        self.info['images_file'] = os.path.join(filepath, f'images-{self.time_point}.db')

    def _fetch_experiment_metadata(self, cur):
        cur.execute('SELECT DateCreated, Creator, Name FROM ExperimentBase')
        info = cur.fetchone()
        info['DateCreated'] = self.convert_dotnet_ticks_to_datetime(int(info['DateCreated']))
        self.info.update(info)

    def _fetch_well_info(self, cur):
        cur.execute('SELECT SensorSizeYPixels, SensorSizeXPixels, Objective, PixelSizeUm, SensorBitness, SitesX, SitesY FROM AcquisitionExp, AutomaticZonesParametersExp')
        well_info = cur.fetchone()
        cur.execute('SELECT Emission, Excitation, Dye, channelNumber, ColorName FROM ImagechannelExp')
        channel_info = cur.fetchall()

        well_info['channels'] = channel_info

        self.info['well_info'] = well_info

        cur.execute('SELECT Name, ZoneIndex FROM Well WHERE HasImages = 1')
        wells = cur.fetchall()
        self.info['numwells'] = len(wells)
        self.info['wells'] = {well['Name']: well['ZoneIndex'] for well in wells}

    def _read_well_info(self, well_id):
        well_id = self.remove_leading_zero(well_id)
        well_ids = self.info.get('wells', {})

        if well_id not in well_ids:
            raise ValueError(f"Invalid Well: {well_id}. Available values: {well_ids}")

        zone_index = well_ids[well_id]
        with sqlite3.connect(self.info['experiment_file']) as conn:
            conn.row_factory = self.dict_factory
            cur = conn.cursor()
            cur.execute('''
                SELECT CoordX, CoordY, SizeX, SizeY, BitsPerPixel, ImageIndex, channelId
                FROM SourceImageBase
                WHERE ZoneIndex = ? AND level = ? AND TimeSeriesElementId = ?
                ORDER BY CoordX ASC, CoordY ASC
            ''', (zone_index, self.level, self.time_point))
            well_info = cur.fetchall()

        # filter channel
        if self.channel is not None:
            well_info = [info for info in well_info if info['ChannelId'] == self.channel]
        if not well_info:
            self.log(f'Error: No data found for well {well_id}')
        return well_info

    def _assemble_image_data(self, well_info):
        well_info = np.asarray(well_info)
        xmax = np.max([info['CoordX'] + info['SizeX'] for info in well_info])
        ymax = np.max([info['CoordY'] + info['SizeY'] for info in well_info])
        nchannels = len(set([info['ChannelId'] for info in well_info]))
        imdata = np.zeros((nchannels, ymax, xmax), dtype=self.dtype)

        with open(self.info['images_file'], 'rb') as fid:
            for info in well_info:
                fid.seek(info['ImageIndex'])
                coordx, coordy = info['CoordX'], info['CoordY']
                sizex, sizey = info['SizeX'], info['SizeY']
                channeli = info['ChannelId']
                subtile_data = np.fromfile(fid, dtype=self.dtype, count=sizey * sizex)
                subtile_data = subtile_data.reshape((sizey, sizex))
                imdata[channeli, coordy:coordy + sizey, coordx:coordx + sizex] = subtile_data

        self.imdata = imdata

    def _extract_tile(self, tile_id=None):
        well_info = self.info['well_info']
        tilex = well_info['SitesX']
        tiley = well_info['SitesY']
        sizex = well_info['SensorSizeXPixels']
        sizey = well_info['SensorSizeYPixels']

        if tile_id is None:
            # Return full image data
            return self.imdata
        if tile_id < 0:
            # Return list of all tiles
            tiles = []
            for ty in range(tiley):
                for tx in range(tilex):
                    startx = tx * sizex
                    starty = ty * sizey
                    tiles.append(self.imdata[:, starty:starty + sizey, startx:startx + sizex])
            return tiles
        elif 0 <= tile_id < tilex * tiley:
            # Return specific tile
            tx = tile_id % tilex
            ty = tile_id // tilex
            startx = tx * sizex
            starty = ty * sizey
            return self.imdata[:, starty:starty + sizey, startx:startx + sizex]
        else:
            raise ValueError(f"Invalid tile: {tile_id}")

    def extract_data(self, base_filename, well_id, tile_id=None, tiff_compression='deflate'):
        if not self.info:
            self.read_experiment_info()

        filepath, filename = os.path.split(base_filename)
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
        if ext.lower() in ['.zar', '.zarr']:
            # TODO: convert to plate ome-zarr
            # TODO: add channel metadata
            nchannels = max(len(self.info['well_info']['channels']), 1)
            dim_order = 'yx'
            if nchannels > 1:
                dim_order = 'c' + dim_order
            axes = create_axes_metadata(dim_order)
            root = zarr.open_group(store=parse_url(filename, mode="w").store, mode="w", zarr_version=2)
            write_image(image=imdata, group=root, axes=axes, fmt=FormatV04())
        elif ext.lower() in ['.tif', '.tiff']:
            with tifffile.TiffWriter(filename) as tif:
                tif.write(imdata, compression=tiff_compression, dtype=self.dtype)

        self.log(f"Image saved as {filename}")

    def log(self, text):
        if self.verbose:
            print(text)

    @staticmethod
    def add_leading_zero(input_string, num_digits=2):
        output = str(input_string)
        while len(output) < num_digits:
            output = '0' + output
        return output

    @staticmethod
    def remove_leading_zero(well_name):
        if not well_name:
            return well_name
        letter_part = well_name[0]
        digit_part = well_name[1:]
        try:
            digit_part_noleading = str(int(digit_part))
        except ValueError:
            return well_name
        return letter_part + digit_part_noleading

    @staticmethod
    def convert_dotnet_ticks_to_datetime(net_ticks):
        return datetime(1, 1, 1) + timedelta(microseconds=net_ticks // 10)

    def display_well_matrix(self):
        """
        Displays a matrix of wells used for each timepoint with well names.
        """
        with sqlite3.connect(self.experiment_file) as conn:
            cur = conn.cursor()
            cur.row_factory = self.dict_factory

            # Fetch all TimeSeriesElementId values
            cur.execute("SELECT DISTINCT TimeSeriesElementId FROM SourceImageBase")
            time_series_ids = [row['TimeSeriesElementId'] for row in cur.fetchall()]

            # Fetch well data
            cur.execute("SELECT Name, ZoneIndex FROM Well WHERE HasImages = 1")
            wells = cur.fetchall()

            well_names = [self.add_leading_zero(well['Name']) for well in wells]
            well_matrix = []
            for timepoint in time_series_ids:
                cur.execute("""
                    SELECT DISTINCT Well.Name FROM SourceImageBase
                    JOIN Well ON SourceImageBase.ZoneIndex = Well.ZoneIndex
                    WHERE TimeSeriesElementId = ?
                """, (timepoint,))
                wells_at_timepoint = [self.add_leading_zero(row['Name']) for row in cur.fetchall()]

                row = [well if well in wells_at_timepoint else '' for well in well_names]
                well_matrix.append(row)

            print("Timepoint x Well Matrix:")
            for idx, row in enumerate(well_matrix):
                print(f"Timepoint {time_series_ids[idx]}: {row}")

    @staticmethod
    def dict_factory(cur, row):
        dct = {}
        for index, column in enumerate(cur.description):
            dct[column[0]] = row[index]
        return dct
