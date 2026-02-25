# Phase 3: Spatial Analysis (Overland) - Research

**Researched:** 2025-03-05
**Domain:** GIS, Spatial Indexing, AIS Spoofing
**Confidence:** HIGH

## Summary

This phase implements overland detection, which identifies vessels broadcasting positions that are physically impossible (on land). This is a high-confidence indicator of AIS spoofing/GPS injection.

## Standard Stack

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `shapely` | Latest | Geometric operations (Point-in-Polygon) | Python standard for GIS. |
| `pyshp` | Latest | Reading Shapefiles (.shp, .dbf) | Lightweight alternative to GeoPandas. |
| Natural Earth | 10m Land | Base map data | High-quality, public domain, ~5MB. |

## Architecture Patterns

### Spatial Indexing (STRtree)
To avoid checking every land polygon for every AIS point (O(N*M)), we use `shapely.strtree.STRtree`. This allows O(log N) lookup.

```python
from shapely.geometry import shape, Point
from shapely.strtree import STRtree
import shapefile

class LandGeometryLoader:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.load_geometries()
        return cls._instance

    def load_geometries(self):
        # Path: data/shp/ne_10m_land/ne_10m_land.shp
        with shapefile.Reader(path) as sf:
            self.geoms = [shape(s.__geo_interface__) for s in sf.shapes()]
            self.tree = STRtree(self.geoms)
```

### Safety Margin (Negative Buffer)
Coastal AIS jitter can cause false positives near shorelines. A "safety margin" is required.
- **Option A:** Buffer the point (slow).
- **Option B:** Negative buffer the land (pre-process, fast).
- **Decision:** Use a 0.001 degree (~100m) buffer check or simply accept that Natural Earth 10m is generalized enough that minor shore overlaps are expected; however, a small buffer check on the point is safest for initial implementation.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Shapefile Parsing | Custom binary parser | `pyshp` | Handles all sidecar files (.shx, .dbf). |
| Point-in-Polygon | Ray-casting logic | `shapely` | Optimized C-extensions (GEOS). |

## Common Pitfalls

### Pitfall 1: Coordinate Order
**What goes wrong:** AIS uses (Lat, Lon), but GIS libraries often expect (X, Y) which is (Lon, Lat).
**How to avoid:** Always use `Point(lon, lat)` when creating Shapely objects.

### Pitfall 2: Memory Usage
**What goes wrong:** Loading 110m land is tiny, but 10m land has thousands of complex polygons.
**How to avoid:** Ensure `LandGeometryLoader` is a singleton and only loads once per process.

### Pitfall 3: Inland Waterbodies
**What goes wrong:** Ships in rivers or the Great Lakes might be flagged if using "land" polygons that don't exclude major water bodies.
**How to avoid:** Natural Earth "land" usually includes everything that isn't ocean. For maritime-OSINT, we specifically want to flag positions that are *not* in water.

## Sources
- [Shapely Documentation](https://shapely.readthedocs.io/)
- [Natural Earth Data](https://www.naturalearthdata.com/)
- [pyshp (PyShp) Documentation](https://github.com/GeospatialPython/pyshp)
