from qgis.core import *
from qgis.PyQt.QtCore import QMetaType
import processing
from processing.core.Processing import Processing
Processing.initialize()
import os
import logging

def generate_save_path(origin_path, prefix = ""):
    dir = os.path.dirname(origin_path)
    name = os.path.basename(origin_path).split('.')[0]
    new_path = os.path.join(dir, f'{name}_{prefix}.shp')
    return new_path

def run_processing_algorithm(algorithm, params):
    result = processing.run(algorithm, params)
    if 'error' in result:
        print(f"error running the processing {algorithm}: {result['error']}")
        return False
    return True

def construct_index_field(field_name):
    return QgsField(field_name, QMetaType.Type.Int)

def reindex_feature(feature_path, field_name):
    '''
    Use QGIS API to reindex the feature layer
    feature_path: the path of the feature shapefile
    field_name: the name of the field to reindex
    '''
    # add the field to the feature layer
    feature_layer = QgsVectorLayer(feature_path, 'Feature Layer', 'ogr')
    feature_layer.dataProvider().addAttributes([construct_index_field(field_name)])
    feature_layer.updateFields()
    monoid_field_index = feature_layer.fields().indexOf(field_name)
    monoid_map = {
        f.id(): {monoid_field_index: f.id()}
        for f in feature_layer.getFeatures()
    }
    feature_layer.dataProvider().changeAttributeValues(monoid_map)
    return feature_path

def reproject_shapefile(geo_shp_path,proj_shp_path = ""):
    '''
    convert WGS84 to WGS84 UTM50N
    geo_shp_path: the path of the original shapefile
    proj_shp_path: the path of the projected shapefile
    if proj_shp_path is not provided, the projected shapefile will be saved in the same directory as the original shapefile
    output: the path of the projected shapefile
    '''
    if proj_shp_path == "":
        proj_shp_path = generate_save_path(geo_shp_path, "p")
    if os.path.exists(proj_shp_path):
        os.remove(proj_shp_path)
    crs_params = {
        'CONVERT_CURVED_GEOMETRIES' : False,
        'INPUT' : geo_shp_path,
        'OPERATION' : '+proj=pipeline +step +proj=unitconvert +xy_in=deg +xy_out=rad +step +proj=utm +zone=50 +ellps=WGS84',
        'OUTPUT' : proj_shp_path,
        'TARGET_CRS' : QgsCoordinateReferenceSystem('EPSG:32650')
    }
    if not run_processing_algorithm("native:reprojectlayer", crs_params):
        return ""
    return proj_shp_path

def filter_remain_field(proj_poly_path, line_path, filter_path = ""):
    '''
    Use QGIS API to filter the line layer by the remain field
    proj_poly_path: the path of the projected polygon shapefile
    line_path: the path of the line shapefile
    filter_path: the path of the filtered line shapefile
    if filter_path is not provided, the filtered line shapefile will be saved in the same directory as the line shapefile
    output: the path of the filtered line shapefile
    '''
    def determine_remain(area):
        if area > 100000: # 0.1 km2
            return 1
        else:
            return 0

    if filter_path == "":
        filter_path = generate_save_path(line_path, "f")
    if os.path.exists(filter_path):
        os.remove(filter_path)
    # iterate through the polygon layer and add the area attribute
    poly_layer = QgsVectorLayer(proj_poly_path, 'Multipolygon Layer', 'ogr')
    if not poly_layer.isValid():
        print("Layer failed to load!")
    line_layer = QgsVectorLayer(line_path, 'Line Layer', 'ogr')
    if not line_layer.isValid():
        print("Line layer failed to load!")
    
    line_layer.dataProvider().addAttributes([QgsField("remain", QMetaType.Type.Int)])
    line_layer.updateFields()
    remain_field = line_layer.fields().indexOf("remain")
    with edit(line_layer):
        for feature, line_feature in zip(poly_layer.getFeatures(), line_layer.getFeatures()):
            area = feature.geometry().area()
            line_layer.changeAttributeValue(line_feature.id(), remain_field, determine_remain(area))

    filter_params = {
        'FIELD' : 'remain',
        'INPUT' : line_path,
        'OPERATOR' : 0,
        'OUTPUT' : filter_path,
        'VALUE' : '1'
    }
    if not run_processing_algorithm("qgis:extractbyattribute", filter_params):
        return ""
    return filter_path

def convert_line_to_polygon(line_path, poly_path = ""):
    '''
    Use QGIS API to convert line to polygon
    line_path: the path of the line shapefile
    poly_path: the path of the polygon shapefile
    if poly_path is not provided, the polygon shapefile will be saved in the same directory as the line shapefile
    output: the path of the polygon shapefile
    '''
    if poly_path == "":
        poly_path = generate_save_path(line_path, "poly")
    if os.path.exists(poly_path):
        os.remove(poly_path)
    convert_params = {
        "INPUT": line_path,
        "OUTPUT": poly_path
    }
    if not run_processing_algorithm("qgis:linestopolygons", convert_params):
        return ""
    return poly_path

