from geopy.geocoders import Nominatim
from geopy.location import Location
import pandas as pd


def main():
    geolocator = Nominatim(user_agent="south_sudan_city_finder")
    csv = pd.read_csv("../road_data/with_coords.csv")
    for i, city in enumerate(csv["name"]):
        if csv.loc[i, "lat"] != 0.0 and csv.loc[i, "lat"] is not None:
            continue
        try:
            query = {"city": city, "country": "South Sudan"}
            lat, lon = search(query, geolocator)
        except:
            try:
                query = {"amenity": city, "country": "South Sudan"}
                lat, lon = search(query, geolocator)
            except:
                lat, lon = (0, 0)
        finally:
            csv.loc[i, "lat"] = lat
            csv.loc[i, "lon"] = lon
    csv.to_csv("../road_data/with_coords2.csv")


def search(query: dict[str, str], geolocator: Nominatim) -> tuple[float, float]:
    print(query)
    location: Location = geolocator.geocode(query)
    lat = location.latitude
    lon = location.longitude
    return (lat, lon)


if __name__ == "__main__":
    main()
