# -*- coding:utf-8 -*-

import copy
from shapely.geometry import Polygon
from primitive import Primitive

class Face(Primitive):

    _SHAPELY_CLASS = Polygon
    _EXTRA_ARGS = ('extring','intrings')

    @property
    def extring(self):
        return self._extring

    @property
    def intrings(self):
        return tuple(sorted(self._intrings))
