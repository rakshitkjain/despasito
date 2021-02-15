"""
    This thermo module contains a series of wrappers to handle the inputs and outputs of these functions. The `calc` module contains the thermodynamic calculations. Calculation of pressure, chemical potential, and max density are handled by an eos object so that these functions can be used with any EOS.
    
    None of the functions in this folder need to be handled directly, as a function factory is included in our __init__.py file. Add "from thermodynamics import thermo" and use "thermo("calc_type",eos,input_dict)" to get started.
    
"""

import numpy as np
import logging

from despasito.utils.parallelization import MultiprocessingJob
from . import calc
from despasito import fund_constants as constants

logger = logging.getLogger(__name__)

######################################################################
#                                                                    #
#                Phase Equilibrium given xi and T                    #
#                                                                    #
######################################################################
def phase_xiT(eos, **sys_dict):

    r"""
    Calculate phase diagram given liquid mole fractions, xi, and temperature.

    Input and system information are assessed first. An output file is generated with T, xi, and corresponding P and yi.
    
    Parameters
    ----------
    eos : obj
        An instance of the defined EOS class to be used in thermodynamic computations.
    sys_dict: kwargs, Optional

        - Tlist: (list[float]) Optional - default 298.15 [K] Temperature of the system corresponding to composition in xilist. If one set is given, this temperature will be used for all compositions.
        - xilist: (list[list[float]]) - List of sets of component mole fraction, where sum(xi)=1.0 for each set. Each set of components corresponds to a temperature in Tlist, or if one set is given, this composition will be used for all temperatures.
        - Pguess: (list[float]) - [Pa] Optional, Guess the system pressure at the dew point. A value of None will force an estimation based on the saturation pressure of each component.
        - Pmin: (list[float]) - [Pa] Optional, Set the upper bound for the minimum system pressure at the dew point. If not defined, the default in :func:`~despasito.thermodynamics.calc_xT_phase` is used.
        - Pmax: (list[float]) - [Pa] Optional, Set the upper bound for the maximum system pressure at the dew point. If not defined, the default in :func:`~despasito.thermodynamics.calc_xT_phase` is used.
        - method: (str) Optional - Solving method for outer loop that converges pressure. If not given the :func:`~despasito.thermodynamics.calc_xT_phase` default will be used.
        - pressure_options: (dict) Optional - Keyword arguments used in the given method, "method" from :func:`~despasito.utils.general_toolbox.solve_root`, to solve the outer loop in the solving algorithm
        - mole_fraction_options: (dict) Optional - Keywords used to solve the mole fraction loop in :func:`~despasito.thermodynamics.calc.solve_yi_xiT`
        - density_dict: (dict) Optional - Other keyword options for density array :func:`~despasito.thermodynamics.calc.PvsRho` 

    Returns
    -------
    output_dict : dict
        Output of dictionary containing given and calculated values    
    """

    #computes P and yi from xi and T

    ## Extract and check input data
    if 'Tlist' in sys_dict:
        T_list = np.array(sys_dict['Tlist'],float)
        logger.info("Using Tlist") 
        del sys_dict['Tlist']
    else:
        T_list = np.array([constants.standard_temperature])
        logger.info("Assuming standard temperature")

    if 'xilist' in sys_dict:
        xi_list = np.array(sys_dict['xilist'],float)
        logger.info("Using xilist")
        del sys_dict['xilist']
    else:
        raise ValueError('Mole fractions, xilist, are not specified')

    if 'mpObj' in sys_dict:
        mpObj = sys_dict['mpObj']
        flag_use_mp_object = True
        del sys_dict['mpObj']
    else:
        flag_use_mp_object = False

    if np.size(T_list) != np.size(xi_list, axis=0):
        if len(T_list) == 1:
            T_list = np.ones(len(xi_list))*T_list[0]
            logger.info("The same temperature, {}, was used for all mole fraction values".format(T_list[0]))
        elif len(xi_list) == 1:
            xi_list = np.array([xi_list[0] for i in range(len(T_list))])
            logger.info("The same composition, {}, was used for all temperature values".format(xi_list[0]))
        else:
            raise ValueError("The number of provided temperatures and mole fraction sets are different")

    ## Optional values
    opts = {}

    # Process initial guess in pressure
    if 'Pguess' in sys_dict:
        Pguess = np.array(sys_dict['Pguess'],float)
        del sys_dict['Pguess']
        if not len(np.shape(Pguess)):
            Pguess = np.array([Pguess])
        if np.size(T_list) != np.size(Pguess):
            if len(Pguess) == 1:
                opts["Pguess"] = np.ones(len(T_list))*float(Pguess[0])
                logger.info("The same pressure, {}, was used for all mole fraction values".format(Pguess))
            else:
                raise ValueError("The number of provided pressure and mole fraction sets are different")
        else:
            opts["Pguess"] = Pguess
        logger.info("Using user defined initial guess has been provided")

    if 'Pmin' in sys_dict:
        Pmin = np.array(sys_dict['Pmin'],float)
        del sys_dict['Pmin']
        if not len(np.shape(Pmin)):
            Pmin = np.array([Pmin])
        if np.size(T_list) != np.size(Pmin):
            if len(Pmin) == 1:
                opts["Pmin"] = np.ones(len(T_list))*float(Pmin[0])
                logger.info("The same min pressure, {}, was used for all mole fraction values".format(Pmin))
            else:
                raise ValueError("The number of provided pressure and mole fraction sets are different")
        else:
            opts["Pmin"] = Pmin
        logger.info("Using user defined min pressure")

    if 'Pmax' in sys_dict:
        Pmax = np.array(sys_dict['Pmax'],float)
        del sys_dict['Pmax']
        if not len(np.shape(Pmax)):
            Pmax = np.array([Pmax])
        if np.size(T_list) != np.size(Pmax):
            if len(Pmax) == 1:
                opts["Pmax"] = np.ones(len(T_list))*float(Pmax[0])
                logger.info("The same max pressure, {}, was used for all mole fraction values".format(Pmax))
            else:
                raise ValueError("The number of provided pressure and mole fraction sets are different")
        else:
            opts["Pmax"] = Pmax
        logger.info("Using user defined max pressure")

    opts.update(sys_dict) # Add unprocessed options

    ## Calculate P and yi
    per_job_var = ["Pmin","Pmax","Pguess"]
    inputs = []
    for i in range(len(T_list)):
        opts_tmp = opts.copy()
        for key in per_job_var:
            if key in opts_tmp:
                opts_tmp[key] = opts_tmp[key][i]
        inputs.append((T_list[i], xi_list[i], eos, opts_tmp))

    if flag_use_mp_object:
        P_list, yi_list, flagv_list, flagl_list, obj_list = mpObj.pool_job(_phase_xiT_wrapper, inputs)
    else:
        P_list, yi_list, flagv_list, flagl_list, obj_list = MultiprocessingJob.serial_job(_phase_xiT_wrapper, inputs)

    logger.info("--- Calculation phase_xiT Complete ---")

    return {"T":T_list,"xi":xi_list,"P":P_list,"yi":yi_list,"flagl":flagl_list,"flagv":flagv_list,"obj":obj_list}

