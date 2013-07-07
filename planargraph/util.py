# -*- coding:utf-8 -*-

import sys
from rtree import Rtree
from shapely.prepared import prep
from shapely.geometry import Point, MultiPoint
from shapely.geometry import LineString, MultiLineString
from shapely.geometry.polygon import LinearRing 
from shapely.geometry import Polygon, MultiPolygon
from shapely.geometry import GeometryCollection


from error import PGException

# liste des arcs d'une géométrie, pour chaque type degéométrie Shapely
# via des fonctions lambda (sauf pour GeometryCollection)

_point_edges           = lambda g: list()
_multipoint_edges      = lambda g: list()
_linestring_edges      = lambda g: [ LineString(tuple(map(lambda xy: xy[:2],g.coords))) ]
_multilinestring_edges = lambda g: [ LineString(tuple(map(lambda xy: xy[:2],geom.coords))) for geom in g.geoms ]
_polygon_edges         = lambda g: [ LineString(tuple(map(lambda xy: xy[:2],g.exterior.coords))) ] + [ LineString(tuple(map(lambda xy: xy[:2],geom.coords))) for geom in g.interiors ]
_multipolygon_edges    = lambda g: sum(map(lambda p: _polygon_edges(p), g.geoms),list())

def _geometrycollection_edges(collection):
    edges = list()
    for geom in collection.geoms:
        if isinstance(geom, GeometryCollection):
            edges.extend(_geometrycollection_edges(geom))
        else:
            edges.extend(geometry_edges(geom))
    return edges

# afin d'éviter des if ... elif ... interminables, regroupement dans un
# dictonnaire où :
#    - les clés sont les différentes classes des géométries Shapely
#    - les valeurs sont les fonctions retournant la liste des arcs pour la clé/classe

_geometry_edges = { Point              : _point_edges,
                    MultiPoint         : _multipoint_edges,
                    LineString         : _linestring_edges,
                    LinearRing         : _linestring_edges,
                    MultiLineString    : _multilinestring_edges,
                    Polygon            : _polygon_edges,
                    MultiPolygon       : _multipolygon_edges,
                    GeometryCollection : _geometrycollection_edges }


geometry_edges = lambda g: _geometry_edges[g.__class__](g)

def _issubtuple(ref,sec):
    offset = 0
    while sec[0] in ref[offset:]:
        index = ref.index(sec[0],offset)
        if ref[index:index+len(sec)] == sec:
            return True
        else:
            offset = index + 1
    return False

def geometry_spatial_index(geometries):
    spatial_index = Rtree()
    for g,geom in enumerate(geometries):
        spatial_index.add(g,geom.bounds)
    return spatial_index

def segment_spatial_index(linestring):
    coords = list(linestring.coords)
    spatial_index = Rtree()
    for i in range(len(coords)-1):
        x = map(lambda xy: xy[0],coords[i:i+2])
        y = map(lambda xy: xy[1],coords[i:i+2])
        spatial_index.add(i,(min(x),min(y),max(x),max(y)))
    return spatial_index

def _orientation(refedge, secedge):

    rcoords = tuple(refedge.coords)
    scoords = tuple(secedge.coords)

    if _issubtuple(rcoords,scoords):
        return True

    elif _issubtuple(rcoords,scoords[::-1]):
        return False

    raise PGException('orientation: refedge does not contain secedge')


def clockwise(edge):

    assert isinstance(edge,LineString)
    assert edge.is_ring

    coords = tuple(edge.coords)
    X0, Y0 = coords[0]
    vectors = [ (coords[i][0]-X0,coords[i][1]-Y0) for i in range(1,len(coords)-1) ]
    sum = 0.
    for i in range(1,len(vectors)):
        sum += vectors[i-1][0]*vectors[i][1]-vectors[i-1][1]*vectors[i][0]
    return False if 0.< sum else True


def build_ring(ring,edges,labels=None):
    
    # hypothèses : les arcs permettent de reconstruire le ring en entier
    # les orientations des arcs indiquent s'ils sont du même sens que
    # le périmètre (True) ou en sens contraire(False)

    # initialisation de la liste à retourner et du pivot
    if _orientation(ring,edges[0]) == True:
        result, node_xy = [(0,True)],  edges[0].coords[-1]
    else:
        result, node_xy = [(0,False)], edges[0].coords[0]

    # index des arcs disponibles pour reconstruire le périmètre
    # (tous sauf le premier qui a servi à l'initialistion)
    indexes = list(range(len(edges)))[1:]

    while indexes:

        # recherche de l'arc qui débute/finit sur le node d'identifiant <node_id>
        next = None
        for i,idx in enumerate(indexes):
            if node_xy in (edges[idx].coords[0],edges[idx].coords[-1]):
                next, todel = idx, i;
                break

        if next is None:
            raise PGException('build_ring: cannot find the next edge')

        if node_xy == edges[next].coords[0]:
            result.append((next,True))
            node_xy = edges[next].coords[-1]

        else:
            result.append((next,False))
            node_xy = edges[next].coords[0]

        del indexes[todel]

    if labels:
        result = map(lambda (i,o): (labels[i],o),result)

    return result


