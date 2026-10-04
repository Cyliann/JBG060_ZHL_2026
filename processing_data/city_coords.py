from geopy.geocoders import Nominatim
from geopy.location import Location
import pandas as pd


def main():
    geolocator = Nominatim(user_agent="south_sudan_city_finder")
    csv = pd.read_csv("../raw_data/roads_network_South_Sudan/with_coords.csv")
    for i, city in enumerate(csv["name"]):
        if csv.loc[i, "lat"] != 0.0:
            continue
        query = {"city": city, "country": "South Sudan"}
        try:
            location = search(query, geolocator)
            if location is None:
                continue
            # except KeyError:
            #     try:
            #         query = {"amenity": city, "country": "South Sudan"}
            #         lat, lon = search(query, geolocator)
            #     except:
            #         lat, lon = (0, 0)
            csv.loc[i, "lat"] = location.latitude
            csv.loc[i, "lon"] = location.longitude
        finally:
            csv.to_csv("../raw_data/roads_network_South_Sudan/with_coords.csv")


def search(query: dict[str, str], geolocator: Nominatim) -> Location:
    print(query)
    location: Location = geolocator.geocode(query)
    return location


if __name__ == "__main__":
    main()
