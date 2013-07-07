# -*- coding:utf-8 -*-

class Primitive(object):

    def __init__(self,*args,**kwargs):

        geometry = kwargs.get('geometry',None)

        if geometry:
            assert(isinstance(geometry,self._SHAPELY_CLASS))
            self._geom = geometry

        else:

            effkwargs = dict(filter(lambda (k,v): k not in self._EXTRA_ARGS,kwargs.items()))
            self._geom = self._SHAPELY_CLASS(*args,**effkwargs)

        for k,v in kwargs.items():
            if k in self._EXTRA_ARGS:
                setattr(self,'_'+k,v)

    @property
    def geom(self):
        return self._geom
