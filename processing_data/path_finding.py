import osmnx as ox
import geopandas as gpd

lat1 = 5.6125
lon1 = 27.4742
lat2 = 4.5750
lon2 = 28.4037

# Get the road network graph
ox.settings.log_console = True
G = ox.graph_from_bbox(bbox=(lon2, lat2, lon1, lat1), network_type="drive")

# Find shortest path between coordinates
origin = ox.nearest_nodes(G, X=lon1, Y=lat1)
destination = ox.nearest_nodes(G, X=lon2, Y=lat2)
route = ox.shortest_path(G, origin, destination)

# Convert to GeoDataFrame
route_lines = [
    G.edges[route[i], route[i + 1], 0]["geometry"] for i in range(len(route) - 1)
]
road_gdf = gpd.GeoDataFrame(geometry=route_lines, crs="EPSG:4326")
road_gdf.to_file("segment.geojson", driver="GeoJSON")
# import overpass
# import geopandas as gpd
# from shapely.geometry import Point, LineString
#
# # Define your coordinates
# start = (lat1, lon1)
# end = (lat2, lon2)
#
# # Query OSM for roads between these points
# api = overpass.API()
# query = f"""
# [bbox:{start[1]},{start[0]},{end[1]},{end[0]}];
# (way["highway"];);
# out geom;
# """
# response = api.get(query, responseformat="json")
# roads_gdf = gpd.GeoDataFrame.from_features(response["features"])