def _phase_xiT_wrapper(args):

    T, xi, eos, opts = args
    logger.info("T (K), xi: {} {}, Let's Begin!".format(T, xi))

    try:
        if len(xi[xi!=0.])==1:
            P, _, _ = calc.calc_Psat(T, xi, eos, **opts)
            yi, flagv, flagl, obj = xi, 0, 1, 0.0
        else:
            if "pressure_options" in opts and "method" in opts["pressure_options"]:
                opts['method'] = opts["pressure_options"]["method"]
                del opts["pressure_options"]["method"]
            P, yi, flagv, flagl, obj = calc.calc_xT_phase(xi, T, eos, **opts)
    except:
        logger.warning("T (K), xi: {} {}, calculation did not produce a valid result.".format(T, xi))
        logger.debug("Calculation Failed:", exc_info=True)
        P, yi, flagl, flagv, obj = [np.nan, np.nan*np.ones(len(xi)), 3, 3, np.nan]

    logger.info("P (Pa), yi: {} {}".format(P, yi)) 

    return P, yi, flagv, flagl, obj


######################################################################
#                                                                    #
#                Phase Equilibria given yi and T                     #
#                                                                    #
######################################################################
def phase_yiT(eos, **sys_dict):

    r"""
    Calculate phase diagram given vapor mole fractions, yi, and temperature.

    Input and system information are assessed first. An output file is generated with T, yi, and corresponding P and xi.
    
    Parameters
    ----------
    eos : obj
        An instance of the defined EOS class to be used in thermodynamic computations.
    sys_dict: kwargs, Optional

        - Tlist: (list[float]) Optional - default 298.15 [K] Temperature of the system corresponding to composition in yilist. If one set is given, this pressure will be used for all compositions.
        - yilist: (list[list[float]]) - List of sets of component mole fraction, where sum(yi)=1.0 for each set. Each set of components corresponds to a temperature in Tlist, or if one set is given, this composition will be used for all temperatures.
        - Pguess: (list[float]) - [Pa] Optional, Guess the system pressure at the dew point. A value of None will force an estimation based on the saturation pressure of each component.
        - method: (str) Optional - Solving method for outer loop that converges pressure. If not given the :func:`~despasito.thermodynamics.calc_yT_phase` default will be used.
        - pressure_options: (dict) Optional - Keyword arguments used in the given method, "method" from :func:`~despasito.utils.general_toolbox.solve_root`, to solve the outer loop in the solving algorithm
        - mole_fraction_options: (dict) Optional - Keywords used to solve the mole fraction loop in :func:`~despasito.thermodynamics.calc.solve_xi_yiT`
        - density_dict: (dict) Optional - Other keyword options for density array :func:`~despasito.thermodynamics.calc.PvsRho` 

    Returns
    -------
    output_dict : dict
        Output of dictionary containing given and calculated values
    """

    ## Extract and check input data
    if 'Tlist' in sys_dict:
        T_list = np.array(sys_dict['Tlist'],float)
        del sys_dict['Tlist']
        logger.info("Using Tlist")
    else:
        T_list = np.array([constants.standard_temperature])
        logger.info("Assuming standard temperature")

    if 'yilist' in sys_dict:
        yi_list = np.array(sys_dict['yilist'],float)
        del sys_dict['yilist']
        logger.info("Using yilist")
    else:
        raise ValueError('Mole fractions, yilist, are not specified')

    if np.size(T_list) != np.size(yi_list, axis=0):
        if len(T_list) == 1:
            T_list = np.ones(len(yi_list))*T_list[0]
            logger.info("The same temperature, {}, was used for all mole fraction values".format(T_list[0]))
        elif len(yi_list) == 1:
            yi_list = np.array([yi_list[0] for i in range(len(T_list))])
            logger.info("The same composition, {}, was used for all temperature values".format(yi_list[0]))
        else:
            raise ValueError("The number of provided temperatures and mole fraction sets are different")

    if 'mpObj' in sys_dict:
        mpObj = sys_dict['mpObj']
        del sys_dict['mpObj']
        flag_use_mp_object = True
    else:
        flag_use_mp_object = False

    ## Optional values
    opts = {}

    # Process initial guess in pressure
    if 'Pguess' in sys_dict:
        Pguess = np.array(sys_dict['Pguess'],float)
        del sys_dict['Pguess']
        if not len(np.shape(Pguess)):
            Pguess = np.array([Pguess])
        if np.size(T_list) != np.size(Pguess):
            if len(Pguess) == 1:
                opts["Pguess"] = np.ones(len(T_list))*float(Pguess[0])
                logger.info("The same pressure, {}, was used for all mole fraction values".format(Pguess))
            else:
                raise ValueError("The number of provided pressure and mole fraction sets are different")
        else:
            opts["Pguess"] = Pguess
        logger.info("Using user defined initial guess has been provided")

    if 'Pmin' in sys_dict:
        Pmin = np.array(sys_dict['Pmin'],float)
        del sys_dict['Pmin']
        if not len(np.shape(Pmin)):
            Pmin = np.array([Pmin])
        if np.size(T_list) != np.size(Pmin):
            if len(Pmin) == 1:
                opts["Pmin"] = np.ones(len(T_list))*float(Pmin[0])
                logger.info("The same min pressure, {}, was used for all mole fraction values".format(Pmin))
            else:
                raise ValueError("The number of provided pressure and mole fraction sets are different")
        else:
            opts["Pmin"] = Pmin
        logger.info("Using user defined min pressure")

    if 'Pmax' in sys_dict:
        Pmax = np.array(sys_dict['Pmax'],float)
        del sys_dict['Pmax']
        if not len(np.shape(Pmax)):
            Pmax = np.array([Pmax])
        if np.size(T_list) != np.size(Pmax):
            if len(Pmax) == 1:
                opts["Pmax"] = np.ones(len(T_list))*float(Pmax[0])
                logger.info("The same max pressure, {}, was used for all mole fraction values".format(Pmax))
            else:
                raise ValueError("The number of provided pressure and mole fraction sets are different")
        else:
            opts["Pmax"] = Pmax
        logger.info("Using user defined max pressure")

    opts.update(sys_dict) # Add unprocessed options

    ## Calculate P and yi
    per_job_var = ["Pguess", "Pmin", "Pmax"]
    inputs = []
    for i in range(len(T_list)):
        opts_tmp = opts.copy()
        for key in per_job_var:
            if key in opts_tmp:
                opts_tmp[key] = opts_tmp[key][i]
        inputs.append((T_list[i], yi_list[i], eos, opts_tmp))

    ## Calculate P and xi
    T_list = np.array(T_list)
    inputs = [(T_list[i], yi_list[i], eos, opts) for i in range(len(T_list))]

    if flag_use_mp_object:
        P_list, xi_list, flagv_list, flagl_list, obj_list = mpObj.pool_job(_phase_yiT_wrapper, inputs)
    else:
        P_list, xi_list, flagv_list, flagl_list, obj_list = MultiprocessingJob.serial_job(_phase_yiT_wrapper, inputs)

    logger.info("--- Calculation phase_yiT Complete ---")

    return {"T":T_list,"xi":xi_list,"P":P_list,"yi":yi_list,"flagl":flagl_list,"flagv":flagv_list, "obj":obj_list}

