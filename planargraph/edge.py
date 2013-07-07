# -*- coding:utf-8 -*-

import copy
from shapely.geometry import LineString
from primitive import Primitive

class Edge(Primitive):

    _SHAPELY_CLASS = LineString
    _EXTRA_ARGS = ('start_node','end_node','left_face','right_face','sources')

    @property
    def start_node(self):
        return self._start_node

    @property
    def end_node(self):
        return self._end_node

    @property
    def left_face(self):
        return self._left_face

    @property
    def right_face(self):
        return self._right_face

    @property
    def sources(self):
        return tuple(sorted(self._sources))
