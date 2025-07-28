# based on https://github.com/Cellular-Imaging-Amsterdam-UMC/crxReader-Python
# which is based on https://github.com/Cellular-Imaging-Amsterdam-UMC/crxReader
# Screen Plate Well (SPW) - High Content Screening (HCS) https://ome-model.readthedocs.io/en/stable/developers/screen-plate-well.html

from datetime import datetime, timedelta
import numpy as np
from ome_zarr.io import parse_url
from ome_zarr.writer import write_image, write_plate_metadata, write_well_metadata
from ome_zarr_util import create_axes_metadata, create_channel_metadata
import os
import re
import sqlite3
import tifffile
import zarr


class CRXReader:
    def __init__(self, experiment_file, channel=None, level=0, time_point=0, dype=np.uint16, verbose=True):
        self.experiment_file = experiment_file

        if not os.path.isfile(self.experiment_file):
            raise ValueError('Experimenter file not found!')

        self.db = DBReader(self.experiment_file)
        self.verbose = verbose
        self.channel = channel
        self.level = level
        self.time_point = time_point
        self.dtype = dype
        self.info = None
        self.imdata = None

    def read_experiment_info(self):
        self.info = {'experiment_file': self.experiment_file, 'image_files': {}}
        self.log('Reading Info from CellReporterXpress experiment.db file')
        self._fetch_time_series_info()
        self._fetch_experiment_metadata()
        self._fetch_well_info()
        return self.info

    def _fetch_time_series_info(self):
        time_series_ids = sorted(self.db.fetch_all("SELECT DISTINCT TimeSeriesElementId FROM SourceImageBase", return_dicts=False))
        self.info['time_points'] = time_series_ids

        level_ids = sorted(self.db.fetch_all("SELECT DISTINCT level FROM SourceImageBase", return_dicts=False))
        self.info['levels'] = level_ids

        image_files = {time_series_id: os.path.join(os.path.dirname(self.experiment_file), f'images-{time_series_id}.db')
                       for time_series_id in time_series_ids}
        self.info['image_files'] = image_files

    def _fetch_experiment_metadata(self):
        info = self.db.fetch_all('SELECT DateCreated, Creator, Name FROM ExperimentBase')[0]
        info['DateCreated'] = self.convert_dotnet_ticks_to_datetime(info['DateCreated'])
        self.info.update(info)

        acquisitions = self.db.fetch_all('SELECT Name, Description, DateCreated, DateModified FROM AcquisitionExp')
        for acquisition in acquisitions:
            acquisition['DateCreated'] = self.convert_dotnet_ticks_to_datetime(acquisition['DateCreated'])
            acquisition['DateModified'] = self.convert_dotnet_ticks_to_datetime(acquisition['DateModified'])
        self.info['acquisitions'] = acquisitions

    def _fetch_well_info(self):
        well_info = self.db.fetch_all('''SELECT SensorSizeYPixels, SensorSizeXPixels, Objective, PixelSizeUm, SensorBitness, SitesX, SitesY
                                         FROM AcquisitionExp, AutomaticZonesParametersExp''')[0]
        self.info['well_info'] = well_info

        channel_infos = self.db.fetch_all('SELECT Emission, Excitation, Dye, ChannelNumber, Color FROM ImagechannelExp')
        for channel_info in channel_infos:
            channel_info['Color'] = channel_info['Color'][1:]   # remove leading '#'
        self.info['well_info']['channels'] = channel_infos

        wells = self.db.fetch_all('SELECT DISTINCT Name FROM Well')
        zone_names = [well['Name'] for well in wells]
        rows = set()
        cols = set()
        for zone_name in zone_names:
            row, col = self.split_well_name(zone_name)
            rows.add(row)
            cols.add(col)
        well_info['rows'] = sorted(list(rows))
        well_info['columns'] = sorted(list(cols), key=lambda x: int(x))

        image_wells = self.db.fetch_all('SELECT Name, ZoneIndex FROM Well WHERE HasImages = 1')
        self.info['numwells'] = len(image_wells)
        self.info['wells'] = dict(sorted({well['Name']: well['ZoneIndex'] for well in image_wells}.items(),
                                         key=lambda x: self.split_well_name(x[0], col_as_int=True)))

    def _read_well_info(self, well_id):
        well_id = self.remove_leading_zeros(well_id)
        well_ids = self.info.get('wells', {})

        if well_id not in well_ids:
            raise ValueError(f"Invalid Well: {well_id}. Available values: {well_ids}")

        zone_index = well_ids[well_id]
        well_info = self.db.fetch_all('''
            SELECT CoordX, CoordY, SizeX, SizeY, BitsPerPixel, ImageIndex, channelId
            FROM SourceImageBase
            WHERE ZoneIndex = ? AND level = ? AND TimeSeriesElementId = ?
            ORDER BY CoordX ASC, CoordY ASC
        ''', (zone_index, self.level, self.time_point))

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

        image_file = self.info['image_files'][self.time_point]
        with open(image_file, 'rb') as fid:
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
        if ext.lower() in ['.tif', '.tiff']:
            with tifffile.TiffWriter(filename) as tif:
                tif.write(imdata, compression=tiff_compression, dtype=self.dtype)

        self.log(f"Image saved as {filename}")

    def _extract_well_to_zarr(self, zarr_group, well_id, tile_id=None, ome_format=None):
        well_info = self._read_well_info(well_id)
        if self.imdata is None:
            self._assemble_image_data(well_info)
        imdata = self._extract_tile(tile_id).squeeze()
        nchannels = max(len(self.info['well_info']['channels']), 1)
        dim_order = 'yx'
        if nchannels > 1:
            dim_order = 'c' + dim_order
        axes = create_axes_metadata(dim_order)
        write_image(image=imdata, group=zarr_group, axes=axes, fmt=ome_format)

    def export_to_zarr(self, filename=None, zarr_version=2, ome_version='0.4'):
        # https://ome-zarr.readthedocs.io/en/stable/python.html#writing-hcs-datasets-to-ome-ngff
        if not self.info:
            self.read_experiment_info()

        if filename is None:
            filename = os.path.basename(os.path.splitext(self.experiment_file)[0])
            if filename.lower() == 'experiment':
                filename = os.path.split(os.path.dirname(self.experiment_file))[-1]
            filename += '.zarr'

        if ome_version == '0.5':
            from ome_zarr.format import FormatV05
            ome_format = FormatV05()
        else:
            from ome_zarr.format import FormatV04
            ome_format = FormatV04()

        zarr_root = zarr.open_group(store=parse_url(filename, mode="w").store, mode="w", zarr_version=zarr_version)

        row_names = self.info['well_info']['rows']
        col_names = self.info['well_info']['columns']
        well_paths = ['/'.join(self.split_well_name(info)) for info in self.info['wells']]
        field_paths = ['0']

        acquisitions = []
        for index, acq in enumerate(self.info.get('acquisitions', [])):
            acquisitions.append({
                'id': index,
                'name': acq['Name'],
                'description': acq['Description'],
                'date_created': acq['DateCreated'].isoformat(),
                'date_modified': acq['DateModified'].isoformat()
            })

        write_plate_metadata(zarr_root, row_names, col_names, well_paths, acquisitions=acquisitions)
        for well, zone_id in self.info['wells'].items():
            row, col = self.split_well_name(well)
            row_group = zarr_root.require_group(row)
            well_group = row_group.require_group(col)
            write_well_metadata(well_group, field_paths)
            for fi, field in enumerate(field_paths):
                image_group = well_group.require_group(str(field))
                self._extract_well_to_zarr(image_group, well, ome_format=ome_format)

        #channels = self.info['well_info']['channels']
        #nchannels = max(len(channels), 1)
        #zarr_root.attrs['omero'] = create_channel_metadata(imdata, channels, nchannels, ome_version)

        self.log(f"Exported as {filename}")

    def log(self, text):
        if self.verbose:
            print(text)

    @staticmethod
    def split_well_name(well_name, remove_leading_zeros=True, col_as_int=False):
        matches = re.findall(r'(\D+)(\d+)', well_name)
        if len(matches) > 0:
            row, col = matches[0]
            if col_as_int or remove_leading_zeros:
                try:
                    col = int(col)
                except ValueError:
                    pass
            if not col_as_int:
                col = str(col)
            return row, col
        else:
            raise ValueError(f"Invalid well name format: {well_name}. Expected format like 'A1', 'B2', etc.")

    @staticmethod
    def add_leading_zero(input_string, num_digits=2):
        output = str(input_string)
        while len(output) < num_digits:
            output = '0' + output
        return output

    @staticmethod
    def remove_leading_zeros(well_name):
        row, col = CRXReader.split_well_name(well_name, remove_leading_zeros=True)
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