def _phase_yiT_wrapper(args):

    T, yi, eos, opts = args
    logger.info("T (K), yi: {} {}, Let's Begin!".format(T, yi))

    try:
        if len(yi[yi!=0.])==1:
            P, _, _ = calc.calc_Psat(T, yi, eos, **opts)
            xi, flagv, flagl, obj = yi, 0, 1, 0.0
        else:
            if "pressure_options" in opts and "method" in opts["pressure_options"]:
                opts['method'] = opts["pressure_options"]["method"]
                del opts["pressure_options"]["method"]
            P, xi, flagl, flagv, obj = calc.calc_yT_phase(yi, T, eos, **opts)
    except:
        logger.warning("T (K), yi: {} {}, calculation did not produce a valid result.".format(T, yi))
        logger.debug("Calculation Failed:", exc_info=True)
        P, xi, flagl, flagv, obj = [np.nan, np.nan*np.ones(len(yi)), 3, 3, np.nan]

    logger.info("P (Pa), xi: {} {}".format(P, xi))

    return P, xi, flagv, flagl, obj

######################################################################
#                                                                    #
#                Phase Equilibria given yi and T                     #
#                                                                    #
######################################################################
def flash(eos, **sys_dict):

    r"""
    Flash calculation of vapor and liquid mole fractions. Only binary systems are currently supported

    Input and system information are assessed first. An output file is generated with T, yi, and corresponding P and xi.
    
    Parameters
    ----------
    eos : obj
        An instance of the defined EOS class to be used in thermodynamic computations.
    sys_dict: kwargs, Optional

        - Tlist: (list[float]) Optional - default 298.15 [K] Temperature of the system corresponding Plist. If one value is given, this temperature will be used for all temperatures.
        - Plist: (list[float]) - Pressure of the system corresponding to Tlist. If one value is given, this pressure will be used for all temperatures.
        - mole_fraction_options: (dict) Optional - Keywords used to solve the mole fraction loop in :func:`~despasito.thermodynamics.calc.calc_flash`
        - density_dict: (dict) Optional - Other keyword options for density array :func:`~despasito.thermodynamics.calc.PvsRho` 

    Returns
    -------
    output_dict : dict
        Output of dictionary containing given and calculated values
    """

    ## Extract and check input data
    if 'Tlist' in sys_dict:
        T_list = np.array(sys_dict['Tlist'],float)
        del sys_dict['Tlist']
        logger.info("Using Tlist")
    else:
        T_list = np.array([constants.standard_temperature])
        logger.info("Assuming standard temperature")

    if 'Plist' in sys_dict:
        P_list = np.array(sys_dict['Plist'],float)
        del sys_dict['Plist']
        logger.info("Using Plist")
    else:
        P_list = constants.standard_pressure * np.ones_like(T_list)
        logger.info("Assuming atmospheric pressure.")

    if np.size(T_list) != np.size(P_list, axis=0):
        if len(T_list) == 1:
            T_list = np.ones(len(P_list))*T_list[0]
            logger.info("The same temperature, {}, was used for all pressure values".format(T_list[0]))
        elif len(P_list) == 1:
            P_list = np.ones(len(T_list))*P_list[0]
            logger.info("The same pressure, {}, was used for all temperature values".format(P_list[0]))
        else:
            raise ValueError("The number of provided temperatures and pressure values are different")

    if 'mpObj' in sys_dict:
        mpObj = sys_dict['mpObj']
        del sys_dict['mpObj']
        flag_use_mp_object = True
    else:
        flag_use_mp_object = False

    opts = sys_dict.copy()

    # Initialize Variables
    if eos.number_of_components != 2:
        raise ValueError("Only binary systems are currently supported for flash calculations, {} were given.".format(eos.number_of_components))

    inputs = [(T_list[i], P_list[i], eos, opts) for i in range(len(T_list))]

    if flag_use_mp_object:
        xi_list, yi_list, flagv_list, flagl_list, obj_list = mpObj.pool_job(_flash_wrapper, inputs)
    else:
        xi_list, yi_list, flagv_list, flagl_list, obj_list = MultiprocessingJob.serial_job(_flash_wrapper, inputs)

    logger.info("--- Calculation flash Complete ---")

    return {"T":T_list,"xi":xi_list,"P":P_list,"yi":yi_list,"flagl":flagl_list,"flagv":flagv_list, "obj":obj_list}

