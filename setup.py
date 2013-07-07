from setuptools import setup
setup(name              = "PlanarGraph",
      version           = "1.0",
      keywords          = "planar graph topology",
      requires_python   = '>=2.6,<3',
      requires_external = 'Shapely (>=1.2.16), Rtree (>=0.7.0)',
      author            = "Pascal Leroux",
      author_email      = "pa.leroux@gmail.com",
      maintainer        = "Pascal Leroux",
      maintainer_email  = "pa.leroux@gmail.com",
      packages          = ['planargraph'],
      description       = "build a planar graph from Shapely 1D/2D geometries",
      zip_safe          = False)
