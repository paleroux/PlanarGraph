# -*- coding:utf-8 -*-

import copy
from shapely.ops import linemerge

class Ring(object):

    def __init__(self,clockwise,edges):
        self._clockwise = clockwise
        self._edges     = edges

    def clockwise(self):
        return self._clockwise

    def edges(self):
        return tuple(self._edges)
