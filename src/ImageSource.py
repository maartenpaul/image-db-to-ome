from abc import ABC


class ImageSource(ABC):
    def __init__(self, uri, metadata={}):
        self.uri = uri
        self.metadata = metadata

    def init(self):
        raise NotImplementedError("The 'init' method must be implemented by subclasses.")
