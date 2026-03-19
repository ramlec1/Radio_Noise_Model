''' ITU 368 Groundwave Propagation
This script computes the groundwave propagation using the C++ ITU 368 model in 
a python wrapper.
Marcel van den Broek, 2025'''

import numpy as np
from ctypes import c_double, c_int, POINTER, Structure, CDLL, WinDLL, byref
import os
from concurrent.futures import ThreadPoolExecutor


class LFMFError(Exception):
    pass

class Result(Structure):
    ''' Class containing the data returned from a C-function in the form of a
    C-struct. Class is used in the lfmf function as the return variable.'''
    _fields_ = [('A_btl__db', c_double),
                ('E_dBuVm', c_double),
                ('P_rx__dbm', c_double),
                ('method', c_int)]
    
class ITU368Grwave:
    ''' Class to compute the groundwave propagation using the C++ ITU 368 model.'''
    def __init__(self):
        # Load the shared library
        if os.name == 'posix':
            # Linux or Mac
            lib_path = os.path.join(os.path.dirname(__file__), 'ITU368_grwave.so')
            self.lfmf_lib = CDLL(lib_path)  
        else:
            # Windows
            lib_path = os.path.join(os.path.dirname(__file__), 'ITU368_grwave.dll')
            self.lfmf_lib = WinDLL(lib_path)
        # Define the argument and return types of the function
        self.lfmf_lib.LFMF.argtypes = [c_double, c_double, c_double, c_double,
                                       c_double, c_double, c_double, c_double, 
                                       c_int, POINTER(Result)]
        self.lfmf_lib.LFMF.restype = c_int

    def run(self, h_tx__meter, h_rx__meter, f__mhz, P_tx__watt, N_s, d__km, epsilon, sigma, pol):
        ''' 
        Function to call the C++ LFMF function and compute groundwave propagation. 

        Parameters:
            h_tx__meter: TX height [m]: 0 ≤ h_tx__meter ≤ 50
            h_rx__meter: RX height [m]: 0 ≤ h_rx__meter ≤ 50
            f__mhz: Frequency [MHz]: 0.01 ≤ f__mhz ≤ 30
            P_tx__watt: TX power [W]: 0 < P_tx__watt
            N_s: Surface refractivity [N-units]: 250 ≤ N_s ≤ 400
            d__km: Distance [km]: d__km ≤ 10 000
            epsilon: Relative permittivity earth surface: 1 ≤ epsilon
            sigma: Conductivity earth surface [S/m]: 0 < sigma
            pol: Polarization: 0 = horizontal, 1 = vertical

        Returns:
            A_btl__db: Basic transmission loss [dB]
            E_dBuVm: Electric field strength [dBuV/m]
            P_rx__dbm: Received power [dBm]
            method: Method used for calculation (0 = Flat Earth with curve correction, 1 = Residue series)
        '''

        # Create an instance of the Result structure
        res = Result()

        # Call the function
        status = self.lfmf_lib.LFMF(h_tx__meter, 
                                h_rx__meter, 
                                f__mhz, 
                                P_tx__watt,
                                N_s,
                                d__km,
                                epsilon,
                                sigma,
                                pol,
                                byref(res))
        
            # Check the status and print the results
        if status == 0:
            return (res.A_btl__db, res.E_dBuVm, res.P_rx__dbm, res.method)
        else:
            error_messages = {
                1000: "VALIDATION ERROR: h_tx__meter out of range",
                1001: "VALIDATION ERROR: h_rx__meter out of range",
                1002: "VALIDATION ERROR: f__mhz out of range",
                1003: "VALIDATION ERROR: P_tx__watt out of range",
                1004: "VALIDATION ERROR: N_s out of range",
                1005: "VALIDATION ERROR: d__km out of range",
                1006: "VALIDATION ERROR: epsilon out of range",
                1007: "VALIDATION ERROR: sigma out of range",
                1008: "VALIDATION ERROR: invalid value for pol"
            }
            msg = error_messages.get(status, "UNKNOWN ERROR")
            raise LFMFError(f"Error code {status}: {msg}")
        
    def evaluate_distances(self, h_tx__meter, h_rx__meter, f__mhz, P_tx__watt, N_s, distances, epsilon, sigma, pol, result_index=0, max_workers=None):
        """
        Evaluate the propagation model for a range of distances in parallel using threads.

        Parameters:
            h_tx__meter, h_rx__meter, f__mhz, P_tx__watt, N_s, epsilon, sigma, pol: model parameters (same as in run)
            distances: iterable of distances [km]
            result_index: which value to return from the result tuple (default: 0 = A_btl__db)
            max_workers: number of threads (default: as many as CPUs)

        Returns:
            List of results (e.g., A_btl__db for each distance)
        """
        def compute_loss(d):
            try:
                return self.run(h_tx__meter, h_rx__meter, f__mhz, P_tx__watt, N_s, d, epsilon, sigma, pol)[result_index]
            except LFMFError as e:
                print(f"Error occurred for distance {d} km: {e}")
                return np.nan

        # Parallel computation using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = list(executor.map(compute_loss, distances))
        return results
    

def main():
    # Define the input parameters
    h_tx__meter = 2.        # TX height [m]: 0 ≤ h_tx__meter ≤ 50
    h_rx__meter = 2.        # RX height [m]: 0 ≤ h_rx__meter ≤ 50
    f__mhz      = 0.01      # Frequency [MHz]: 0.01 ≤ f__mhz ≤ 30
    P_tx__watt  = 1e3       # TX power [W]: 0 < P_tx__watt
    N_s         = 350.      # Surface refractivity [N-units]: 250 ≤ N_s ≤ 400
    d__km       = 100.      # Distance [km]: d__km ≤ 10 000
    epsilon     = 80.       # Relative permittivity earth surface: 1 ≤ epsilon
    sigma       = 1.        # Conductivity earth surface [S/m]: 0 < sigma
    pol         = 1         # Polarization: 0 = horizontal, 1 = vertical 
    
    # create an instance of the ITU368Grwave class
    grwave = ITU368Grwave()

    # run the grwave function
    result = grwave.run(h_tx__meter, h_rx__meter, f__mhz, P_tx__watt, N_s, d__km, epsilon, sigma, pol)

    # print the results
    print(f"A_btl__db: {result[0]}")
    print(f"E_dBuVm: {result[1]}")
    print(f"P_rx__dbm: {result[2]}")
    print(f"Method: {result[3]}")

    # Verify the implementation against the figures in report ITU-R P.368-10 Figure 1
    # Compute the transmission loss for a range of distances using parallel processing
    import matplotlib.pyplot as plt
    distances = np.geomspace(1, 10000, 300) # [km]
    frequencies = np.array([0.01, 0.015, 0.02, 0.03, 0.04, 0.05, 0.075, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.75, 1., 1.5, 2., 3., 4., 5., 7.5, 10., 15., 20., 30.]) # [MHz]
    for f__mhz in frequencies:
        results = grwave.evaluate_distances(h_tx__meter, h_rx__meter, f__mhz, P_tx__watt, N_s, distances, epsilon, sigma, pol, result_index=1)
        plt.plot(distances, results, label=f'{f__mhz} MHz')
    plt.grid()
    plt.ylim(-30, 120)
    plt.xscale('log')
    plt.xlabel('Distance [km]')
    plt.ylabel('Electric field strength [dBuV/m]')
    plt.title('ITU 368 Groundwave Propagation - Verification against ITU-R P.368-10 Figure 1')
    plt.legend()
    plt.show()


if __name__ == "__main__": 
    main()