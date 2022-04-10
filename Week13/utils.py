import requests
from shapely.geometry import Point
import geopandas as gpd
import pandas as pd
import osmnx as ox
import networkx as nx
import time
import ipywidgets as widgets
from IPython.display import display
import folium
import geocoder


def collect_point_of_interest(search_item, api_key, lng, lat):

    # Formulate the query for collecting POI
    api_address = r"https://maps.googleapis.com/maps/api/place/textsearch/json?"
    api_request = f"{api_address}&location={lat},{lng}&query={search_item}&key={api_key}"

    # Collect POI from Google Maps API
    api_response = requests.get(api_request).json()

    if (api_response['status'] == 'OK') & (bool(api_response['results'])):
        poi_gdf = gpd.GeoDataFrame(api_response['results'], crs='EPSG:4326')
        poi_gdf['geometry'] = poi_gdf.apply(lambda x: Point(x['geometry']['location']['lng'],
                                                            x['geometry']['location']['lat']),
                                            axis=1
                                            )


        # If the query results has more than one page (more than 20 pois)
        page_count = 1
        while 'next_page_token' in api_response:
            page_count += 1
            time.sleep(2)
            api_request_next_page = f'{api_request}&pagetoken={api_response["next_page_token"]}'

            api_response = requests.get(api_request_next_page).json()

            poi_gdf_next_page = gpd.GeoDataFrame(api_response['results'], crs='EPSG:4326')

            poi_gdf_next_page['geometry'] = poi_gdf_next_page.apply(lambda x: Point(x['geometry']['location']['lng'],
                                                                                    x['geometry']['location']['lat']),
                                                                    axis=1
                                                                    )

            poi_gdf = pd.concat([poi_gdf, poi_gdf_next_page], ignore_index=True)

            # If poi is more than 100, exit.
            if page_count == 5:
                break

        # print(f'Accumulated Counts of POI: {poi_gdf.shape[0]}')
        poi_gdf = poi_gdf.set_crs(epsg=4326)

    else:
        print("Error: Not able to retrieve data from Google Maps")
        print(f"Error Message: {api_response['status']}")
    
    if poi_gdf.shape[0] > 0:
        return poi_gdf
    else:
        return False


def remove_uncenessary_nodes(network):
    _nodes_removed = len([n for (n, deg) in network.out_degree() if deg == 0])
    network.remove_nodes_from([n for (n, deg) in network.out_degree() if deg == 0])
    for component in list(nx.strongly_connected_components(network)):
        if len(component) < 10:
            for node in component:
                _nodes_removed += 1
                network.remove_node(node)

    return network


def collect_road_network_from_OSM(location):
    network = ox.graph_from_place(location, network_type='drive', simplify=True)
    network = remove_uncenessary_nodes(network)
    
    return network


def find_nearest_osm(network, gdf):
    for idx, row in gdf.iterrows():
        if row.geometry.geom_type == 'Point':
            nearest_osm = ox.distance.nearest_nodes(network,
                                                    X=row.geometry.x,
                                                    Y=row.geometry.y
                                                    )
        elif row.geometry.geom_type == 'Polygon' or row.geometry.geom_type == 'MultiPolygon':
            nearest_osm = ox.distance.nearest_nodes(network,
                                                    X=row.geometry.centroid.x,
                                                    Y=row.geometry.centroid.y
                                                    )
        else:
            print(row.geometry.geom_type)
            continue

        gdf.at[idx, 'nearest_osm'] = nearest_osm

    return gdf


def calculate_service_area(gdf, network, dist):
    
    gdf = find_nearest_osm(network, gdf)

    nodes, edges = ox.graph_to_gdfs(network, nodes=True, edges=True, node_geometry=True)

    service_area = gpd.GeoDataFrame()
    for idx, row in gdf.iterrows():
        temp_nodes = nx.single_source_dijkstra_path_length(network, row['nearest_osm'], dist, weight='length')
        access_nodes = nodes.loc[nodes.index.isin(temp_nodes.keys()), 'geometry']
        temp_service_area = access_nodes.unary_union.convex_hull  # Create convex hull from the unioned nodes

        service_area.at[idx, 'geometry'] = temp_service_area

    service_area = service_area.set_crs(epsg=4326)

    return service_area