def _flash_wrapper(args):

    T, P, eos, opts = args

    try:
        xi, flagl, yi, flagv, obj = calc.calc_flash(P, T, eos, **opts)
    except:
        logger.warning("T (K), P (Pa): {} {}, calculation did not produce a valid result.".format(T, P))
        logger.debug("Calculation Failed:", exc_info=True)
        xi, yi, flagl, flagv, obj = [np.nan*np.ones(eos.number_of_components), np.nan*np.ones(eos.number_of_components), 3, 3, np.nan]

    logger.info("xi: {}, yi: {}".format(xi, yi))

    return xi, yi, flagv, flagl, obj

######################################################################
#                                                                    #
#                Saturation calc for 1 Component                     #
#                                                                    #
######################################################################
def saturation_properties(eos, **sys_dict):

    r"""
    Computes the saturated pressure, liquid, and gas density a one component phase at a temperature.

    Input and system information are assessed first.  An output file is generated with T, :math:`P^{sat}`, :math:`\rho^{sat}_{l}, :math:`\rho^{sat}_{v}
    
    Parameters
    ----------
    eos : obj
        An instance of the defined EOS class to be used in thermodynamic computations.
    sys_dict: kwargs, Optional

        - Tlist: (list[float]) Optional - default: 298.15 [K] Temperature of the system corresponding Plist. If one value is given, this temperature will be used for all temperatures.
        - density_dict: (dict) Optional - Other keyword options for density array :func:`~despasito.thermodynamics.calc.PvsRho` 

    Returns
    -------
    output_dict : dict
        Output of dictionary containing given and calculated values
    """

    ## Extract and check input data
    if 'Tlist' in sys_dict:
        T_list = np.array(sys_dict['Tlist'],float)
        del sys_dict['Tlist']
        logger.info("Using Tlist")
    else:
        T_list = np.array([constants.standard_temperature])
        logger.info("Using standard temperature")

    if 'xilist' in sys_dict:
        xi_list = np.array(sys_dict['xilist'],float)
        del sys_dict['xilist']
    else:
        xi_list = np.array([[1.0] for x in range(len(T_list))])

    if 'mpObj' in sys_dict:
        mpObj = sys_dict['mpObj']
        del sys_dict['mpObj']
        flag_use_mp_object = True
    else:
        flag_use_mp_object = False

    opts = sys_dict.copy()

    inputs = [(T_list[i], xi_list[i], eos, opts) for i in range(len(T_list))]
    if flag_use_mp_object:
        Psat, rholsat, rhovsat = mpObj.pool_job(_saturation_properties_wrapper, inputs)
    else:
        Psat, rholsat, rhovsat = MultiprocessingJob.serial_job(_saturation_properties_wrapper, inputs)

    logger.info("--- Calculation saturation_properties Complete ---")

    return {"T":T_list,"Psat":Psat,"rhol":rholsat,"rhov":rhovsat}

