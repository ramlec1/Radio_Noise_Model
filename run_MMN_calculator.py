"""This webapp is a tool to calculate the radio noise field strength at a given location.

It uses the MMN model to calculate the radio noise field strength at a given location.

It retreives the households from OpenStreetMap, calculates the propagation from each
noise source to the receiver, and sums the contributions to the total received power.

Marcel van den Broek, 2026
"""

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)