# based on https://github.com/Cellular-Imaging-Amsterdam-UMC/crxReader-Python
# which is based on https://github.com/Cellular-Imaging-Amsterdam-UMC/crxReader
# Screen Plate Well (SPW) - High Content Screening (HCS) https://ome-model.readthedocs.io/en/stable/developers/screen-plate-well.html

from datetime import datetime, timedelta
import logging
import numpy as np
import os
import sqlite3

from src.ImageSource import ImageSource
from src.util import split_well_name


class ImageDbSource(ImageSource):
    def __init__(self, uri, metadata={}):
        super().__init__(uri, metadata)
        self.db = DBReader(self.uri)
        self.data = None

    def read_experiment_info(self):
        logging.info('Reading Info from CellReporterXpress experiment.db file')
        self._get_time_series_info()
        self._get_experiment_metadata()
        self._get_well_info()
        self._get_image_info()
        return self.metadata

    def _get_time_series_info(self):
        time_series_ids = sorted(self.db.fetch_all("SELECT DISTINCT TimeSeriesElementId FROM SourceImageBase", return_dicts=False))
        self.metadata['time_points'] = time_series_ids

        level_ids = sorted(self.db.fetch_all("SELECT DISTINCT level FROM SourceImageBase", return_dicts=False))
        self.metadata['levels'] = level_ids

        image_files = {time_series_id: os.path.join(os.path.dirname(self.uri), f'images-{time_series_id}.db')
                       for time_series_id in time_series_ids}
        self.metadata['image_files'] = image_files

    def _get_experiment_metadata(self):
        creation_info = self.db.fetch_all('SELECT DateCreated, Creator, Name FROM ExperimentBase')[0]
        creation_info['DateCreated'] = self.convert_dotnet_ticks_to_datetime(creation_info['DateCreated'])
        self.metadata.update(creation_info)

        acquisitions = self.db.fetch_all('SELECT Name, Description, DateCreated, DateModified FROM AcquisitionExp')
        for acquisition in acquisitions:
            acquisition['DateCreated'] = self.convert_dotnet_ticks_to_datetime(acquisition['DateCreated'])
            acquisition['DateModified'] = self.convert_dotnet_ticks_to_datetime(acquisition['DateModified'])
        self.metadata['acquisitions'] = acquisitions

    def _get_well_info(self):
        well_info = self.db.fetch_all('''
            SELECT SensorSizeYPixels, SensorSizeXPixels, Objective, PixelSizeUm, SensorBitness, SitesX, SitesY
            FROM AcquisitionExp, AutomaticZonesParametersExp
        ''')[0]
        self.metadata['well_info'] = well_info

        channel_infos = self.db.fetch_all('SELECT Emission, Excitation, Dye, ChannelNumber, Color FROM ImagechannelExp')
        for channel_info in channel_infos:
            channel_info['Color'] = channel_info['Color'][1:]   # remove leading '#'
        self.metadata['channels'] = channel_infos

        wells = self.db.fetch_all('SELECT DISTINCT Name FROM Well')
        zone_names = [well['Name'] for well in wells]
        rows = set()
        cols = set()
        for zone_name in zone_names:
            row, col = split_well_name(zone_name)
            rows.add(row)
            cols.add(col)
        well_info['rows'] = sorted(list(rows))
        well_info['columns'] = sorted(list(cols), key=lambda x: int(x))
        num_fields = well_info['SitesX'] * well_info['SitesY']
        well_info['fields'] = [f'{field_index}' for field_index in range(num_fields)]
        well_info['num_fields'] = num_fields

        image_wells = self.db.fetch_all('SELECT Name, ZoneIndex FROM Well WHERE HasImages = 1')
        self.metadata['num_wells'] = len(image_wells)
        self.metadata['wells'] = dict(sorted({well['Name']: well['ZoneIndex'] for well in image_wells}.items(),
                                             key=lambda x: split_well_name(x[0], col_as_int=True)))

    def _get_image_info(self):
        bits_per_pixel = self.db.fetch_all("SELECT DISTINCT BitsPerPixel FROM SourceImageBase", return_dicts=False)[0]
        self.metadata['bits_per_pixel'] = bits_per_pixel
        bits_per_pixel = int(np.ceil(bits_per_pixel / 8)) * 8
        self.metadata['dtype'] = np.dtype(f'uint{bits_per_pixel}').type

    def _read_well_info(self, well_id, channel=None, time_point=0, level=0):
        well_id = self.remove_leading_zeros(well_id)
        well_ids = self.metadata.get('wells', {})

        if well_id not in well_ids:
            raise ValueError(f"Invalid Well: {well_id}. Available values: {well_ids}")

        zone_index = well_ids[well_id]
        well_info = self.db.fetch_all('''
            SELECT CoordX, CoordY, SizeX, SizeY, BitsPerPixel, ImageIndex, channelId
            FROM SourceImageBase
            WHERE ZoneIndex = ? AND level = ? AND TimeSeriesElementId = ?
            ORDER BY CoordX ASC, CoordY ASC
        ''', (zone_index, level, time_point))

        # filter channel
        if channel is not None:
            well_info = [info for info in well_info if info['ChannelId'] == channel]
        if not well_info:
            logging.info(f'Error: No data found for well {well_id}')
        return well_info

    def _assemble_image_data(self, well_info, time_point=0):
        dtype = self.metadata['dtype']
        well_info = np.asarray(well_info)
        xmax = np.max([info['CoordX'] + info['SizeX'] for info in well_info])
        ymax = np.max([info['CoordY'] + info['SizeY'] for info in well_info])
        nchannels = len(set([info['ChannelId'] for info in well_info]))
        data = np.zeros((nchannels, ymax, xmax), dtype=dtype)

        image_file = self.metadata['image_files'][time_point]
        with open(image_file, 'rb') as fid:
            for info in well_info:
                fid.seek(info['ImageIndex'])
                coordx, coordy = info['CoordX'], info['CoordY']
                sizex, sizey = info['SizeX'], info['SizeY']
                channeli = info['ChannelId']
                subtile_data = np.fromfile(fid, dtype=dtype, count=sizey * sizex)
                subtile_data = subtile_data.reshape((sizey, sizex))
                data[channeli, coordy:coordy + sizey, coordx:coordx + sizex] = subtile_data

        self.data = data

    def _extract_field(self, field_id=None):
        well_info = self.metadata['well_info']
        fieldx = well_info['SitesX']
        fieldy = well_info['SitesY']
        numfields = well_info['num_fields']
        sizex = well_info['SensorSizeXPixels']
        sizey = well_info['SensorSizeYPixels']

        if field_id is None:
            # Return full image data
            return self.data
        if field_id < 0:
            # Return list of all fields
            fields = []
            for yi in range(fieldy):
                for xi in range(fieldx):
                    startx = xi * sizex
                    starty = yi * sizey
                    fields.append(self.data[:, starty:starty + sizey, startx:startx + sizex])
            return fields
        elif 0 <= field_id < numfields:
            # Return specific field
            xi = field_id % fieldx
            yi = field_id // fieldx
            startx = xi * sizex
            starty = yi * sizey
            return self.data[:, starty:starty + sizey, startx:startx + sizex]
        else:
            raise ValueError(f"Invalid field: {field_id}")

    def get_field_image(self, well_id, field_id):
        well_info = self._read_well_info(well_id)
        if self.data is None:
            self._assemble_image_data(well_info)
        return self._extract_field(field_id).squeeze()

    @staticmethod
    def add_leading_zero(input_string, num_digits=2):
        output = str(input_string)
        while len(output) < num_digits:
            output = '0' + output
        return output

    @staticmethod
    def remove_leading_zeros(well_name):
        row, col = split_well_name(well_name, remove_leading_zeros=True)
        return f'{row}{col}'

    @staticmethod
    def convert_dotnet_ticks_to_datetime(net_ticks):
        return datetime(1, 1, 1) + timedelta(microseconds=net_ticks // 10)

    def display_well_matrix(self):
        """
        Displays a matrix of wells used for each timepoint with well names.
        """

        # Fetch all TimeSeriesElementId values
        time_series_ids = self.db.fetch_all("SELECT DISTINCT TimeSeriesElementId FROM SourceImageBase", return_dicts=False)

        # Fetch well data
        wells = self.db.fetch_all("SELECT Name, ZoneIndex FROM Well WHERE HasImages = 1")

        well_names = [self.add_leading_zero(well['Name']) for well in wells]
        well_matrix = []
        for timepoint in time_series_ids:
            wells_at_timepoint = self.db.fetch_all("""
                SELECT DISTINCT Well.Name FROM SourceImageBase
                JOIN Well ON SourceImageBase.ZoneIndex = Well.ZoneIndex
                WHERE TimeSeriesElementId = ?
            """, (timepoint,), return_dicts=False)

            row = [well if well in wells_at_timepoint else '' for well in well_names]
            well_matrix.append(row)

        print("Timepoint x Well Matrix:")
        for idx, row in enumerate(well_matrix):
            print(f"Timepoint {time_series_ids[idx]}: {row}")

    def close(self):
        self.db.close()


class DBReader:
    def __init__(self, db_file):
        self.conn = sqlite3.connect(db_file)
        self.conn.row_factory = DBReader.dict_factory

    @staticmethod
    def dict_factory(cursor, row):
        dct = {}
        for index, column in enumerate(cursor.description):
            dct[column[0]] = row[index]
        return dct

    def fetch_all(self, query, params=(), return_dicts=True):
        cursor = self.conn.cursor()
        cursor.execute(query, params)
        dct = cursor.fetchall()
        if return_dicts:
            values = dct
        else:
            values = [list(row.values())[0] for row in dct]
        return values

    def close(self):
        self.conn.close()
