# -*- coding:utf-8 -*-

from shapely.geometry import Point
from primitive import Primitive

class Node(Primitive):

    _SHAPELY_CLASS = Point
    _EXTRA_ARGS = tuple()
