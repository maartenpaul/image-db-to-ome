from abc import ABC


class ImageSource(ABC):
    def __init__(self, uri, metadata={}):
        self.uri = uri
        self.metadata = metadata

    def init_metadata(self):
        raise NotImplementedError("The 'init_metadata' method must be implemented by subclasses.")

    def select_well(self, well_id):
        raise NotImplementedError("The 'select_well' method must be implemented by subclasses.")

    def get_image(self, field_id):
        raise NotImplementedError("The 'get_image' method must be implemented by subclasses.")

    def get_name(self):
        raise NotImplementedError("The 'get_name' method must be implemented by subclasses.")

    def get_dim_order(self):
        raise NotImplementedError("The 'get_dim_order' method must be implemented by subclasses.")

    def get_dtype(self):
        raise NotImplementedError("The 'get_dtype' method must be implemented by subclasses.")

    def get_pixel_size_um(self):
        raise NotImplementedError("The 'get_pixel_size_um' method must be implemented by subclasses.")

    def get_well_coords_um(self, well_id):
        raise NotImplementedError("The 'get_well_coords_um' method must be implemented by subclasses.")

    def get_channels(self):
        raise NotImplementedError("The 'get_channels' method must be implemented by subclasses.")

    def get_nchannels(self):
        raise NotImplementedError("The 'get_nchannels' method must be implemented by subclasses.")

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
