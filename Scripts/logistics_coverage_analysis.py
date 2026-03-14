import os
import glob
import random
from qgis.core import *
from qgis.analysis import *
import processing

# ── 1. CLEANUP ───────────────────────────────────────────────────────────────
keep_layers = ['Reprojected_Roads', 'Delivery_hubs',
               'Reprojected_Munich_Boundary', 'OpenStreetMap']

for lid, layer in list(QgsProject.instance().mapLayers().items()):
    if layer.name() not in keep_layers:
        QgsProject.instance().removeMapLayer(lid)

QgsApplication.processEvents()
print("Cleanup done.")

# ── 2. PATHS ──────────────────────────────────────────────────────────────────
PROJECT_FOLDER = os.path.dirname(QgsProject.instance().fileName())
OUTPUT_FOLDER = os.path.join(PROJECT_FOLDER, "outputs")
if not os.path.exists(OUTPUT_FOLDER):
    os.makedirs(OUTPUT_FOLDER)

for f in glob.glob(os.path.join(OUTPUT_FOLDER, '*')):
    os.remove(f)
print("Output folder ready:", OUTPUT_FOLDER)

# ── 3. LOAD LAYERS ────────────────────────────────────────────────────────────
roads_layer = QgsProject.instance().mapLayersByName('Reprojected_Roads')[0]
hubs_layer = QgsProject.instance().mapLayersByName('Delivery_hubs')[0]
boundary_layer = QgsProject.instance().mapLayersByName('Reprojected_Munich_Boundary')[0]

roads_layer.setSubsetString("\"type\" IN ('motorway','trunk','primary','secondary','tertiary','unclassified')")
print("Layers loaded and roads filtered.")

# ── 4. VORONOI ────────────────────────────────────────────────────────────────
print("Running Voronoi...")
voronoi_result = processing.run("qgis:voronoipolygons", {
    'INPUT': hubs_layer,
    'BUFFER': 10,
    'OUTPUT': os.path.join(OUTPUT_FOLDER, 'voronoi.shp')
})

voronoi_clipped = processing.run("native:intersection", {
    'INPUT': voronoi_result['OUTPUT'],
    'OVERLAY': boundary_layer,
    'OUTPUT': os.path.join(OUTPUT_FOLDER, 'voronoi_clipped.shp')
})
print("Voronoi complete.")

# ── 5. ISOCHRONES ─────────────────────────────────────────────────────────────
print("Running Isochrones...")
isochrone_result = processing.run("qneat3:isoareaaspolygonsfromlayer", {
    'INPUT': roads_layer,
    'START_POINTS': hubs_layer,
    'ID_FIELD': 'id',
    'MAX_DIST': 10000,
    'INTERVAL': 3333,
    'CELL_SIZE': 50,
    'STRATEGY': 0,
    'DEFAULT_DIRECTION': 2,
    'DEFAULT_SPEED': 30,
    'TOLERANCE': 0,
    'OUTPUT_POLYGONS': os.path.join(OUTPUT_FOLDER, 'isochrones.shp'),
    'OUTPUT_INTERPOLATION': os.path.join(OUTPUT_FOLDER, 'isochrones_raster.tif')
})
print("Isochrones complete.")

# ── 6. CLIP ISOCHRONES TO MUNICH ──────────────────────────────────────────────
print("Clipping isochrones to Munich boundary...")
isochrones_clipped = processing.run("native:intersection", {
    'INPUT': isochrone_result['OUTPUT_POLYGONS'],
    'OVERLAY': boundary_layer,
    'OUTPUT': os.path.join(OUTPUT_FOLDER, 'isochrones_clipped.shp')
})
print("Isochrones clipped.")

# ── 7. COVERAGE GAPS ──────────────────────────────────────────────────────────
print("Finding coverage gaps...")
fixed = processing.run("native:fixgeometries", {
    'INPUT': isochrones_clipped['OUTPUT'],
    'OUTPUT': 'TEMPORARY_OUTPUT'
})
gaps_result = processing.run("native:difference", {
    'INPUT': boundary_layer,
    'OVERLAY': fixed['OUTPUT'],
    'OUTPUT': os.path.join(OUTPUT_FOLDER, 'coverage_gaps.shp')
})
print("Coverage gaps complete.")

# ── 8. LOAD INTO QGIS ─────────────────────────────────────────────────────────
print("Loading layers into QGIS...")

voronoi_layer = QgsVectorLayer(voronoi_clipped['OUTPUT'], 'Voronoi Territories', 'ogr')
QgsProject.instance().addMapLayer(voronoi_layer)

iso_layer = QgsVectorLayer(isochrones_clipped['OUTPUT'], 'Isochrones', 'ogr')
QgsProject.instance().addMapLayer(iso_layer)

gaps_layer = QgsVectorLayer(gaps_result['OUTPUT'], 'Coverage Gaps', 'ogr')
QgsProject.instance().addMapLayer(gaps_layer)

print("All layers loaded.")

# ── 9. SYMBOLOGY ──────────────────────────────────────────────────────────────

# Isochrones - graduated colors
ranges = []
symbol1 = QgsFillSymbol.createSimple({'color': '255,0,0,150', 'outline_width': '0.5'})
ranges.append(QgsRendererRange(0, 3333, symbol1, '0 - 3333m (close)'))
symbol2 = QgsFillSymbol.createSimple({'color': '255,255,0,150', 'outline_width': '0.5'})
ranges.append(QgsRendererRange(3333, 6666, symbol2, '3333 - 6666m (medium)'))
symbol3 = QgsFillSymbol.createSimple({'color': '0,200,0,150', 'outline_width': '0.5'})
ranges.append(QgsRendererRange(6666, 10000, symbol3, '6666 - 10000m (far)'))
symbol4 = QgsFillSymbol.createSimple({'color': '0,100,0,150', 'outline_width': '0.5'})
ranges.append(QgsRendererRange(10000, 15000, symbol4, '10000m+ (outer)'))
iso_layer.setRenderer(QgsGraduatedSymbolRenderer('cost_level', ranges))
iso_layer.triggerRepaint()
print("Isochrone symbology applied.")

# Coverage gaps - purple
gap_symbol = QgsFillSymbol.createSimple({
    'color': '128,0,128,180',
    'outline_width': '0.5'
})
gaps_layer.setRenderer(QgsSingleSymbolRenderer(gap_symbol))
gaps_layer.triggerRepaint()
print("Coverage gaps symbology applied.")

# Voronoi - random colors
random.seed(42)
categories = []
for feature in voronoi_layer.getFeatures():
    r = random.randint(50, 255)
    g = random.randint(50, 255)
    b = random.randint(50, 255)
    symbol = QgsFillSymbol.createSimple({
        'color': f'{r},{g},{b},180',
        'outline_width': '0.5'
    })
    categories.append(QgsRendererCategory(
        feature['id'], symbol, str(feature['id'])))
voronoi_layer.setRenderer(QgsCategorizedSymbolRenderer('id', categories))
voronoi_layer.setOpacity(0.7)
voronoi_layer.triggerRepaint()
print("Voronoi symbology applied.")

print("\n✓ Analysis complete!")