def _saturation_properties_wrapper(args):

    T, xi, eos, opts = args

    logger.info("T (K), xi: {} {}, Let's Begin!".format(T, xi))

    try:
        Psat, rholsat, rhovsat = calc.calc_Psat(T, xi, eos, **opts)
        if np.isnan(Psat):
            logger.warning("T (K), xi: {} {}, calculation did not produce a valid result.".format(T, xi))
            logger.debug("Calculation Failed:", exc_info=True)
            Psat, rholsat, rhovsat = [np.nan, np.nan, np.nan]
        else:
            logger.info("Psat {} Pa, rhol {}, rhov {}".format(Psat,rholsat,rhovsat))
    except:
        logger.warning("T (K), xi: {} {}, calculation did not produce a valid result.".format(T, xi))
        logger.debug("Calculation Failed:", exc_info=True)
        Psat, rholsat, rhovsat = [np.nan, np.nan, np.nan]

    return Psat, rholsat, rhovsat

######################################################################
#                                                                    #
#                Liquid density given xi, T, and P                   #
#                                                                    #
######################################################################
def liquid_properties(eos, **sys_dict):

    r"""
    Computes the liquid density and chemical potential given a temperature, pressure, and liquid mole fractions.

    Input and system information are assessed first. An output file is generated with P, T, xi, :math:`\rho_{l}, and :math:`\phi_{l}.
    
    Parameters
    ----------
    eos : obj
        An instance of the defined EOS class to be used in thermodynamic computations.
    sys_dict: kwargs, Optional

        - xilist: (list[list[float]]) - List of sets of component mole fraction, where sum(xi)=1.0 for each set. Each set of components corresponds to a temperature in Tlist, or if one set is given, this composition will be used for all temperatures.
        - Tlist: (list[float]) Optional - default: 298.15 [K] Temperature of the system corresponding Plist. If one value is given, this temperature will be used for all temperatures.
        - Plist: (list[float]) Optional - default: 101325.0 Pa. Pressure of the system corresponding to Tlist. If one value is given, this pressure will be used for all temperatures.
        - density_dict: (dict) Optional - Other keyword options for density array :func:`~despasito.thermodynamics.calc.PvsRho` 

    Returns
    -------
    output_dict : dict
        Output of dictionary containing given and calculated values
    """

    ## Extract and check input data
    if 'Tlist' in sys_dict:
        T_list = np.array(sys_dict['Tlist'],float)
        del sys_dict['Tlist']
        logger.info("Using Tlist")
    else:
        T_list = np.array([constants.standard_temperature])
        logger.info("Assuming standard temperature")

    if 'xilist' in sys_dict:
        xi_list = np.array(sys_dict['xilist'],float)
        del sys_dict['xilist']
        logger.info("Using xilist")
    else:
        if eos.number_of_components == 1:
            logger.info("Array xilist wasn't specified, assume one component system")
            xi_list = [[1.0] for i in T_list]
        else:
            raise ValueError("With more than one component, xilist must be provided.")

    if np.size(T_list) != np.size(xi_list, axis=0):
        if len(T_list) == 1:
            T_list = np.ones(len(xi_list))*T_list[0]
            logger.info("The same temperature, {}, was used for all mole fraction values".format(T_list[0]))
        elif len(xi_list) == 1:
            xi_list = [xi_list[0] for i in T_list]
            logger.info("The same mole fraction set, {}, was used for all temperature values".format(xi_list[0]))
        else:
            raise ValueError("The number of provided temperatures and mole fraction sets are different")

    if "Plist" in sys_dict:
        P_list = np.array(sys_dict['Plist'])
        del sys_dict['Plist']
        if np.size(T_list) != np.size(P_list, axis=0):
            if len(P_list)==1:
                P_list = P_list[0] * np.ones_like(T_list)
            elif len(T_list)==1:
                T_list = T_list[0] * np.ones_like(P_list)
                xi_list = np.array([xi_list[0] for i in T_list])
            else:
                raise ValueError("The number of provided temperatures and pressure sets are different")
        logger.info("Using Plist")
    else:
        P_list = constants.standard_pressure * np.ones_like(T_list)
        logger.info("Assuming atmospheric pressure.")

    if 'mpObj' in sys_dict:
        mpObj = sys_dict['mpObj']
        del sys_dict['mpObj']
        flag_use_mp_object = True
    else:
        flag_use_mp_object = False

    opts = sys_dict.copy()

    inputs = [(P_list[i], T_list[i], xi_list[i], eos, opts) for i in range(len(T_list))]
    if flag_use_mp_object:
        rhol, phil, flagl = mpObj.pool_job(_liquid_properties_wrapper, inputs)
    else:
        rhol, phil, flagl = MultiprocessingJob.serial_job(_liquid_properties_wrapper, inputs)

    logger.info("--- Calculation liquid_properties Complete ---")

    return {"P":P_list,"T":T_list,"xi":xi_list,"rhol":rhol,"phil":phil,"flagl":flagl}

def _liquid_properties_wrapper(args):

    P, T, xi, eos, opts = args

    logger.info("T (K), P (Pa), xi: {} {} {}, Let's Begin!".format(T, P, xi))

    try:
        phil, rhol, flagl = calc.calc_phil(P, T, xi, eos, **opts)
        logger.info("P {} Pa, T {} K, xi {}, rhol {}, phil {}, flagl {}".format(P, T, xi, rhol, phil, flagl))
    except:
        logger.warning('Failed to calculate rhol at {} K and {} Pa'.format(T,P))
        rhol, flagl = np.nan, 3
        phil = np.nan*np.ones(eos.number_of_components)

    return rhol, phil, flagl

