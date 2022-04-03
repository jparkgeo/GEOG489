from tqdm import tqdm, trange
import osmnx as ox
import networkx as nx
from shapely.ops import cascaded_union
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
import numpy as np


def assign_max_speed_with_highway_type(row_):
    """
    Assign the maximum speed of an edge based on its attribute 'highway'
    # https://wiki.openstreetmap.org/wiki/Key:highway

    Args:
        row_: (dict) a row of OSMnx network data

    Returns:
        temp_speed_: (int) the maximum speed of an edge

    """

    max_speed_per_type = {'motorway': 50,
                          'motorway_link': 30,
                          'trunk': 50,
                          'trunk_link': 30,
                          'primary': 40,
                          'primary_link': 30,
                          'secondary': 40,
                          'secondary_link': 30,
                          'tertiary': 40,
                          'tertiary_link': 20,
                          'residential': 30,
                          'living_street': 20,
                          'unclassified': 20
                          }

    # if the variable is a list, obtain just the first one.
    if type(row_['highway']) == list:
        road_type = row_['highway'][0]
    else:
        road_type = row_['highway']

    # If the maximum speed of the road_type is predefined.
    if road_type in max_speed_per_type.keys():
        temp_speed_ = max_speed_per_type[road_type]
    else:  # If not defined, just use 20 mph.
        temp_speed_ = 20

    return temp_speed_


def network_settings(network):
    for u, v, k, data in network.edges(data=True, keys=True):
        if 'maxspeed' in data.keys():
            if type(data['maxspeed']) == list:
                temp_speed = data['maxspeed'][0]  # extract only numbers
            else:
                temp_speed = data['maxspeed']

            temp_speed = temp_speed.split(' ')[0]

        else:
            temp_speed = assign_max_speed_with_highway_type(data)

        data['maxspeed'] = temp_speed
        data['maxspeed_meters'] = int(data['maxspeed']) * 26.8223  # MPH * 1.6 * 1000 / 60; meter per minute
        data['time'] = float(data['length'] / data['maxspeed_meters'])

    # create point geometries for the entire graph
    for node, data in network.nodes(data=True):
        data['geometry'] = Point(data['x'], data['y'])

    return network


def step1_E2SFCA(supply, supply_attr, demand, demand_attr, mobility, thresholds, weights):
    """
    Input:
    - supply (GeoDataFrame): stores locations and attributes of supply
    - supply_attr (str): the column of `supply` to be used for the analysis
    - demand (GeoDataFrame): stores locations and attributes of demand
    - demand_attr (str): the column of `demand` to be used for the analysis
    - mobility (NetworkX MultiDiGraph): Network Dataset obtained from OSMnx
    - thresholds (list): the list of threshold travel times e.g., [5, 10, 15]
    - weights (dict): keys: threshold travel time, values: weigths according to the threshold travel times
                      e.g., [5: 1, 10: 0.68, 15: 0.22]

    Output:
    - supply_ (GeoDataFrame):
      a copy of supply and it stores supply-to-demand ratio of each supply at `ratio` column
    """

    # Your code here (Change the name of the variable according to the inputs)
    supply_ = supply.copy(deep=True)
    supply_['ratio'] = 0

    for i in trange(supply.shape[0]):

        # Create catchment areas from a given location
        ctmt_area = calculate_catchment_area(mobility, supply.loc[i, 'nearest_osm'], thresholds)

        # Calculate the population within the catchment area based on distance decay
        ctmt_area_pops = 0
        for c_idx, c_row in ctmt_area.iterrows():
            temp_pop = demand.loc[demand['geometry'].centroid.within(c_row['geometry']), demand_attr].sum()
            ctmt_area_pops += temp_pop * weights[c_idx]

        # Calculate the number of hospital beds in each hospital
        temp_supply = supply.loc[i, supply_attr]

        # Calculate the number of hospital beds available for 100,000 people
        supply_.at[i, 'ratio'] = temp_supply / ctmt_area_pops * 100000

    return supply_


def step2_E2SFCA(result_step1, demand, mobility, thresholds, weights):
    """
    Input:
    - result_step1 (GeoDataFrame): stores locations and 'ratio' attribute that resulted in step1
    - demand (GeoDataFrame): stores locations and attributes of demand
    - mobility (NetworkX MultiDiGraph): Network Dataset obtained from OSMnx
    - thresholds (list): the list of threshold travel times e.g., [5, 10, 15]
    - weights (dict): keys: threshold travel time, values: weigths according to the threshold travel times
                      e.g., [5: 1, 10: 0.68, 15: 0.22]

    Output:
    - demand_ (GeoDataFrame):
      a copy of demand and it stores the final accessibility measures of each demand location at `ratio` column
    """

    # Your code here (Change the name of the variable according to the inputs)
    demand_ = demand.copy(deep=True)
    demand_['access'] = 0

    for j in trange(demand.shape[0]):

        # Create catchment areas from a given location
        ctmt_area = calculate_catchment_area(mobility, demand.loc[j, 'nearest_osm'], thresholds)

        # Sum the ratio within the catchment areas based on distance decay
        ctmt_area_ratio = 0
        for c_idx, c_row in ctmt_area.iterrows():
            temp_ratio = result_step1.loc[result_step1['geometry'].centroid.within(c_row['geometry']), 'ratio'].sum()
            ctmt_area_ratio += temp_ratio * weights[c_idx]

        # Assign the summed ratio for each demand location
        demand_.at[j, 'access'] = ctmt_area_ratio

    return demand_


