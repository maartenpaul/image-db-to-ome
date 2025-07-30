from abc import ABC

from src.util import convert_to_um


class ImageSource(ABC):
    def __init__(self, uri, metadata={}):
        self.uri = uri
        self.metadata = metadata

    def init(self):
        raise NotImplementedError("The 'init' method must be implemented by subclasses.")

    def get_dim_order(self):
        return self.metadata.get('dim_order', 'tczyx')

    def get_dtype(self):
        return self.metadata.get('dtype')