def split_lines(base_road_filepath, feature_path, splited_road_path = ""):
    '''
    Use QGIS API to split the line layer by the feature layer
    base_road_filepath: the path of the base road shapefile
    feature_path: the path of the feature shapefile
    splited_road_path: the path of the splited road shapefile
    if splited_road_path is not provided, the splited road shapefile will be saved in the same directory as the feature shapefile
    output: the path of the splited road shapefile
    '''
    if splited_road_path == "":
        splited_road_path = generate_save_path(feature_path, "roads")
    if os.path.exists(splited_road_path):
        os.remove(splited_road_path)
    merge_params = {
        'INPUT' : base_road_filepath,
        'LINES' : feature_path,
        'OUTPUT' : splited_road_path
    }
    if not run_processing_algorithm("native:splitwithlines", merge_params):
        return ""

    reindex_feature(splited_road_path,"monoid")
    return splited_road_path

def calc_line_centroid(line_path, centroid_path = ""):
    '''
    Use QGIS API to calculate the centroid of the line layer
    line_path: the path of the line shapefile
    centroid_path: the path of the centroid shapefile
    if centroid_path is not provided, the centroid shapefile will be saved in the same directory as the line shapefile
    output: the path of the centroid shapefile
    '''
    if centroid_path == "":
        centroid_path = generate_save_path(line_path, "c")
    if os.path.exists(centroid_path):
        os.remove(centroid_path)
    calc_params = {
        'ALL_PARTS' : True,
        'INPUT' : line_path,
        'OUTPUT' : centroid_path
    }
    if not run_processing_algorithm("native:centroids", calc_params):
        return ""
    return centroid_path

def create_spatial_index(feature_path):
    '''
    Use QGIS API to create a spatial index for the feature layer
    feature_path: the path of the feature shapefile
    '''
    if not run_processing_algorithm("native:createspatialindex", {'INPUT' : feature_path}):
        return False
    return True

def join_by_attribute(input_feature_path, add_feature_path, join_path = ""):
    '''
    Use QGIS API to join the input feature layer by the add feature layer
    input_feature_path: the path of the input feature shapefile
    add_feature_path: the path of the add feature shapefile
    if join_path is not provided, the joined shapefile will be saved in the same directory as the input feature shapefile
    output: the path of the joined shapefile
    '''
    if join_path == "":
        join_path = generate_save_path(input_feature_path, "j")
    if os.path.exists(join_path):
        os.remove(join_path)
    join_params = {
        'DISCARD_NONMATCHING' : False,
        'FIELD' : 'monoid',
        'FIELDS_TO_COPY' : [],
        'FIELD_2' : 'monoid',
        'INPUT' : input_feature_path,
        'INPUT_2' : add_feature_path,
        'METHOD' : 1,
        'OUTPUT' : join_path,
        'PREFIX' : '' 
    }
    if not run_processing_algorithm("native:joinattributestable", join_params):
        return ""
    return join_path


def extract_nonull_attribute(input_feature_path, field_name, extracted_path = ""):
    '''
    Use QGIS API to extract the non-null attribute of the input feature layer
    input_feature_path: the path of the input feature shapefile
    field_name: the name of the field to extract
    extracted_path: the path of the extracted shapefile
    if extracted_path is not provided, the extracted shapefile will be saved in the same directory as the input feature shapefile
    output: the path of the extracted shapefile
    '''
    if extracted_path == "":
        extracted_path = generate_save_path(input_feature_path, "uni")
    if os.path.exists(extracted_path):
        os.remove(extracted_path)
    extract_params = {
        'FIELD' : field_name,
        'INPUT' : input_feature_path,
        'OPERATOR' : 8,
        'OUTPUT' : extracted_path,
        'VALUE' : ''
    }
    if not run_processing_algorithm("native:extractbyattribute", extract_params):
        return ""
    return extracted_path

def extract_whithindistance(input_feature_path, compare_feature_path, distance, distance_extracted_path = ""):
    '''
    Use QGIS API to extract the input feature layer within the distance of the compare feature layer
    input_feature_path: the path of the input feature shapefile
    compare_feature_path: the path of the compare feature shapefile
    distance_extracted_path: the path of the distance extracted shapefile
    if distance_extracted_path is not provided, the distance extracted shapefile will be saved in the same directory as the input feature shapefile
    output: the path of the distance extracted shapefile
    '''
    if distance_extracted_path == "":
        distance_extracted_path = generate_save_path(input_feature_path, "distance")
    if os.path.exists(distance_extracted_path):
        os.remove(distance_extracted_path)
    extract_params = {
        'DISTANCE' : distance,
        'INPUT' : input_feature_path,
        'REFERENCE' : compare_feature_path,
        'OUTPUT' : distance_extracted_path
    }
    create_spatial_index(input_feature_path)
    create_spatial_index(compare_feature_path)
    if not run_processing_algorithm("native:extractwithindistance", extract_params):
        return ""
    return distance_extracted_path