def calculate_catchment_area(network, nearest_osm, minutes, distance_unit='time'):
    polygons = gpd.GeoDataFrame(crs="EPSG:4326")

    # Create convex hull for each travel time (minutes), respectively.
    for minute in minutes:
        access_nodes = nx.single_source_dijkstra_path_length(network, nearest_osm, minute, weight=distance_unit)
        convex_hull = gpd.GeoSeries(nx.get_node_attributes(network.subgraph(access_nodes), 'geometry')).unary_union.convex_hull
        polygon = gpd.GeoDataFrame({'minutes': [minute], 'geometry': [convex_hull]}, crs="EPSG:4326")
        polygon = polygon.set_index('minutes')
        polygons = polygons.append(polygon)

    # Calculate the differences between convex hulls which created in the previous section.
    polygons_ = polygons.copy(deep=True)
    for idx, minute in enumerate(minutes):
        if idx != 0:
            current_polygon = polygons.loc[[minute]]
            previous_polygons = cascaded_union(polygons.loc[minutes[:idx], 'geometry'])
            previous_polygons = gpd.GeoDataFrame({'geometry': [previous_polygons]}, crs="EPSG:4326")
            diff_polygon = gpd.overlay(current_polygon, previous_polygons, how="difference")
            if diff_polygon.shape[0] != 0:
                polygons_.at[minute, 'geometry'] = diff_polygon['geometry'].values[0]

    return polygons_.copy(deep=True)




def extract_edges_nodes_from_networkx(network):
    nodes, edges = ox.graph_to_gdfs(network, nodes=True, edges=True, node_geometry=True)

    return nodes, edges


def step1_2SFCA(supply, supply_attr, demand, demand_attr, mobility, threshold):
    """
    Input:
    - supply (GeoDataFrame): stores locations and attributes of supply
    - supply_attr (str): the column of `supply` to be used for the analysis
    - demand (GeoDataFrame): stores locations and attributes of demand
    - demand_attr (str): the column of `demand` to be used for the analysis
    - mobility (NetworkX MultiDiGraph): Network Dataset obtained from OSMnx
    - threshold (int): threshold travel distance

    Output:
    - supply_ (GeoDataFrame):
      a copy of supply and it stores supply-to-demand ratio of each supply at `ratio` column
    """

    # Extract the nodes and edges of the network dataset for the future analysis.
    nodes, edges = extract_edges_nodes_from_networkx(mobility)

    supply_ = supply.copy(deep=True)
    supply_['ratio'] = 0

    for i in trange(supply.shape[0]):
        # Create a catchment area from a given location
        temp_nodes = nx.single_source_dijkstra_path_length(mobility, supply.loc[i, 'nearest_osm'], threshold,
                                                           weight='length')
        access_nodes = nodes.loc[nodes.index.isin(temp_nodes.keys()), 'geometry']
        access_nodes = gpd.GeoSeries(access_nodes.unary_union.convex_hull, crs="EPSG:5070")

        # Calculate the population within the catchment area
        temp_demand = demand.loc[demand['geometry'].centroid.within(access_nodes[0]), demand_attr].sum()

        # Calculate the number of hospital beds in each hospital
        temp_supply = supply.loc[i, supply_attr]

        # Calculate the number of hospital beds available for 100,000 people
        supply_.at[i, 'ratio'] = temp_supply / temp_demand * 100000

    supply_['ratio'].replace(np.inf, 0, inplace=True)

    return supply_


def step2_2SFCA(result_step1, demand, mobility, threshold):
    """
    Input:
    - result_step1 (GeoDataFrame): stores locations and 'ratio' attribute that resulted in step1
    - demand (GeoDataFrame): stores locations and attributes of demand
    - mobility (NetworkX MultiDiGraph): Network Dataset obtained from OSMnx
    - threshold (int): threshold travel distance

    Output:
    - demand_ (GeoDataFrame):
      a copy of demand and it stores the final accessibility measures of each demand location at `ratio` column
    """

    # Extract the nodes and edges of the network dataset for the future analysis.
    nodes, edges = extract_edges_nodes_from_networkx(mobility)

    demand_ = demand.copy(deep=True)
    demand_['access'] = 0

    for j in trange(demand.shape[0]):
        temp_nodes = nx.single_source_dijkstra_path_length(mobility, demand.loc[j, 'nearest_osm'], threshold,
                                                           weight='length')
        access_nodes = nodes.loc[nodes.index.isin(temp_nodes.keys()), 'geometry']
        access_nodes = gpd.GeoSeries(access_nodes.unary_union.convex_hull, crs="EPSG:5070")

        accum_ratio = result_step1.loc[result_step1['geometry'].within(access_nodes[0]), 'ratio'].sum()
        demand_.at[j, 'access'] = accum_ratio

    return demand_