######################################################################
#                                                                    #
#                Vapor density given yi, T, and P                    #
#                                                                    #
######################################################################
def vapor_properties(eos, **sys_dict):

    r"""
    Computes the vapor density and chemical potential given a temperature, pressure, and vapor mole fractions.

    Input and system information are assessed first. An output file is generated with P, T, yi, :math:`\rho_{v}, and :math:`\phi_{v}.
    
    Parameters
    ----------
    eos : obj
        An instance of the defined EOS class to be used in thermodynamic computations.
    sys_dict: kwargs, Optional

        - yilist: (list[list[float]]) - List of sets of component mole fraction, where sum(yi)=1.0 for each set. Each set of components corresponds to a temperature in Tlist, or if one set is given, this composition will be used for all temperatures.
        - Tlist: (list[float]) Optional - default: 298.15 [K] Temperature of the system corresponding Plist. If one value is given, this temperature will be used for all temperatures.
        - Plist: (list[float]) Optional - default: 101325.0 Pa. Pressure of the system corresponding to Tlist. If one value is given, this pressure will be used for all temperatures.
        - density_dict: (dict) Optional - Other keyword options for density array :func:`~despasito.thermodynamics.calc.PvsRho` 

    Returns
    -------
    output_dict : dict
        Output of dictionary containing given and calculated values
    """

    ## Extract and check input data
    if 'Tlist' in sys_dict:
        T_list = np.array(sys_dict['Tlist'],float)
        del sys_dict['Tlist']
        logger.info("Using Tlist")
    else:
        logger.info("Assuming standard temperature")
        T_list = np.array([constants.standard_temperature])

    if 'yilist' in sys_dict:
        yi_list = np.array(sys_dict['yilist'],float)
        del sys_dict['yilist']
        logger.info("Using yilist")
    else:
        if eos.number_of_components == 1:
            logger.info("Array yilist wasn't specified, assume one component system")
            yi_list = [[1.0] for i in T_list]
        else:
            raise ValueError("With more than one component, yilist must be provided.")

    if np.size(T_list) != np.size(yi_list, axis=0):
        if len(T_list) == 1:
            T_list = np.ones(len(yi_list))*T_list[0]
            logger.info("The same temperature, {}, was used for all mole fraction values".format(T_list[0]))
        elif len(yi_list) == 1:
            yi_list = [yi_list[0] for i in T_list]
            logger.info("The same mole fraction set, {}, was used for all temperature values".format(yi_list[0]))
        else:
            raise ValueError("The number of provided temperatures and mole fraction sets are different")

    if "Plist" in sys_dict:
        P_list = np.array(sys_dict['Plist'])
        del sys_dict['Plist']
        if np.size(T_list) != np.size(P_list, axis=0):
            if len(P_list)==1:
                P_list = P_list[0] * np.ones_like(T_list)
            elif len(T_list)==1:
                T_list = T_list[0] * np.ones_like(P_list)
                yi_list = np.array([yi_list[0] for i in T_list])
            else:
                raise ValueError("The number of provided temperatures and pressure sets are different")
        logger.info("Using Plist")
    else:
        P_list = constants.standard_pressure * np.ones_like(T_list)
        logger.info("Assuming atmospheric pressure.")

    if 'mpObj' in sys_dict:
        mpObj = sys_dict['mpObj']
        del sys_dict['mpObj']
        flag_use_mp_object = True
    else:
        flag_use_mp_object = False

    opts = sys_dict.copy()

    inputs = [(P_list[i], T_list[i], yi_list[i], eos, opts) for i in range(len(T_list))]
    if flag_use_mp_object:
        rhov, phiv, flagv = mpObj.pool_job(_vapor_properties_wrapper, inputs)
    else:
        rhov, phiv, flagv = MultiprocessingJob.serial_job(_vapor_properties_wrapper, inputs)

    logger.info("--- Calculation vapor_properties Complete ---")

    return {"P":P_list,"T":T_list,"yi":yi_list,"rhov":rhov,"phiv":phiv,"flagv":flagv}

def _vapor_properties_wrapper(args):

    P, T, yi, eos, opts = args

    logger.info("T (K), P (Pa), yi: {} {} {}, Let's Begin!".format(T, P, yi))

    try:
        phiv, rhov, flagv = calc.calc_phiv(P, T, yi, eos, **opts)
        logger.info("P {} Pa, T {} K, yi {}, rhov {}, phiv {}, flagv {}".format(P, T, yi, rhov, phiv, flagv))
    except:
        logger.warning('Failed to calculate rhov at {} K and {} Pa'.format(T,P))
        rhov, flagv = np.nan, 3
        phiv = np.nan*np.ones(eos.number_of_components)

    return rhov, phiv, flagv

######################################################################
#                                                                    #
#               Solubility Parameter given xi and T                  #
#                                                                    #
######################################################################