def holes(faces,face_si=None):

    result = map(lambda f: list(),faces)
    
    if face_si is None:
        face_si = geometry_spatial_index(faces)

    for f,face in enumerate(faces):
        for h,hole in enumerate(face.interiors):

            indexes = list(face_si.intersection(hole.bounds))
            if f in indexes: indexes.remove(f)

            indexes = filter(lambda i: hole.intersects(faces[i].exterior),indexes)
            
            hole_polygon = Polygon(hole)
            indexes = filter(lambda i: hole_polygon.contains(faces[i]),indexes)

            result[f].append(indexes)

    return result


def _add_points_to_edge(edge,points,epsilon):

    # liste des coordonnées (x,y) de l'arc à mettre à jour
    edge_coords = list(edge.coords)

    # on shunte les points déjà présents dans l'arc  
    points = filter(lambda pt: pt.coords[0] not in edge_coords,points)

    if not points: return edge

    # index spatial basé sur les segments de l'arc
    segment_si = segment_spatial_index(edge)
    
    # ptbounds : rectangles englobants centrés sur les points
    epsilons = 2*(-epsilon,)+2*(epsilon,)
    ptbounds = map(lambda pt: map(lambda (a,b): a+b,zip(pt.coords[0]*2,epsilons)),points)
    
    # liste de tuples (s,p), 1 par point à ajouter dans l'arc, avec :
    #    s : indice du segment où il faut ajouter le point
    #    p : indice dans <points> du point à ajouter
    new_vertices = list()

    for p,(point,bounds) in enumerate(zip(points,ptbounds)):
        # indice des segments susceptibles d'être à moins d'epsilon du point
        candidates = list(segment_si.intersection(bounds))
        # segments correspondant aux indices <candidates>
        segments = map(lambda c: (c,LineString(edge.coords[c:c+2])),candidates)
        mindist, s = sorted(map(lambda (s,ls): (ls.distance(point),s),segments))[0]
        new_vertices.append((s,p))

    # pour pouvoir utiliser les infos de new_vertices, il faut trier les
    # points en sens inverse, dernier segement à la fin et, dans un même
    # segment, s'il y a plusieurs points, point le plus éloigné du départ
    # du segment    
    sort_key = lambda (seg,pt): (seg,Point(edge_coords[seg]).distance(points[pt]))
    new_vertices.sort(key=sort_key,reverse=True)
    
    for noseg,nopt in new_vertices:
        #print >> wkt, points[nopt].wkt
        edge_coords.insert(noseg+1,points[nopt].coords[0])

    return LineString(edge_coords)

def add_points(points,edges,epsilon,edge_si=None):

    #wkt = open('/Users/pascal/Desktop/new_points.wkt','w')

    # construction d'un index spatial basé les arcs si non fourni
    if edge_si is None:
        edge_si = geometry_spatial_index(edges)

    # cercles de rayon epsilon centré sur les points
    zones = map(lambda point: point.buffer(epsilon),points)

    # les (indices des) arcs cibles pour chaque point
    edge_targets = map(lambda e: list(),edges)

    for p,(point,zone) in enumerate(zip(points,zones)):
        candidates = list(edge_si.intersection(zone.bounds))
        candidates = filter(lambda c: zone.intersects(edges[c]),candidates)
        for c in candidates:
            edge_targets[c].append(p)

    for e,(edge,idpts) in enumerate(zip(edges,edge_targets)):
        if idpts:
            edges[e] = _add_points_to_edge(edge,map(lambda i:points[i],idpts),epsilon)

    #wkt.close()

def is_1D_geometry(geometry):

    if geometry.is_empty: return False

    if isinstance(geometry,(LineString,MultiLineString)):
        return True

    elif isinstance(geometry,GeometryCollection):
        for geom in geometry.geoms:
            if is_1D_geometry(geom):
                return True
        
    return False