def dissolve_shapefile(input_feature_path, dissolved_path = ""):
    '''
    Use QGIS API to dissolve the input feature layer
    input_feature_path: the path of the input feature shapefile
    dissolved_path: the path of the dissolved shapefile
    if dissolved_path is not provided, the dissolved shapefile will be saved in the same directory as the input feature shapefile
    output: the path of the dissolved shapefile
    '''
    if dissolved_path == "":
        dissolved_path = generate_save_path(input_feature_path, "d")
    if os.path.exists(dissolved_path):
        os.remove(dissolved_path)
    dissolve_params = {
        'FIELD' : [],
        'INPUT' : input_feature_path,
        'OUTPUT' : dissolved_path,
        'SEPARATE_DISJOINT' : False
    }
    if not run_processing_algorithm("native:dissolve", dissolve_params):
        return ""
    return dissolved_path

def split_line_with_line(line_path, overlap_line_path, splited_line_path = ""):
    '''
    Use QGIS API to split the line layer by the overlap line layer
    line_path: the path of the line shapefile
    overlap_line_path: the path of the overlap line shapefile
    if splited_line_path is not provided, the splited line shapefile will be saved in the same directory as the line shapefile
    output: the path of the splited line shapefile
    '''
    if splited_line_path == "":
        splited_line_path = generate_save_path(line_path, "s")
    if os.path.exists(splited_line_path):
        os.remove(splited_line_path)
    split_params = { 
        'INPUT' : line_path,
        'LINES' : overlap_line_path, 
        'OUTPUT' : splited_line_path
    }
    if not run_processing_algorithm("native:splitwithlines", split_params):
        return ""
    return splited_line_path

def specific_vertices(input_feature_path, specific_vertices_path = ""):
    '''
    Use QGIS API to extract the specific vertices of the input feature layer
    input_feature_path: the path of the input feature shapefile
    if specific_vertices_path is not provided, the specific vertices shapefile will be saved in the same directory as the input feature shapefile
    output: the path of the specific vertices shapefile
    '''
    if specific_vertices_path == "":
        specific_vertices_path = generate_save_path(input_feature_path, "v")
    if os.path.exists(specific_vertices_path):
        os.remove(specific_vertices_path)
    vertice_calc_params = {
        'INPUT' : input_feature_path,
        'VERTICES' : '0, -1',
        'OUTPUT' : specific_vertices_path
    }
    if not run_processing_algorithm("native:extractspecificvertices", vertice_calc_params):
        return ""
    return specific_vertices_path

def calc_intersection(input_feature_path, compare_feature_path, grid_size = 0.01, intersection_path = ""):
    '''
    Use QGIS API to calculate the intersection of the input feature layer and the compare feature layer
    input_feature_path: the path of the input feature shapefile
    compare_feature_path: the path of the compare feature shapefile
    grid_size: the size of the grid
    if intersection_path is not provided, the intersection shapefile will be saved in the same directory as the input feature shapefile
    output: the path of the intersection shapefile
    '''
    if intersection_path == "":
        intersection_path = generate_save_path(input_feature_path, "intersection")
    if os.path.exists(intersection_path):
        os.remove(intersection_path)
    intersection_params = {
        'INPUT' : input_feature_path,
        'OVERLAY' : compare_feature_path,
        'INPUT_FIELDS' : [],
        'OVERLAY_FIELDS' : [],
        'OVERLAY_FIELDS_PREFIX' : '',
        'OUTPUT' : intersection_path,
        'GRID_SIZE' : grid_size
    }
    if not run_processing_algorithm("native:intersection", intersection_params):
        return ""
    return intersection_path

def calc_line_intersection(input_feature_path, compare_feature_path, intersection_path = ""):
    '''
    Use QGIS API to calculate the intersection of the input feature layer and the compare feature layer
    input_feature_path: the path of the input feature shapefile
    compare_feature_path: the path of the compare feature shapefile
    if intersection_path is not provided, the intersection shapefile will be saved in the same directory as the input feature shapefile
    output: the path of the intersection shapefile
    '''
    if intersection_path == "":
        intersection_path = generate_save_path(input_feature_path, "int")
    if os.path.exists(intersection_path):
        os.remove(intersection_path)
    intersection_params = {
        'INPUT' : input_feature_path,
        'INTERSECT' : compare_feature_path,
        'INPUT_FIELDS' : [],
        'INTERSECT_FIELDS' : [],
        'INTERSECT_FIELDS_PREFIX' : '',
        'OUTPUT' : intersection_path
    }
    if not run_processing_algorithm("native:lineintersections", intersection_params):
        return ""
    return intersection_path

def merge_layers(layer_list, EPSG_code, merged_path = ""):
    '''
    Use QGIS API to merge the input feature layer and the compare feature layer
    layer_list: the list of the feature shapefile
    EPSG_code: the EPSG code of the merged shapefile
    merged_path: the path of the merged shapefile
    '''
    if merged_path == "":
        merged_path = generate_save_path(layer_list[0], "m")
    if os.path.exists(merged_path):
        os.remove(merged_path)
    merge_params = {
        'LAYERS' : layer_list,
        'CRS' : QgsCoordinateReferenceSystem(f'EPSG:{EPSG_code}'),
        'OUTPUT' : merged_path
    }
    if not run_processing_algorithm("native:mergevectorlayers", merge_params):
        return ""
    return merged_path