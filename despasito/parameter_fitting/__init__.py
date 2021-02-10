"""
Fit Parameters
--------------

This package uses functions from input_output, equations_of_state, and thermodynamics to fit parameters to experimental data.

Input.json files have a different dictionary structure that is processed by :func:`~despasito.input_output.read_input.process_param_fit_inputs`

"""

import sys
import os
import numpy as np
from importlib import import_module
import logging

from . import fit_funcs as ff
from . import data_classes

logger = logging.getLogger(__name__)

def fit( optimization_parameters=None, exp_data=None, global_opts={}, minimizer_opts=None, MultiprocessingObject=None, **thermo_dict):
    r"""
    Fit defined parameters for equation of state object with given experimental data. 

    Each set of experimental data is converted to an object with the built in ability to evaluate its part of objective function.
    To add another type of supported experimental data, add a class to the fit_classes.py file.

    Parameters
    ----------
    thermo_dict : dict
        Dictionary of instructions for thermodynamic calculations and parameter fitting.

        - optimization_parameters (dict) - Parameters used in global fitting algorithm.

            - fit_bead (str) - Name of bead whose parameters are being fit, should be in bead list of bead_configuration
            - fit_params (list[str]) - This list of contains the name of the parameter being fit (e.g. epsilon). See EOS documentation for supported parameter names. Cross interaction parameter names should be composed of parameter name and the other bead type, separated by an underscore (e.g. epsilon_CO2).
            - beadparams0 (list[float]), Optional - Initial guess in parameter. If one is not provided, a guess is made based on the type of parameter from Eos object.
            - \*_bounds (list[float]), Optional - This list contains the minimum and maximum of the parameter from a parameter listed in fit_params, represented in place of the asterisk. See input file instructions for more information.

        - exp_data (dict) - This dictionary is made up of a dictionary for each data set that the parameters are fit to. Each dictionary is converted into an object and saved back to this structure before parameter fitting begins. Each key is an arbitrary string used to identify the data set and used later in reporting objective function values during the fitting process. See data type objects for more details.

            - data_class_type (str) - One of the supported data type objects to fit parameters
            - eos_obj (obj) - Equation of state output that writes pressure, max density, chemical potential, updates parameters, and evaluates objective functions. For parameter fitting algorithm See equation of state documentation for more details.

        - global_opts (dict), Optional - kwargs used in global optimization method. See :func:`~despasito.parameter_fitting.fit_funcs.global_minimization`.

            - method (str), Optional - default: 'differential_evolution', Global optimization method used to fit parameters. See :func:`~despasito.parameter_fitting.fit_funcs.global_minimization`.
            - Additional options, specific to global_optimizaiton method

        - minimizer_opts (dict), Optional - Dictionary used to define minimization type and the associated options.

            - method (str) - Method available to scipy.optimize.minimize
            - options (dict) - This dictionary contains the kwargs available to the chosen method
  
    Returns
    -------
    Output file saved in current working directory
    """

    # Extract relevant quantities from thermo_dict
    dicts = {}

    # Extract inputs
    if optimization_parameters == None:
        raise ValueError("Required input, optimization_parameters, is missing.")

    dicts['global_opts'] = global_opts
    if minimizer_opts != None:
        dicts['minimizer_opts'] =  minimizer_opts

    if exp_data == None:
        raise ValueError("Required input, exp_data, is missing.")

    # Add multiprocessing object to exp_data objects and global_optss
    if MultiprocessingObject != None:
        for k2 in list(exp_data.keys()):
            exp_data[k2]["MultiprocessingObject"] = MultiprocessingObject
        dicts['global_opts']["MultiprocessingObject"] = MultiprocessingObject

    # Thermodynamic options and optimizaiton options are added to data object
    for k2 in list(exp_data.keys()):
        for key, value in thermo_dict.items():
            if key not in exp_data[k2]:
                exp_data[k2][key] = value

    # Generate initial guess and bounds for parameters if none was given
    optimization_parameters = ff.consolidate_bounds(optimization_parameters)
    if "bounds" in optimization_parameters:
        bounds = optimization_parameters["bounds"]
        del optimization_parameters['bounds']
    else:
        bounds = np.zeros((len(optimization_parameters["fit_params"]),2))
    Eos = exp_data[list(exp_data.keys())[0]]["eos_obj"] # since all exp data sets use the same Eos, it doesn't really matter
    bounds = ff.check_parameter_bounds(optimization_parameters, Eos, bounds)

    if "beadparams0" in optimization_parameters:
        beadparams0 = optimization_parameters["beadparams0"]
        if len(beadparams0) != len(optimization_parameters["fit_params"]):
            raise ValueError("The number of initial parameters given isn't the same number of parameters to be fit.")
    else:
        beadparams0 = ff.initial_guess(optimization_parameters, Eos)
    logger.info("Initial guess in parameters: {}".format(beadparams0))

    # _________________________________________________________

    # Reformat exp. data into formatted dictionary
    exp_dict = {}
    pkgpath = os.path.dirname(data_classes.__file__)
    type_list = [f for f in os.listdir(pkgpath) if ".py" in f]
    type_list = type_list.remove("__init__.py")

    for key, data_dict in exp_data.items():
        fittype = data_dict["data_class_type"]
        try:
            exp_module = import_module("."+fittype,package="despasito.parameter_fitting.data_classes")
            data_class = getattr(exp_module, "Data")
        except:
            if not type_list:
                raise ImportError("No fit types")
            elif len(type_list) == 1:
                tmp = type_list[0]
            else:
                tmp = ", ".join(type_list)
            raise ImportError("The experimental data type, '{}', was not found\nThe following calculation types are supported: {}".format(fittype,tmp))

        try:
            instance = data_class(data_dict)
            exp_dict[key] = instance
            logger.info("Initiated exp. data object: {}".format(instance.name))
        except:
            raise AttributeError("Data set, {}, did not properly initiate object".format(key))

    # Check global optimization method
    if "method" in dicts['global_opts']:
        global_method = dicts['global_opts']["method"]
        del dicts['global_opts']["method"]
    else:
        global_method = "differential_evolution"

    # Run Parameter Fitting
    try:
        result = ff.global_minimization(global_method, beadparams0, bounds, optimization_parameters["fit_bead"], optimization_parameters["fit_params"], exp_dict, **dicts)

        logger.info("Fitting terminated:\n{}".format(result.message))
        logger.info("Best Fit Parameters")
        logger.info("    Obj. Value: {}".format(result.fun))
        for i in range(len(optimization_parameters["fit_params"])):
            logger.info("    {} {}: {}".format(optimization_parameters["fit_bead"],optimization_parameters["fit_params"][i],result.x[i]))

    except:
        raise TypeError("The parameter fitting failed")

    return {"fit_bead": optimization_parameters["fit_bead"], "fit_parameters":optimization_parameters["fit_params"], "final_parameters": result.x, "objective_value": result.fun} 

