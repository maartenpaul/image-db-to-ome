import numpy as np
from tifffile import TiffFile, xml2dict

from ImageSource import ImageSource
from util import convert_to_um


class OmeTiffSource(ImageSource):
    def __init__(self, uri, metadata={}):
        super().__init__(uri, metadata)
        self.tiff = TiffFile(uri)

    def init_metadata(self):
        if self.tiff.is_ome:
            self.metadata = xml2dict(self.tiff.ome_metadata)
            if 'OME' in self.metadata:
                self.metadata = self.metadata['OME']
        #self.dim_order = ''.join(reversed(self.metadata['Image']['Pixels']['DimensionOrder'].lower()))
        self.dim_order = 'tczyx'
        return self.metadata

    def is_screen(self):
        return 'Plate' in self.metadata

    def get_data(self, well_id=None, field_id=None):
        data = self.tiff.asarray()
        while data.ndim < len(self.dim_order):
            data = np.expand_dims(data, 0)
        return data

    def get_name(self):
        if self.is_screen():
            base_node = self.metadata['Plate']
        else:
            base_node = self.metadata['Image']
        return base_node.get('Name')

    def get_dim_order(self):
        return self.dim_order

    def get_dtype(self):
        return np.dtype(self.metadata['Image']['Pixels']['Type'])

    def get_pixel_size_um(self):
        pixel_size = {}
        pixels = self.metadata['Image']['Pixels']
        if 'PositionX' in pixels:
            pixel_size['x'] = convert_to_um(float(pixels.get('PhysicalSizeX')), pixels.get('PhysicalSizeXUnit'))
        if 'PositionY' in pixels:
            pixel_size['y'] = convert_to_um(float(pixels.get('PhysicalSizeY')), pixels.get('PhysicalSizeYUnit'))
        if 'PositionZ' in pixels:
            pixel_size['z'] = convert_to_um(float(pixels.get('PhysicalSizeZ')), pixels.get('PhysicalSizeZUnit'))
        return pixel_size

    def get_position_um(self, well_id=None):
        position = {}
        plane = self.metadata['Image']['Pixels'].get('Plane')
        if plane:
            if 'PositionX' in plane:
                position['x'] = convert_to_um(float(plane.get('PositionX')), plane.get('PositionXUnit'))
            if 'PositionY' in plane:
                position['y'] = convert_to_um(float(plane.get('PositionY')), plane.get('PositionYUnit'))
            if 'PositionZ' in plane:
                position['z'] = convert_to_um(float(plane.get('PositionZ')), plane.get('PositionZUnit'))
        return position

    def get_channels(self):
        channels = []
        for channel0 in self.metadata['Image']['Pixels'].get('Channel'):
            channel = {'label': channel0.get('Name'),
                       'color': channel0.get('Color')}
            if channel['label'] is None:
                channel['label'] = ''
            channels.append(channel)
        return channels

    def get_nchannels(self):
        nchannels = 1
        dim_order = self.get_dim_order()
        if 'c' in dim_order:
            c_index = dim_order.index('c')
            nchannels = self.tiff.pages.first.shape[c_index]
        return nchannels

    def get_rows(self):
        raise NotImplementedError("The 'get_rows' method must be implemented by subclasses.")

    def get_columns(self):
        raise NotImplementedError("The 'get_columns' method must be implemented by subclasses.")

    def get_wells(self):
        raise NotImplementedError("The 'get_wells' method must be implemented by subclasses.")

    def get_time_points(self):
        raise NotImplementedError("The 'get_time_points' method must be implemented by subclasses.")

    def get_fields(self):
        raise NotImplementedError("The 'get_fields' method must be implemented by subclasses.")

    def get_acquisitions(self):
        raise NotImplementedError("The 'get_acquisitions' method must be implemented by subclasses.")
