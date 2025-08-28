import numpy as np
import re
from pathlib import Path
import tifffile
from datetime import datetime

from src.ImageSource import ImageSource
from src.util import strip_leading_zeros


class IncucyteSource(ImageSource):
    """
    ImageSource implementation for Incucyte data
    
    Handles the specific directory structure:
    EssenFiles/ScanData/YYMM/DD/HHMM/XXXX/*.tif
    
    Filenames follow pattern: WELL-FIELD-CHANNEL.tif
    e.g., A1-1-C1.tif, B2-1-Ph.tif
    """
    
    def __init__(self, uri, metadata={}):
        super().__init__(uri, metadata)
        self.base_path = Path(self.uri)
        self.scan_data_path = self.base_path / "EssenFiles" / "ScanData"
        self.metadata['dim_order'] = 'tczyx'
        self._file_cache = {}
        
    def init_metadata(self):
        """Initialize all metadata from Incucyte structure"""
        self._get_experiment_metadata()
        self._scan_timepoints()
        self._get_well_info()
        self._get_channel_info()
        self._get_image_info()
        return self.metadata
    
    def _get_experiment_metadata(self):
        """Extract experiment metadata from folder structure"""
        # Use parent folder name as experiment name
        experiment_name = self.base_path.name
        self.metadata.update({
            'Name': experiment_name,
            'Creator': 'Incucyte',
            'DateCreated': datetime.now(),  # Could be improved by reading folder creation date
        })
        
    def _scan_timepoints(self):
        """Scan the Incucyte directory structure for timepoints"""
        timepoints = []
        wells = set()
        fields = set()
        channels = set()
        
        print(f"Scanning directory: {self.scan_data_path}")
        
        if not self.scan_data_path.exists():
            raise ValueError(f"Scan data path not found: {self.scan_data_path}")
        
        # Navigate through year/month directories (YYMM)
        for year_month in self.scan_data_path.iterdir():
            if not year_month.is_dir():
                continue
            # Navigate through day directories (DD)  
            for day in year_month.iterdir():
                if not day.is_dir():
                    continue
                # Navigate through time directories (HHMM)
                for time_dir in day.iterdir():
                    if not time_dir.is_dir():
                        continue
                    # Navigate through fixed ID directories (XXXX)
                    for fixed_id in time_dir.iterdir():
                        if not fixed_id.is_dir():
                            continue
                        
                        timepoint_path = fixed_id
                        timestamp = f"{year_month.name}_{day.name}_{time_dir.name}"
                        
                        # Parse timestamp to datetime
                        try:
                            # YYMM_DD_HHMM format
                            dt = datetime.strptime(timestamp, "%y%m_%d_%H%M")
                            # Assume 2000s for year
                            if dt.year < 2000:
                                dt = dt.replace(year=dt.year + 2000)
                        except ValueError:
                            dt = None
                        
                        timepoint_info = {
                            'path': timepoint_path,
                            'timestamp': timestamp,
                            'datetime': dt,
                            'index': len(timepoints)
                        }
                        timepoints.append(timepoint_info)
                        
                        # Scan TIFF files in this timepoint
                        tiff_files = list(timepoint_path.glob("*.tif"))
                        
                        for file in tiff_files:
                            well, field, channel = self._parse_filename(file.name)
                            if well and field is not None and channel:
                                wells.add(well)
                                fields.add(field)
                                channels.add(channel)
        
        # Sort timepoints by datetime if available, otherwise by timestamp
        timepoints.sort(key=lambda x: x['datetime'] if x['datetime'] else x['timestamp'])
        
        # Update indices after sorting
        for i, tp in enumerate(timepoints):
            tp['index'] = i
        
        self.metadata['timepoints'] = timepoints
        self.metadata['time_points'] = [tp['index'] for tp in timepoints]
        self.metadata['wells_raw'] = sorted(wells)
        self.metadata['fields_raw'] = sorted(fields)
        self.metadata['channels_raw'] = sorted(channels)
        
        print(f"Found: {len(timepoints)} timepoints, {len(wells)} wells, {len(fields)} fields, {len(channels)} channels")
        
    def _parse_filename(self, filename):
        """
        Parse Incucyte filename format: WELL-FIELD-CHANNEL.tif
        Examples: A1-1-C1.tif, B2-1-Ph.tif
        Returns: (well, field, channel)
        """
        pattern = r"([A-Z]\d+)-(\d+)-(.+)\.tif"
        match = re.match(pattern, filename)
        if match:
            well = match.group(1)
            field = int(match.group(2))-1 # TODO implement this properly as now should start at field 0
            channel = match.group(3)
            return well, field, channel
        return None, None, None
    
    def _get_well_info(self):
        """Process well information and determine plate layout"""
        wells_raw = self.metadata['wells_raw']
        
        if not wells_raw:
            raise ValueError("No wells found in data")
        
        # Parse well positions
        rows = set()
        cols = set()
        wells_dict = {}
        
        for well_name in wells_raw:
            row_letter = well_name[0]
            col_number = int(well_name[1:])
            
            rows.add(row_letter)
            cols.add(col_number)
            
            wells_dict[well_name] = {
                'Name': well_name,
                'row': ord(row_letter) - ord('A'),
                'column': col_number - 1,
                'ZoneIndex': len(wells_dict)  # Sequential index for compatibility
            }
        
        rows = sorted(rows)
        cols = sorted(cols)
        
        # Get image dimensions from first available image
        sample_image_info = self._get_sample_image_info()
        
        well_info = {
            'rows': rows,
            'columns': [str(c) for c in cols],
            'SensorSizeXPixels': sample_image_info['width'],
            'SensorSizeYPixels': sample_image_info['height'],
            'SitesX': 1,  # Incucyte typically has 1 site per field
            'SitesY': 1,
            'num_sites': len(self.metadata['fields_raw']),
            'fields': [str(f) for f in self.metadata['fields_raw']],
            'PixelSizeUm': 1.0,  # Default, could be extracted from metadata if available
            'SensorBitness': sample_image_info['bits'],
            'max_sizex_um': sample_image_info['width'] * 1.0,
            'max_sizey_um': sample_image_info['height'] * 1.0,
        }
        
        self.metadata['wells'] = wells_dict
        self.metadata['well_info'] = well_info

    def is_screen(self):
        return len(self.metadata['wells']) > 0
    
    def get_position_um(self, well_id=None):
        well = self.metadata['wells'][well_id]
        well_info = self.metadata['well_info']
        x = well.get('CoordX', 0) * well_info['max_sizex_um']
        y = well.get('CoordY', 0) * well_info['max_sizey_um']
        return {'x': x, 'y': y}
    
    def _get_sample_image_info(self):
        """Get image dimensions and bit depth from first available TIFF"""
        # Citation: pixel size extraction logic adapted from bioio-tifffile (https://github.com/bioimage-io/bioio-tifffile)
        _NAME_TO_MICRONS = {
            "pm": 1e-6,
            "picometer": 1e-6,
            "nm": 1e-3,
            "nanometer": 1e-3,
            "micron": 1,
            "µm": 1,
            "um": 1,
            "\\u00B5m": 1,
            tifffile.RESUNIT.NONE: 1,
            tifffile.RESUNIT.MICROMETER: 1,
            None: 1,
            "mm": 1e3,
            "millimeter": 1e3,
            tifffile.RESUNIT.MILLIMETER: 1e3,
            "cm": 1e4,
            "centimeter": 1e4,
            tifffile.RESUNIT.CENTIMETER: 1e4,
            "cal": 2.54 * 1e4,
            tifffile.RESUNIT.INCH: 2.54 * 1e4,
        }
        for timepoint in self.metadata['timepoints']:
            for tiff_file in timepoint['path'].glob("*.tif"):
                try:
                    with tifffile.TiffFile(str(tiff_file)) as tif:
                        page = tif.pages[0]
                        array = page.asarray()
                        # Try to get tags, raise error if not available
                        if not hasattr(tif.pages[0], "tags"):
                            raise RuntimeError("TIFF page does not have 'tags' attribute. Please check your tifffile version or file format.")
                        tags = tif.pages[0].tags
                        # Get resolution unit
                        unit = tags["ResolutionUnit"].value if "ResolutionUnit" in tags else None
                        scalar = _NAME_TO_MICRONS.get(unit, 1)
                        # Get X/Y resolution
                        npix_x, x_res_units = tags["XResolution"].value if "XResolution" in tags else (1, 1)
                        npix_y, y_res_units = tags["YResolution"].value if "YResolution" in tags else (1, 1)
                        # Calculate pixel size in microns
                        pixel_x = scalar * x_res_units / npix_x if npix_x else None
                        pixel_y = scalar * y_res_units / npix_y if npix_y else None
                        return {
                            'width': array.shape[1],
                            'height': array.shape[0],
                            'bits': array.dtype.itemsize * 8,
                            'dtype': array.dtype,
                            'pixel_x': pixel_x,
                            'pixel_y': pixel_y
                        }
                except Exception as e:
                    print(f"Could not read sample image {tiff_file}: {e}")
                    continue
        # Fallback defaults
        return {
            'width': 2048,
            'height': 2048,
            'bits': 16,
            'dtype': np.uint16,
            'pixel_x': 1.0,
            'pixel_y': 1.0
        }
    
    def _get_channel_info(self):
        """Process channel information"""
        channels_raw = self.metadata['channels_raw']
        channels = []
        
        channel_mapping = {
            'C1': {'label': 'Green', 'color': '00FF00'},
            'C2': {'label': 'Red', 'color': 'FF0000'},
            'Ph': {'label': 'Phase_Contrast', 'color': 'FFFFFF'},
            'P': {'label': 'Phase_Contrast', 'color': 'FFFFFF'},
        }
        
        for i, channel_code in enumerate(channels_raw):
            channel_info = channel_mapping.get(channel_code, {
                'label': channel_code,
                'color': 'FFFFFF'
            })
            
            channels.append({
                'ChannelNumber': i,
                'Dye': channel_info['label'],
                'Color': f"#{channel_info['color']}",
                'Emission': None,
                'Excitation': None,
                'code': channel_code
            })
        
        self.metadata['channels'] = channels
        self.metadata['num_channels'] = len(channels)
    
    def _get_image_info(self):
        """Get image-related metadata"""
        sample_info = self._get_sample_image_info()
        
        self.metadata['bits_per_pixel'] = sample_info['bits']
        self.metadata['dtype'] = sample_info['dtype']
        
        # Calculate approximate data size
        well_info = self.metadata['well_info']
        max_data_size = (
            well_info['SensorSizeXPixels'] * well_info['SensorSizeYPixels'] *
            len(self.metadata['wells']) * well_info['num_sites'] * 
            self.metadata['num_channels'] * len(self.metadata['time_points']) *
            (sample_info['bits'] // 8)
        )
        self.metadata['max_data_size'] = max_data_size
    
    def _load_image_data(self, well_id, field_id, channel_id, timepoint_id):
        """Load specific image data"""
        if (well_id, field_id, channel_id, timepoint_id) in self._file_cache:
            return self._file_cache[(well_id, field_id, channel_id, timepoint_id)]
        
        # Find the file for this combination
        timepoint_info = self.metadata['timepoints'][timepoint_id]
        channel_code = self.metadata['channels_raw'][channel_id]
        
        filename = f"{well_id}-{field_id+1}-{channel_code}.tif" #TODO fix this +1 hack
        file_path = timepoint_info['path'] / filename
        
        if not file_path.exists():
            # Print warning and return zeros if file doesn't exist
            print(f"WARNING: File not found: {file_path}")
            print(f"  Expected: Well={well_id}, Field={field_id}, Channel={channel_code}, Timepoint={timepoint_id}")
            sample_info = self._get_sample_image_info()
            data = np.zeros((sample_info['height'], sample_info['width']), dtype=sample_info['dtype'])
            self._file_cache[(well_id, field_id, channel_id, timepoint_id)] = data
            return data
        
        try:
            with tifffile.TiffFile(str(file_path)) as tif:
                # Get first page (full resolution for pyramid TIFFs)
                page = tif.pages[0] 
                data = page.asarray()
                self._file_cache[(well_id, field_id, channel_id, timepoint_id)] = data
                return data
        except Exception as e:
            print(f"ERROR: Failed to load {file_path}: {e}")
            print(f"  Details: Well={well_id}, Field={field_id}, Channel={channel_code}, Timepoint={timepoint_id}")
            sample_info = self._get_sample_image_info()
            data = np.zeros((sample_info['height'], sample_info['width']), dtype=sample_info['dtype'])
            self._file_cache[(well_id, field_id, channel_id, timepoint_id)] = data
            return data
    
    def get_data(self, well_id, field_id):
        """Get data for a specific well and field"""
        well_id = strip_leading_zeros(well_id)
        
        if well_id not in self.metadata['wells']:
            raise ValueError(f'Invalid Well: {well_id}. Available: {list(self.metadata["wells"].keys())}')
        
        field_id = int(field_id)
        if field_id not in self.metadata['fields_raw']:
            raise ValueError(f'Invalid Field: {field_id}. Available: {self.metadata["fields_raw"]}')
        
        # Build 5D array: (t, c, z, y, x)
        nt = len(self.metadata['time_points'])
        nc = self.metadata['num_channels'] 
        sample_info = self._get_sample_image_info()
        ny, nx = sample_info['height'], sample_info['width']
        nz = 1  # Incucyte is typically 2D
        
        data = np.zeros((nt, nc, nz, ny, nx), dtype=sample_info['dtype'])
        
        for t in range(nt):
            for c in range(nc):
                image_data = self._load_image_data(well_id, field_id, c, t)
                # Handle different image shapes
                if len(image_data.shape) == 2:
                    data[t, c, 0, :, :] = image_data
                elif len(image_data.shape) == 3 and image_data.shape[0] == 1:
                    data[t, c, 0, :, :] = image_data[0]
                else:
                    # Take first z-plane if 3D
                    data[t, c, 0, :, :] = image_data[..., 0] if len(image_data.shape) > 2 else image_data
        
        return data
    
    # ImageSource interface methods
    def get_name(self):
        return self.metadata.get('Name', 'Incucyte_Experiment')
    
    def get_rows(self):
        return self.metadata['well_info']['rows']
    
    def get_columns(self):
        return self.metadata['well_info']['columns']
    
    def get_wells(self):
        return list(self.metadata['wells'].keys())
    
    def get_time_points(self):
        return self.metadata['time_points']
    
    def get_fields(self):
        return self.metadata['well_info']['fields']
    
    def get_dim_order(self):
        return self.metadata.get('dim_order', 'tczyx')
    
    def get_dtype(self):
        return self.metadata.get('dtype', np.uint16)
    
    def get_pixel_size_um(self):
        pixel_size = self.metadata['well_info'].get('PixelSizeUm', 1.0)
        return {'x': pixel_size, 'y': pixel_size}
    
    def get_well_coords_um(self, well_id):
        """Get well coordinates (placeholder - Incucyte doesn't typically have stage coordinates)"""
        return {'x': 0.0, 'y': 0.0}
    
    def get_channels(self):
        return [{'label': ch['Dye'], 'color': ch['Color'].lstrip('#')} for ch in self.metadata['channels']]
    
    def get_nchannels(self):
        return max(self.metadata['num_channels'], 1)
    
    def get_acquisitions(self):
        """Return acquisition information based on timepoints"""
        acquisitions = []
        for i, tp in enumerate(self.metadata['timepoints']):
            acq = {
                'id': i,
                'name': f"Timepoint_{tp['timestamp']}",
                'description': f"Incucyte acquisition at {tp['timestamp']}",
                'date_created': tp['datetime'].isoformat() if tp['datetime'] else tp['timestamp'],
                'date_modified': tp['datetime'].isoformat() if tp['datetime'] else tp['timestamp']
            }
            acquisitions.append(acq)
        return acquisitions
    
    def get_total_data_size(self):
        return self.metadata.get('max_data_size', 0)
    
    def print_well_matrix(self):
        """Print a visual representation of the plate layout"""
        s = ''
        well_info = self.metadata['well_info']
        rows, cols = well_info['rows'], [int(c) for c in well_info['columns']]
        used_wells = set(self.metadata['wells'].keys())
        
        # Header with column numbers
        header = '   ' + '  '.join(f'{col:2d}' for col in cols)
        s += header + '\n'
        
        # Each row
        for row_letter in rows:
            row_line = f'{row_letter}  '
            for col_num in cols:
                well_id = f'{row_letter}{col_num}'
                row_line += ' + ' if well_id in used_wells else '   '
            s += row_line + '\n'
        
        return s
    
    
    def print_timepoint_well_matrix(self):
        """Print timepoint vs well matrix"""
        s = ''
        timepoints = self.metadata['timepoints']
        wells = list(self.metadata['wells'].keys())
        
        # Header
        header = 'Timepoint   ' + '  '.join(f'{well:>3}' for well in wells)
        s += header + '\n'
        
        # Check which wells have data at each timepoint
        for tp in timepoints:
            line = f'{tp["timestamp"]:>9}   '
            for well in wells:
                # Check if any files exist for this well at this timepoint
                has_data = any(
                    (tp['path'] / f'{well}-{field}-{channel}.tif').exists()
                    for field in self.metadata['fields_raw']
                    for channel in self.metadata['channels_raw']
                )
                line += ' + ' if has_data else '   '
            s += line + '\n'
        
        return s
    
    def close(self):
        """Clean up resources"""
        self._file_cache.clear()