def solubility_parameter(eos, **sys_dict):

    r"""
    Calculate the Hildebrand solubility parameter based on temperature and composition. This function is based on the method used in Zeng, Z., Y. Xi, and Y. Li "Calculation of Solubility Parameter Using Perturbed-Chain SAFT and Cubic-Plus-Association Equations of State" Ind. Eng. Chem. Res. 2008, 47, 9663–9669.

    Input and system information are assessed first. An output file is generated with T, xi, :math:`\rho_{l}, and :math:`\detla.
    
    Parameters
    ----------
    eos : obj
        An instance of the defined EOS class to be used in thermodynamic computations.
    sys_dict: kwargs, Optional

        - Tlist: (list[float]) Optional - default: 298.15 [K] Temperature of the system corresponding Plist. If one value is given, this temperature will be used for all temperatures.
        - xilist: (list[list[float]]) Optional - default: [1.0] assuming all of one component. List of sets of component mole fraction, where sum(xi)=1.0 for each set. Each set of components corresponds to a temperature in Tlist, or if one set is given, this composition will be used for all temperatures.
        - Plist: (list[float]) Optional - default: 101325.0 Pa. Pressure of the system corresponding to Tlist. If one value is given, this pressure will be used for all temperatures.
        - dT: (float) Optional - Change in temperature used in calculating the derivative with central difference method. See func:`~despasito.thermodynamics.calc.hildebrand_solubility` for default.
        - tol: (float) Optional - This cutoff value evaluates the extent to which the integrand of the calculation has decayed. If the last value if the array is greater than tol, then the remaining area is estimated as a triangle, where the intercept is estimated from an interpolation of the previous four points. See func:`~despasito.thermodynamics.calc.hildebrand_solubility` for default.
        - density_dict: (dict) Optional - Other keyword options for density array :func:`~despasito.thermodynamics.calc.PvsRho` 

    Returns
    -------
    output_dict : dict
        Output of dictionary containing given and calculated values
    """

    ## Extract and check input data
    if 'Tlist' in sys_dict:
        T_list = np.array(sys_dict['Tlist'],float)
        logger.info("Using Tlist")
        del sys_dict['Tlist']
    else:
        logger.info("Assuming standard temperature")
        T_list = np.array([constants.standard_temperature])

    if "Plist" in sys_dict:
        P_list = np.array(sys_dict['Plist'])
        logger.info("Using Plist")
        del sys_dict['Plist']
    else:
        P_list = constants.standard_pressure * np.ones_like(T_list)
        logger.info("Assuming atmospheric pressure.")

    if "xilist" in sys_dict:
        xi_list = np.array(sys_dict['xilist'])
        logger.info("Using xilist")
        del sys_dict['xilist']
    else:
        if eos.number_of_components == 1:
            xi_list = np.array([[1.0] for x in range(len(T_list))])
            logger.info("Single mole fraction of one.")
        else:
            raise ValueError("Mole fractions, xilist, must be specified")

    if np.size(T_list) != np.size(xi_list, axis=0):
        if len(T_list) == 1:
            T_list = np.ones(len(xi_list))*T_list[0]
            logger.info("The same temperature, {}, was used for all mole fraction values".format(T_list[0]))
        elif len(xi_list) == 1:
            xi_list = np.array([xi_list[0] for x in range(len(T_list))])
            logger.info("The same mole fraction values, {}, were used for all temperature values".format(xi_list[0]))
        else:
            raise ValueError("The number of provided temperatures and mole fraction sets are different")

    if np.size(T_list) != np.size(P_list, axis=0):
        if len(P_list) == 1:
            P_list = np.ones(len(T_list))*P_list[0]
            logger.info("The same pressure, {}, was used for all temperature values".format(P_list[0]))
        elif len(T_list)==1:
            T_list = T_list[0] * np.ones_like(P_list)
            xi_list = np.array([xi_list[0] for i in T_list])
        else:
            raise ValueError("The number of provided temperatures and pressure sets are different")

    if 'mpObj' in sys_dict:
        mpObj = sys_dict['mpObj']
        del sys_dict['mpObj']
        flag_use_mp_object = True
    else:
        flag_use_mp_object = False

    opts = sys_dict.copy()

    ## Calculate solubility parameter
    inputs = [(P_list[i], T_list[i], xi_list[i], eos, opts) for i in range(len(T_list))]
    if flag_use_mp_object:
        rhol, flagl, delta = mpObj.pool_job(_solubility_parameter_wrapper, inputs)
    else:
        rhol, flagl, delta = MultiprocessingJob.serial_job(_solubility_parameter_wrapper, inputs)

    logger.info("--- Calculation solubility_parameter Complete ---")

    return {"P":P_list,"T":T_list,"xi":xi_list,"rhol":rhol,"delta":delta}

def _solubility_parameter_wrapper(args):

    P, T, xi, eos, opts = args

    logger.info("T (K), P (Pa), xi: {} {} {}, Let's Begin!".format(T, P, xi))

    try:
        rhol, flagl = calc.calc_rhol(P, T, xi, eos, **opts)
        delta = calc.hildebrand_solubility(rhol, xi, T, eos, **opts)
        logger.info("P {} Pa, T {} K, xi {}, rhol {}, flagl {}, delta {}".format(P, T, xi, rhol, flagl, delta))
    except:
        logger.warning('Failed to calculate rhov at {} K and {} Pa'.format(T,P))
        rhol, flagl, delta = np.nan, 3, np.nan

    return rhol, flagl, delta

######################################################################
#                                                                    #
#               Solubility Parameter given xi and T                  #
#                                                                    #
######################################################################

