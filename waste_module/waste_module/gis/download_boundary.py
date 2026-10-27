from pathlib import Path
import osmnx as ox
import matplotlib.pyplot as plt

def main():
    print("=" * 60)
    print("Downloading Bengaluru Boundary from OpenStreetMap...")
    print("=" * 60)

    # Bengaluru location
    place_name = "Bengaluru, Karnataka, India"

    try:
        # Download boundary
        boundary = ox.geocode_to_gdf(place_name)

        print("\nBoundary downloaded successfully!")
        print(boundary[["display_name"]])

        # Create data folder if it doesn't exist
        data_folder = Path(__file__).resolve().parent.parent / "data"
        data_folder.mkdir(parents=True, exist_ok=True)

        # Output file
        output_file = data_folder / "bengaluru_boundary.geojson"

        # Save boundary
        boundary.to_file(output_file, driver="GeoJSON")

        print(f"\nBoundary saved at:\n{output_file}")

        # Plot boundary
        fig, ax = plt.subplots(figsize=(8, 8))
        boundary.plot(ax=ax, edgecolor="blue", facecolor="lightblue")
        plt.title("Bengaluru Boundary")
        plt.show()

        # Check whether file exists
        if output_file.exists():
            print("\n✅ GeoJSON file created successfully!")
        else:
            print("\n❌ File was not created.")

    except Exception as e:
        print("\nError occurred:")
        print(e)


if __name__ == "__main__":
    main()