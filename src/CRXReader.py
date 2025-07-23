# based on https://github.com/Cellular-Imaging-Amsterdam-UMC/crxReader-Python

import sqlite3
import numpy as np
from PIL import Image
import tifffile
import os
from datetime import datetime, timedelta


class CRXReader:
    def __init__(self, **kwargs):
        self.verbose = kwargs.get('verbose', False)
        self.channel = kwargs.get('channel', 1)
        self.level = kwargs.get('level', 0)
        self.time_point = kwargs.get('time_point', 0)
        self.tiff_compression = kwargs.get('tiff_compression', 'deflate')
        self.show_well_matrix = kwargs.get('show_well_matrix', False)
        self.info = {}

    def read_experiment_info(self, experiment_file):
        if not os.path.isfile(experiment_file):
            self.log('Error: File not found!')
            return None

        self.info = {'experiment_file': experiment_file, 'images_file': None}

        self.log('Reading Info from CellReporterXpress experiment.db file')
        try:
            filepath = os.path.dirname(experiment_file)
            with sqlite3.connect(experiment_file) as conn:
                cursor = conn.cursor()
                self._fetch_time_series_info(cursor, filepath)
                self._fetch_experiment_metadata(cursor)
                self._fetch_well_info(cursor)
        except sqlite3.Error as e:
            self.log(f'Error Reading Info: {str(e)}')
            return None

        return self.info

    def _fetch_time_series_info(self, cursor, filepath):
        cursor.execute("SELECT DISTINCT TimeSeriesElementId FROM SourceImageBase")
        time_series_ids = [row[0] for row in cursor.fetchall()]

        if len(time_series_ids) == 1 and time_series_ids[0] == 0:
            self.time_point = 0
        elif self.time_point not in time_series_ids:
            raise ValueError(f"Invalid TimePoint: {self.time_point}. Available values: {time_series_ids}")
        self.info['images_file'] = os.path.join(filepath, f'images-{self.time_point}.db')

    def _fetch_experiment_metadata(self, cursor):
        cursor.execute('SELECT DateCreated, Creator, Name FROM ExperimentBase')
        info = cursor.fetchone()
        dt = self.convert_dotnet_ticks_to_datetime(int(info[0]))
        self.info.update({'name': info[2], 'creator': info[1], 'dt': dt})

    def _fetch_well_info(self, cursor):
        cursor.execute('SELECT SensorSizeYPixels, SensorSizeXPixels, Objective, PixelSizeUm, SensorBitness, SitesX, SitesY FROM AcquisitionExp, AutomaticZonesParametersExp')
        image_info = cursor.fetchone()
        cursor.execute('SELECT Emission, Excitation, Dye, channelNumber, ColorName FROM ImagechannelExp')
        channel_info = cursor.fetchall()

        self.info['well_info'] = self.get_well_info_dict(image_info, channel_info)

        cursor.execute('SELECT Name, ZoneIndex FROM Well WHERE HasImages = 1')
        wells = cursor.fetchall()
        self.info['numwells'] = len(wells)
        self.info['wells'] = {well[0]: well[1] for well in wells}

    def _read_well_info(self, well_id):
        well_ids = self.info.get('wells', {})

        if well_id not in well_ids:
            self.log('Error: Well not found!')

        zone_index = well_ids[well_id]
        with sqlite3.connect(self.info['experiment_file']) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT CoordX, CoordY, SizeX, SizeY, BitsPerPixel, ImageIndex, channelId
                FROM SourceImageBase
                WHERE ZoneIndex = ? AND level = ? AND TimeSeriesElementId = ?
                ORDER BY CoordX ASC, CoordY ASC
            ''', (zone_index, self.level, self.time_point))
            well_info = cursor.fetchall()

        # filter channel
        well_info = [info for info in well_info if info[6] == self.channel - 1]
        if not well_info:
            self.log(f'Error: No data found for well {well_id}')
        return well_info

    def _assemble_image_data(self, well_info):
        well_info = np.asarray(well_info)
        xmax = well_info[well_info[:, 1] == 0, 2].sum()
        ymax = well_info[well_info[:, 0] == 0, 3].sum()
        imdata = np.zeros((ymax, xmax), dtype=np.uint16)

        with open(self.info['images_file'], 'rb') as fid:
            for info in well_info:
                fid.seek(info[5])
                sub_image_data = np.fromfile(fid, dtype=np.uint16, count=info[2] * info[3])
                sub_image_data = sub_image_data.reshape((info[3], info[2]))
                imdata[info[1]:info[1] + info[3], info[0]:info[0] + info[2]] = sub_image_data

        return imdata

    def _extract_tile(self, imdata, tile_id):
        well_info = self.info['well_info']
        tilex = well_info['tilex']
        tiley = well_info['tiley']
        xs = well_info['xs']
        ys = well_info['ys']

        if isinstance(tile_id, str) and tile_id.lower() == 'all':
            tiles = []
            for ty in range(tiley):
                for tx in range(tilex):
                    x_start = tx * xs
                    y_start = ty * ys
                    tiles.append(imdata[y_start:y_start + ys, x_start:x_start + xs])
            return tiles
        elif isinstance(tile_id, int) and 1 <= tile_id <= tilex * tiley:
            tx = (tile_id - 1) % tilex
            ty = (tile_id - 1) // tilex
            x_start = tx * xs
            y_start = ty * ys
            return imdata[y_start:y_start + ys, x_start:x_start + xs]
        else:
            self.log(f'Error: Invalid tile {tile_id}')
            return None

    def extract_data(self, base_filename, well_id, tile_id=None):
        filepath, filename = os.path.split(base_filename)
        filetitle, ext = os.path.splitext(filename)

        filename = os.path.join(filepath, f"{filetitle}_ch{self.channel}_{self.add_leading_zero(well_id)}")
        well_info = self._read_well_info(well_id)
        imdata = self._assemble_image_data(well_info)
        if tile_id is not None:
            imdata = self._extract_tile(imdata, tile_id)
            filename += f"_{self.add_leading_zero(tile_id)}"
        if self.level > 0:
            filename += f"_level{self.level}"
        filename += ext

        if ext == '.tif':
            with tifffile.TiffWriter(filename, bigtiff=False) as tif:
                tif.write(imdata, compression=self.tiff_compression.lower())
        elif ext == '.png':
            Image.fromarray(imdata).save(filename)

        self.log(f"Image saved as {filename}")

    def log(self, text):
        if self.verbose:
            print(text)

    @staticmethod
    def add_leading_zero(input_string):
        output = str(input_string)
        while len(output) < 2:
            return '0' + output
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
        TICKS_AT_EPOCH = 621355968000000000
        TICKS_PER_SECOND = 10000000
        ticks_since_epoch = net_ticks - TICKS_AT_EPOCH
        seconds_since_epoch = ticks_since_epoch // TICKS_PER_SECOND
        microseconds_remainder = (ticks_since_epoch % TICKS_PER_SECOND) // 10
        return datetime(1970, 1, 1) + timedelta(seconds=seconds_since_epoch, microseconds=microseconds_remainder)

    @staticmethod
    def get_well_info_dict(image_info, channel_info):
        well_info = {
            'channels': len(channel_info),
            'tilex': image_info[5],
            'tiley': image_info[6],
            'tiles': image_info[5] * image_info[6],
            'bits': image_info[4],
            'xs': image_info[0],
            'ys': image_info[0],
            'xres': image_info[3],
            'yres': image_info[3],
            'objective': image_info[2]
        }
        return well_info