def show_results(gdf, network, dist, rating_val, rating_count, lng, lat):
    good_gdf = gdf.loc[(gdf['rating'] > rating_val) & (gdf['user_ratings_total'] > rating_count)]

    results_gdf = calculate_service_area(good_gdf, network, dist)

    if results_gdf.shape[0] > 0:
        # Initiate folium map
        final_result = folium.Map([lat, lng], zoom_start=11, tiles='Stamen Toner')

        # Service area of Grocery stores
        folium.GeoJson(results_gdf['geometry'].unary_union,
                       style_function=lambda feature: {
                           'fillColor': "green",
                           'color': "green",
                           'fillOpacity': 0.2,
                       }).add_to(final_result)

        # Location of Grocery stores
        folium.GeoJson(good_gdf['geometry'],
                       marker=folium.CircleMarker(radius=3,  # Radius in metres
                                                  weight=0,  # outline weight
                                                  fill_color='#006400',
                                                  fill_opacity=1)
                       ).add_to(final_result)

        return final_result

    else:
        print("Location not found!")

        return


def widget():
    style = {'description_width': 'initial'}

    w_loc = widgets.Text(
        value='Champaign County, IL',
        description='Location: ',
        style=style,
        disabled=False
    )

    w_poi = widgets.Text(
        value='Grocery Stores',
        description='Point of Interest: ',
        style=style,
        disabled=False
    )

    w_key = widgets.Text(
        value='',
        description='Google Maps API Key: ',
        style=style,
        disabled=False
    )

    w_dist = widgets.IntSlider(
        value=1000,
        min=500,
        max=3000,
        step=100,
        description='Max travel distance (in meters): ',
        style=style,
        continuous_update=False,
        orientation='horizontal',
        readout=True,
        layout=widgets.Layout(width='50%')
    )

    w_rate = widgets.FloatSlider(
        value=4,
        min=1,
        max=5,
        step=0.1,
        description='Minimum rating: ',
        style=style,
        readout=True,
        layout=widgets.Layout(width='50%')
    )

    w_count = widgets.IntSlider(
        value=10,
        min=1,
        max=100,
        step=1,
        description='Minimum review counts: ',
        style=style,
        readout=True,
        layout=widgets.Layout(width='50%')
    )

    display(w_loc)
    display(w_poi)
    display(w_key)
    display(w_dist)
    display(w_rate)
    display(w_count)

    button = widgets.Button(description="Submit")
    output = widgets.Output()

    display(button, output)

    def on_button_clicked(b):
        location = w_loc.value
        search_item = w_poi.value
        api_key = w_key.value
        distance = w_dist.value
        rating_min = w_rate.value
        rating_count_min = w_count.value

        with output:
            print(f"Your maximum travel distance to {search_item} is {distance} meters")
            print("Your accessible area is shown in green!")
            print("\n")

            loc = geocoder.google(location, key=api_key)

            latitude = loc.latlng[0]  # 40.115950
            longitude = loc.latlng[1]  # -88.241591

            print("#### STEP1: COLLECTING POI #### \n")
            poi_gdf = collect_point_of_interest(search_item, api_key, longitude, latitude)

            print("#### STEP2: COLLECTING ROAD NETWORK #### \n")
            G = collect_road_network_from_OSM(location)

            print("#### STEP3: CALCULATING SERVICE AREA #### \n")
            final_plot = show_results(poi_gdf, G, distance, rating_min, rating_count_min, longitude, latitude)

        display(final_plot)

    button.on_click(on_button_clicked)

