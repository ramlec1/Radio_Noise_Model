# Man-made radio noise model
**Author:** Marcel van den Broek, 2026

A web application that calculates radio noise field strength at a given location using the **MMN (Man-Made Noise) model**. The tool retrieves household locations from OpenStreetMap, treats each as a noise source, and computes the total received power at a receiver using relevant propagation model(s).



---

## Usage

Run the Flask application:

```bash
python run_MMN_calculator.py
```

The server starts at **http://0.0.0.0:5000** (accessible on your network). Open a browser and navigate to `http://localhost:5000`.

---

# Assumptions
- **Uniform smooth environment:** Environmental conditions are uniform and constant. For example, ground wave propagation depends on earth surface conditions. These conditions may vary over the propagation path. This model will only consider one set of environmental conditions given as input and apply it over all paths. Clutter is not considered by ITU-R P.368-13.
- **Households only:** Only noise sources in households are considered. No cars, high voltage power lines, etc.
- **OSM data completeness:** Only OSM objects with addr:housenumber are used. Missing or incomplete tags will lead to underestimation of noise levels. This can be checked on the map however.
- **Uniform antenna height:** Antenna height (source and receiver) can be configured, but is a constant value for all antennas.
- **Uniform wide-band power spectral density:** Source power is the same for all sources and applies to the frequency submitted. 
- **Single Frequency:** A single frequency is used in the calculations instead of considering a frequency band.
- **Radius of significance:** RoS can be used to define the distance up to which noise sources provide a significant contribution to the predicted level. A mathematical derivation of the RoS is given in a separate document (ask author). For now the RoS is not calculated, but a manual value of the radius under consideration is provided.
- **Far-field condition:** The receiver must be in the far field of each source. If a household is too close (`r ≤ c₀ / (2f)`), a `NearFieldError` is raised. This equation comes from the Fraunhofer criterion `r > 2 D**2 / λ` with an assumed antenna dimension of `D=λ/2`.
- **Incoherent addition:** Contributions are summed in linear power (e.g. total_power += db_to_rat(contribution)). This assumes uncorrelated, incoherent noise sources.
- **Polarization:** The polarization is currently hardcoded to be vertical only.


---

## Technical Notes

- **Coordinate system:** Household positions are converted from WGS84 to local Cartesian (meters) using GeographicLib for accurate geodesic distances.
- **Overpass API:** The app uses public Overpass endpoints; large radii may hit timeouts.
- **ITU-R P.368-13:** The C++ source code has some MSVC compiler specific code. Compiling it into a .so shared library resulted in errors or wrong calculations. Therefore, only the .dll implementation for windows is available at this moment.

---

## Current features

- **Interactive map** – Choose a receiver location by entering coordinates or clicking on the map
- **OpenStreetMap integration** – Automatically fetches households with `addr:housenumber` within a configurable search radius (1 m – 100 km) and visually displays the retrieved household locations on the map for verification.
- **ITU-R P.368-13 propagation** – Currently only uses groundwave propagation for frequencies 0.01–30 MHz. This is a wrapper of the official ITU-R P.368-13 C++ code of the groundwave propagation model. The model enforces the range limits of the input parameters.

---

## To Do
- **Verification:** The model needs to be verified with measurement data from the ITU Radio Noise Databank. Verification with other measurement sources is also possible.
- **Propagation models:** Include more propagation models (e.g. P.2001, P.452, P.1411, P.684, etc.). Find a skywave solution (P.532, P.581, P.1147, P.1239, P.1240). Find a suitable propagation model for near-field situations.
- **Statistics:** Include statistical distributions in source power, source density per household, and antenna
height, etc. (like seamcat)
- **Source Characteristics:** Provide guidance on source power (e.g. from EMC limits, papers on average device density per household, wall attenuation ITU-R P.2040, etc.)