def verify_eos(eos, **sys_dict):

    r"""
    The following consistency checks are performed to ensure the calculated fugacity coefficients are thermodynamically consistent.

    - 1. d(log phi) / dP = (Z - 1)/P
    - 

    TODO: Finish documentation
    
    Parameters
    ----------
    eos : obj
        An instance of the defined EOS class to be used in thermodynamic computations.
    sys_dict: kwargs, Optional

        - Tlist: (list[float]) Optional - default: 298.15 [K] Temperature of the system corresponding Plist. If one value is given, this temperature will be used for all temperatures.
        - xilist: (list[list[float]]) Optional - default: Array of 11 values from x1=0 to x1=1 for binary array. List of sets of component mole fraction, where sum(xi)=1.0 for each set. Each set of components corresponds to a temperature in Tlist, or if one set is given, this composition will be used for all temperatures.
        - Plist: (list[float]) Optional - default: 101325.0 Pa. Pressure of the system corresponding to Tlist. If one value is given, this pressure will be used for all temperatures.
        - density_dict: (dict) Optional - Other keyword options for density array :func:`~despasito.thermodynamics.calc.PvsRho` 

    Returns
    -------
    output_dict : dict
        Output of dictionary containing given and calculated values
    """

    ## Extract and check input data

    if "xilist" in sys_dict:
        xi_list = np.array(sys_dict['xilist'])
        logger.info("Using xilist")
        del sys_dict['xilist']
    elif eos.number_of_components == 2:
        tmp = np.linspace(0,1,11)
        xi_list = np.array([[x, 1.0-x] for x in tmp])
        logger.info("Use array of mole fractions")
    else:
        raise ValueError("Must have at least 2 components. With more that 2 components, the mole fractions need to be specified")

    if 'Tlist' in sys_dict:
        T_list = np.array(sys_dict['Tlist'],float)
        logger.info("Using Tlist")
        del sys_dict['Tlist']
    else:
        T_list = constants.standard_temperature*np.ones(len(xi_list))
        logger.info("Assume 298.15 K")

    if "Plist" in sys_dict:
        P_list = np.array(sys_dict['Plist'])
        logger.info("Using Plist")
        del sys_dict['Plist']
    else:
        P_list = constants.standard_pressure * np.ones_like(T_list)
        logger.info("Assuming atmospheric pressure.")

    if np.size(T_list) != np.size(xi_list, axis=0):
        if len(T_list) == 1:
            T_list = np.ones(len(xi_list))*T_list[0]
            logger.info("The same temperature, {}, was used for all mole fraction values".format(T_list[0]))
        elif len(xi_list) == 1:
            xi_list = np.array([xi_list[0] for x in range(len(T_list))])
            logger.info("The same mole fraction values, {}, were used for all temperature values".format(xi_list[0]))
        else:
            raise ValueError("The number of provided temperatures and mole fraction sets are different")

    if np.size(T_list) != np.size(P_list, axis=0):
        if len(P_list) == 1:
            P_list = np.ones(len(T_list))*P_list[0]
            logger.info("The same pressure, {}, was used for all temperature values".format(P_list[0]))
        else:
            raise ValueError("The number of provided temperatures and pressure sets are different")

    if 'mpObj' in sys_dict:
        mpObj = sys_dict['mpObj']
        del sys_dict['mpObj']
        flag_use_mp_object = True
    else:
        flag_use_mp_object = False

    opts = sys_dict.copy()

    ## Calculate solubility parameter
    inputs = [(P_list[i], T_list[i], xi_list[i], eos, opts) for i in range(len(T_list))]
    if flag_use_mp_object:
        residual_v1, residual_v2, flagv, log_phiv, residual_l1, residual_l2, flagl, log_phil = mpObj.pool_job(_verify_eos_wrapper, inputs)
    else:
        residual_v1, residual_v2, flagv, log_phiv, residual_l1, residual_l2, flagl, log_phil = MultiprocessingJob.serial_job(_verify_eos_wrapper, inputs)

    logger.info("--- Calculation verify_eos Complete ---")

    return {"P":P_list, "T":T_list, "xi":xi_list, "residual_v1":residual_v1, "residual_v2":residual_v2, "flagv": flagv, "log_phivi":log_phiv, "residual_l1":residual_l1, "residual_l2":residual_l2, "flagl": flagl, "log_phili":log_phil}

def _verify_eos_wrapper(args):

    P, T, xi, eos, opts = args

    logger.info("T (K), P (Pa), xi: {} {} {}, Let's Begin!".format(T, P, xi))

    rhov, flagv = calc.calc_rhov(P, T, xi, eos, **opts)
    if np.isnan(rhov):
        logger.warning('Failed to calculate rhov at {} K and {} Pa'.format(T,P))
        log_phiv, residual_v1, residual_v2 = np.nan, np.nan, np.nan
    else:
        phiv = eos.fugacity_coefficient(P, np.array([rhov]), xi, T)
        log_phiv = np.log(phiv)
        residual_v1 = calc.fugacity_test_1(P, T, xi, rhov, eos, **opts)
        residual_v2 = calc.fugacity_test_2(P, T, xi, rhov, eos, **opts)
        logger.info("rhov {}, flagv {}, log_phiv {}, log_phiv {}, residual1 {}, residual2 {}".format(rhov, flagv, np.sum(xi*log_phiv), log_phiv, residual_v1, residual_v2))

    rhol, flagl = calc.calc_rhol(P, T, xi, eos, **opts)
    if np.isnan(rhol):
        logger.warning('Failed to calculate rhol at {} K and {} Pa'.format(T,P))
        log_phil, residual_l1, residual_l2 = np.nan, np.nan, np.nan
    else:
        phil = eos.fugacity_coefficient(P, np.array([rhol]), xi, T)
        log_phil = np.log(phil)
        residual_l1 = calc.fugacity_test_1(P, T, xi, rhol, eos, **opts)
        residual_l2 = calc.fugacity_test_2(P, T, xi, rhol, eos, **opts)
        logger.info("rhol {}, flagl {}, log_phil {}, log_phil {}, residual1 {}, residual2 {}".format(rhol, flagl, np.sum(xi*log_phil), log_phil, residual_l1, residual_l2))

    return residual_v1, residual_v2, flagv, log_phiv, residual_l1, residual_l2, flagl, log_phil

