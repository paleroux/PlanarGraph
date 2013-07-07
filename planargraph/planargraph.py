# -*- coding:utf-8 -*-

import os
import sys

from rtree import Rtree

from shapely.ops import unary_union, linemerge, polygonize
from shapely.prepared import prep
from shapely.geometry import Point, MultiPoint
from shapely.geometry import LineString, MultiLineString
from shapely.geometry.polygon import LinearRing
from shapely.geometry import Polygon, MultiPolygon
from shapely.geometry import GeometryCollection

from node import Node
from edge import Edge
from face import Face
from ring import Ring

from error import PGException
from util import clockwise
from util import build_ring
from util import holes
from util import geometry_edges
from util import geometry_spatial_index
from util import add_points
from util import is_1D_geometry

class PlanarGraph(object):

    _INIT_KWARGS  = ('bnode','bface','btopo','bsrce')
    _INIT_DEFAULT = (False,) * len(_INIT_KWARGS)


    def __init__(self,**kwargs):

        self._entries = list()   # liste des arcs en entrée du calcul
        self._done    = False    # calcul fait ou pas ?
        self._nextid  = 0        # prochaine ident à retourner (si bsrce)

        for key, default in zip(PlanarGraph._INIT_KWARGS,PlanarGraph._INIT_DEFAULT):
            setattr(self,'_'+key,kwargs.get(key,default))

        # sources à calculer ? la topologie sera disponible !
        if self._bsrce: self._btopo = True
        
        # topologie à calculer ? les noeuds et les faces seront disponibles !
        if self._btopo: self._bnode = self._bface = True

        if self._bsrce: self._idents = list()

    def add_geometry(self, geometry):

        if self._done: return

        # arcs issus de la géométrie
        new_edges = geometry_edges(geometry)

        if new_edges:
            self._entries.extend(new_edges)
            if self._bsrce:
                self._idents.extend([self._nextid]*len(new_edges))
                self._nextid += 1
                return self._nextid - 1


    def _geometric_process(self):

        if len(self._entries) != 1:
            merged_union = linemerge(unary_union(self._entries))
        else:
            merged_union = MultiLineString(self._entries)

        self._edges = [ Edge(tuple(g.coords)) for g in merged_union.geoms ]

        edges = map(lambda e: e._geom, self._edges)

        if self._bnode:
            xyset = set([edge.coords[i] for edge in edges for i in (0,-1)])
            self._nodes = map(lambda xy: Node(xy),xyset)

        if self._bface:
            self._faces = [Face(poly.exterior,poly.interiors) for poly in polygonize(edges)]


    def _process_rings(self,edges=None,faces=None,edge_si=None,face_si=None):

        self._rings = list()    # initialisation des périmètres du graphe

        # facilité d'écriture pour la suite + travail fait une seule fois
        if edges is None: edges = map(lambda e: e._geom,self._edges)
        if faces is None: faces = map(lambda f: f._geom,self._faces)

        # index spatiaux basés sur les arcs et les faces s'ils n'ont pas été fournis
        if edge_si is None: edge_si = geometry_spatial_index(edges)
        if face_si is None: face_si = geometry_spatial_index(faces)

        # listes des périmètres extérieurs et de leur géométrie préparée
        # les périmètres n'ont pas leur propre géométrie mais pointent vers les faces
        rings = map(lambda f: f.exterior,faces)
        preps = map(lambda r: prep(r), rings)

        # boucle sur les faces/périmètres extérieurs (ils se correspondent !)
        for f,(ring,pring) in enumerate(zip(rings,preps)):

            # indices des arcs qui composent le périmètre courant
            indexes  = list(edge_si.intersection(ring.bounds))
            indexes  = filter(lambda i: pring.contains(edges[i]),indexes)

            # séquence d'arcs orientés décrivant le périmètre courant
            # orientation de l'arc (sens aiguilles d'une montre ou inverse)
            content = build_ring(ring,map(lambda i: edges[i],indexes),indexes)
            edge_clockwise = clockwise(ring)

            # mise à jour des arcs composant le périmètre (_left_face ou _right_face) 
            for noedge, direct in content:
                right_attrname = '_right_face' if edge_clockwise == direct else '_left_face'
                setattr(self._edges[noedge],right_attrname,f)
                # print getattr(self._edges[noedge],right_attrname)

            # mise à jour de la face correspondante
            self._faces[f]._extring = len(self._rings)

            # ajout du périmètre (instance Ring) dans le graphe
            self._rings.append(Ring(edge_clockwise,content))

        for face_container, all_holes in enumerate(holes(faces,face_si)):

            # quand un trou est bouché par PLUSIEURS faces, le ring n'existe
            # pas déjà (il n'est pas LE ring extérieur d'UNE FACE).
            
            for hole in all_holes:

                if len(hole) == 1:
                    self._faces[face_container]._intrings.append(self._faces[hole[0]]._extring)
                    continue

                # il va falloir créer un nouveau ring ...
                # il faut prendre le périmètre extérieur de l'union des faces du trou
                # et enlever, dans les arcs constituant les périmètre extérieurs
                
                newring   = unary_union(map(lambda h: self._faces[h]._geom,hole)).exterior
                all_edges = set()
                for h in hole:
                    for noedge, _ in self._rings[self._faces[h]._extring]._edges:
                        all_edges.add(noedge)

                true_edges = filter(lambda e: newring.contains(self._edges[e]._geom),all_edges)
                
                newring = Ring(clockwise(newring),build_ring(newring,map(lambda e: self._edges[e]._geom,true_edges),true_edges))
                
                
                idring = len(self._rings)
                self._rings.append(newring)
                self._faces[face_container]._intrings.append(idring)
            

            for included_faces in all_holes:
                for noface in included_faces:
                    for noedge,_ in self._rings[self._faces[noface]._extring]._edges:
                        if self._edges[noedge]._left_face is None:
                            self._edges[noedge]._left_face = face_container
                        if self._edges[noedge]._right_face is None:
                            self._edges[noedge]._right_face = face_container

        # il peut rester des arcs "flottants" au beau milieu d'une face
        for edge in self._edges:
            if (edge._left_face,edge._right_face) != (None,None):
                continue
            candidates = list(face_si.intersection(edge._geom.bounds))
            if not candidates: continue
            candidates = filter(lambda c: self._faces[c]._geom.contains(edge._geom),candidates)
            assert len(candidates) in (0,1)
            if len(candidates) == 1:
                edge._left_face = edge._right_face = candidates[0]

    def process_sources(self):

        EPSILON = 1e-9

        edges   = map(lambda e: e._geom,self._edges)
        entries = self._entries

        # ajout, dans les arcs en entrée, des noeuds qui sont apparus
        points  = map(lambda n: n._geom,self._nodes)
        si = geometry_spatial_index(self._entries)
        add_points(points,self._entries,EPSILON,si)

        entry_si = geometry_spatial_index(self._entries)

        for e,edge in enumerate(edges):
            candidates = list(entry_si.intersection(edge.bounds))
            prepedge = prep(edge)
            candidates = filter(lambda c: prepedge.intersects(entries[c]),candidates)
            candidates = filter(lambda c: is_1D_geometry(edge.intersection(entries[c])),candidates)
            self._edges[e]._sources = map(lambda c: self._idents[c], candidates)

    def _topological_process(self):

        # initialisation des arcs (géométrie calculée, autres attributs à None)

        init_None = dict.fromkeys(('start_node','end_node','left_face','right_face'),None)
        if len(self._entries) != 1:
            merged_union = linemerge(unary_union(self._entries))
        else:
            merged_union = MultiLineString(self._entries)
        self._edges = [ Edge(tuple(g.coords),**init_None) for g in merged_union.geoms ]
        del merged_union


        # liste des géométries Shapely des Edge (arcs du graphe) et index spatial
        # (facilité d'écriture par la suite + fait une seule fois)

        edges   = map(lambda e: e._geom,self._edges)
        edge_si = geometry_spatial_index(edges)

        # construction des noeuds, mise à jour des noeuds départ et fin des arcs

        self._nodes, already_done = list(), dict()
        for edge in self._edges:
            for i,attname in ((0,'_start_node'),(-1,'_end_node')):
                xy = edge._geom.coords[i]
                inode = already_done.get(xy,None)
                if inode is None:
                    already_done[xy] = inode = len(self._nodes)
                    self._nodes.append(Node(xy))
                setattr(edge,attname,inode)
        del already_done

        # création des faces du graphe planaire

        self._faces = list()
        for polygon in polygonize(edges):
            new_face = Face(polygon.exterior,polygon.interiors,extring=None,intrings=list())
            self._faces.append(new_face)

        # liste des géométries Shapely des Face (faces du graphe et index spatial)
        # (facilité d'écriture par la suite + fait une seule fois)
        faces   = map(lambda pgf: pgf._geom,self._faces)
        face_si = geometry_spatial_index(faces)

        self._process_rings(edges,faces,edge_si,face_si)


    def process(self):

        if self._done: return

        if not self._bsrce and not self._entries:
            return

        if not self._btopo:
            self._geometric_process()

        else:
            self._topological_process()
            if self._bsrce:
                self.process_sources()

        self._done = True
        del self._entries

    @property
    def nodes(self):
        return tuple(self._nodes)

    @property
    def edges(self):
        return tuple(self._edges)

    @property
    def faces(self):
        return tuple(self._faces)

    @property
    def rings(self):
        return tuple(self._rings)
