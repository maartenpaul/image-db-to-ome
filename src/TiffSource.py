from enum import Enum
import numpy as np
import os
from tifffile import TiffFile, xml2dict

from ImageSource import ImageSource
from util import convert_to_um, ensure_list


class TiffSource(ImageSource):
    def __init__(self, uri, metadata={}):
        super().__init__(uri, metadata)
        self.tiff = TiffFile(uri)

    def init_metadata(self):
        self.is_ome = self.tiff.is_ome
        self.is_imagej = self.tiff.is_imagej
        if self.is_ome:
            self.metadata = xml2dict(self.tiff.ome_metadata)
            if 'OME' in self.metadata:
                self.metadata = self.metadata['OME']
            self.dim_order = ''.join(reversed(self.metadata['Image']['Pixels']['DimensionOrder'].lower()))
        else:
            self.metadata = tags_to_dict(self.tiff.pages.first.tags)
            if self.tiff.series:
                page = self.tiff.series[0]
            else:
                page = self.tiff.pages.first
            self.dim_order = page.axes.lower().replace('s', 'c').replace('r', '')
        if self.is_imagej:
            self.imagej_metadata = self.tiff.imagej_metadata
        return self.metadata

    def is_screen(self):
        return 'Plate' in self.metadata

    def get_data(self, well_id=None, field_id=None):
        data = self.tiff.asarray()
        while data.ndim < len(self.dim_order):
            data = np.expand_dims(data, 0)
        return data

    def get_name(self):
        if self.is_ome:
            if self.is_screen():
                name = self.metadata['Plate'].get('Name')
            else:
                name = self.metadata['Image'].get('Name')
        else:
            name = os.path.splitext(self.tiff.filename)[0]
        return name

    def get_dim_order(self):
        return self.dim_order

    def get_dtype(self):
        if self.is_ome:
            dtype = np.dtype(self.metadata['Image']['Pixels']['Type'])
        else:
            dtype = self.tiff.pages.first.dtype
        return dtype

    def get_pixel_size_um(self):
        pixel_size = {'x': 1, 'y': 1}
        if self.is_ome:
            pixels = self.metadata['Image']['Pixels']
            if 'PositionX' in pixels:
                pixel_size['x'] = convert_to_um(float(pixels.get('PhysicalSizeX')), pixels.get('PhysicalSizeXUnit'))
            if 'PositionY' in pixels:
                pixel_size['y'] = convert_to_um(float(pixels.get('PhysicalSizeY')), pixels.get('PhysicalSizeYUnit'))
            if 'PositionZ' in pixels:
                pixel_size['z'] = convert_to_um(float(pixels.get('PhysicalSizeZ')), pixels.get('PhysicalSizeZUnit'))
        else:
            if self.is_imagej:
                pixel_size_unit = self.imagej_metadata.get('unit', '').encode().decode('unicode_escape')
                if 'scales' in self.imagej_metadata:
                    for dim, scale in zip(['x', 'y'], self.imagej_metadata['scales'].split(',')):
                        scale = scale.strip()
                        if scale != '':
                            pixel_size[dim] = convert_to_um(float(scale), pixel_size_unit)
                if 'spacing' in self.imagej_metadata:
                    pixel_size['z'] = convert_to_um(self.imagej_metadata['spacing'], pixel_size_unit)
            res_unit = self.metadata.get('ResolutionUnit', '')
            if isinstance(res_unit, Enum):
                res_unit = res_unit.name
            res_unit = res_unit.lower()
            if res_unit == 'none':
                res_unit = ''
            if 'x' not in pixel_size:
                res0 = convert_rational_value(self.metadata.get('XResolution'))
                if res0 is not None and res0 != 0:
                    pixel_size['x'] = convert_to_um(1 / res0, res_unit)
            if 'y' not in pixel_size:
                res0 = convert_rational_value(self.metadata.get('YResolution'))
                if res0 is not None and res0 != 0:
                    pixel_size['y'] = convert_to_um(1 / res0, res_unit)
        return pixel_size

    def get_position_um(self, well_id=None):
        position = {}
        if self.is_ome:
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
        if self.is_ome:
            for channel0 in ensure_list(self.metadata['Image']['Pixels'].get('Channel')):
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

    def close(self):
        self.tiff.close()


def tags_to_dict(tags):
    tag_dict = {}
    for tag in tags.values():
        tag_dict[tag.name] = tag.value
    return tag_dict


def convert_rational_value(value):
    if value is not None and isinstance(value, tuple):
        if value[0] == value[1]:
            value = value[0]
        else:
            value = value[0] / value[1]
    return value
