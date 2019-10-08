"""
This module contains our thermodynamic calculations. Calculation of pressure, chemical potential, and max density are handled by an eos object so that these functions can be used with any EOS. The thermo module contains a series of wrapper to handle the inputs and outputs of these functions.

.. todo:: 
    Add types of scipy solving methods and the types available
    
    Update if statement to generalize as a factory
    
"""

import numpy as np
import sys
from scipy import interpolate
from scipy.optimize import minimize
from scipy.optimize import minimize_scalar
from scipy.optimize import fmin
from scipy.optimize import newton
from scipy.optimize import root
from scipy.optimize import brentq
from scipy.optimize import bisect
from scipy.optimize import fsolve
from scipy.misc import derivative
from scipy.ndimage.filters import gaussian_filter1d
import random
#import deap
import copy
import time
import matplotlib.pyplot as plt
import logging

from . import fund_constants as const

######################################################################
#                                                                    #
#                              Calc CC Params                        #
#                                                                    #
######################################################################
def calc_CC_Pguess(xilist, Tlist, CriticalProp):
    r"""
    Computes the Mie parameters of a mixture from the mixed critical properties of the pure components. 
    From: Mejia, A., C. Herdes, E. Muller. Ind. Eng. Chem. Res. 2014, 53, 4131-4141
    
    Parameters
    ----------
    xilist : list[list[xi]]
        List of different Mole fractions of each component, sum(xi) should equal 1.0 for each set. Each set of components corresponds to a temperature in Tlist.
    Tlist : list[float]
        Temperature of the system corresponding to composition in xilist [K]
    CriticalProp : list[list]
        List of critical properties :math:`T_C`, :math:`P_C`, :math:`\omega`, :math:`\rho_{0.7}`, :math:`Z_C`, :math:`V_C`, and molecular weight, where each of these properties is a list of values for each bead.
    
    Returns
    -------
    Psatm : list[float]
        A list of guesses in pressure based on critical properties, of the same length as xilist and Tlist [Pa]
    """

    logger = logging.getLogger(__name__)

    Tc, Pc, omega, rho_7, Zc, Vc, M = CriticalProp

    ############## Calculate Mixed System Mie Parameters
    flag = 0
    if all(-0.847 > x > 0.2387 for x in omega):
        flag = 1
        logger.warning("Omega is outside of the range that these correlations are valid")

    a = [14.8359, 22.2019, 7220.9599, 23193.4750, -6207.4663, 1732.9600]
    b = [0.0, -6.9630, 468.7358, -983.6038, 914.3608, -1383.4441]
    c = [0.1284, 1.6772, 0.0, 0.0, 0.0, 0.0]
    d = [0.0, 0.4049, -0.1592, 0.0, 0.0, 0.0]
    j = [1.8966, -6.9808, 10.6330, -9.2041, 4.2503, 0.0]
    k = [0.0, -1.6205, -0.8019, 1.7086, -0.5333, 1.0536]

    Tcm, Pcm, sigma, epsilon, Psatm = [[] for x in range(5)]

    i = 0
    jj = 1

    if flag == 1:
        Psatm = np.nan
    elif flag == 0: 
        for kk, xi in enumerate(xilist):
            # Mixture alpha
            omegaij = xi[i] * omega[i] + xi[jj] * omega[jj]
            tmp1 = np.sum([a[ii] * omegaij**ii for ii in range(6)])
            tmp2 = np.sum([b[ii] * omegaij**ii for ii in range(6)])
            l_r = tmp1 / (1. + tmp2)
            C = (l_r / (l_r - 6.)) * (l_r / 6.)**(6. / (l_r - 6.))
            al_tmp = C * (1. / 3. - 1. / (l_r - 3.))
            # Mixture Critical Properties Stewart-Burkhardt-Voo
            K = xi[i] * Tc[i] / Pc[i]**.5 + xi[jj] * Tc[jj] / Pc[jj]**.5
            tmp1 = xi[i] * Tc[i] / Pc[i] + xi[jj] * Tc[jj] / Pc[jj]
            tmp2 = xi[i] * (Tc[i] / Pc[i])**.5 + xi[jj] * (Tc[jj] / Pc[jj])**.5
            J = tmp1 / 3. + 2. / 3. * tmp2**2.
            Tc_tmp = K**2. / J
            Pc_tmp = (K / J)**2.
            # Mixture Pressure Prausnitz-Gunn
            if (Tlist[kk] / Tc[i] > 1. or Tlist[kk] / Tc[jj] > 1.):
                R = 8.3144598  # [kg*m^2/(s^2*mol*K)] Gas constant
                tmp1 = Zc[i] + Zc[jj]
                tmp2 = xi[i] * M[i] * Vc[i] + xi[jj] * M[jj] * Vc[jj]
                Pc_tmp = R * Tc_tmp * tmp1 / tmp2
            # Mixture Molar Density, Plocker Knapp
            Mij = M[i] * xi[i] + M[jj] * xi[jj]
            rho_tmp = 8. / Mij / ((rho_7[i] * M[i])**(-1. / 3.) + (rho_7[jj] * M[jj])**(-1. / 3.))**3.
            Nav = 6.0221415e+23  # avogadros number
    
            tmp1 = np.sum([c[ii] * al_tmp**ii for ii in range(6)])
            tmp2 = np.sum([d[ii] * al_tmp**ii for ii in range(6)])
            Tc_star = tmp1 / (1. + tmp2)
            eps_tmp = Tc_tmp / Tc_star  # [K], multiply by kB to change to energy units
    
            tmp3 = np.sum([j[ii] * al_tmp**ii for ii in range(6)])
            tmp4 = np.sum([k[ii] * al_tmp**ii for ii in range(6)])
            rho_star = tmp3 / (1. + tmp4)
            sig_tmp = (rho_star / rho_tmp / Nav)**(1. / 3.)
    
            # Calculate Psat
            eos_dict['massi'] = np.array([Mij])
            eos_dict['nui'] = np.array([[1]])
            eos_dict['beads'] = ['bead']
            eos_dict['beadlibrary'] = {
                'bead': {
                    'l_r': l_r,
                    'epsilon': eps_tmp,
                    'Vks': 1.0,
                    'Sk': 1.0,
                    'l_a': 6,
                    'mass': Mij,
                    'sigma': sig_tmp
                }
            }
            eos = eos("saft.gamma_mie",**eos_dict)
    
            if (Tlist[kk] < Tc_tmp):
                Psat_tmp, rholsat_tmp, rhogsat_tmp = calc_Psat(Tlist[kk], np.array([1.0]), eos)
            else:
                Psat_tmp = np.nan
    
            if np.isnan(Psat_tmp):
                Psatm = np.nan
                break
    
            # Save values
            # Nothing is done with rholsat_tmp and rhogsat_tmp
            Tcm.append(Tc_tmp)
            Pcm.append(Pc_tmp)
            sigma.append(sig_tmp)
            epsilon.append(eps_tmp)
            Psatm.append(Psat_tmp)

    return Psatm

######################################################################
#                                                                    #
#                      Pressure-Density Curve                        #
#                                                                    #
######################################################################
def PvsRho(T, xi, eos, minrhofrac=(1.0 / 200000.0), rhoinc=5.0, vspacemax=1.0E-4, maxpack=0.65):

    r"""
    Computes the Mie parameters of a mixture from the mixed critical properties of the pure components. 
    From: Mejia, A., C. Herdes, E. Muller. Ind. Eng. Chem. Res. 2014, 53, 4131-4141
    
    Parameters
    ----------
    T : float
        Temperature of the system [K]
    xi : numpy.ndarray
        Mole fraction of each component, sum(xi) should equal 1.0
    eos : obj
        An instance of the defined EOS class to be used in thermodynamic computations.
    minrhofrac : float, Optional, default: (1.0/200000.0)
        Fraction of the maximum density used to calculate, and is equal to, the minimum density of the density array. The minimum density is the reciprocal of the maximum specific volume used to calculate the roots. Passed from inputs to through the dictionary rhodict.
    rhoinc : float, Optional, default: 5.0
        The increment between density values in the density array. Passed from inputs to through the dictionary rhodict.
    vspacemax : float, Optional, default: 1.0E-4
        Maximum increment between specific volume array values. After conversion from density to specific volume, the increment values are compared to this value. Passed from inputs to through the dictionary rhodict.
    maxpack : float, Optional, default: 0.65
        Maximum packing fraction. Passed from inputs to through the dictionary rhodict.

    Returns
    -------
    vlist : numpy.ndarray
        Specific volume array. Length depends on values in rhodict [:math:`m^3`/mol]
    Plist : numpy.ndarray
        Pressure associated with specific volume of system with given temperature and composition [Pa]
    """

    logger = logging.getLogger(__name__)

    #estimate the maximum density based on the hard sphere packing fraction, part of EOS
    maxrho = eos.density_max(xi, T, maxpack=maxpack)
    #min rho is a fraction of max rho, such that minrho << rhogassat
    minrho = maxrho * minrhofrac
    #list of densities for P,rho and P,v
    rholist = np.arange(minrho, maxrho, rhoinc)
    #check rholist to see when the spacing
    vspace = (1.0 / rholist[:-1]) - (1.0 / rholist[1:])
    if np.amax(vspace) > vspacemax:
        vspaceswitch = np.where(vspace > vspacemax)[0][-1]
        rholist_2 = 1.0 / np.arange(1.0 / rholist[vspaceswitch + 1], 1.0 / minrho, vspacemax)[::-1]
        rholist = np.append(rholist_2, rholist[vspaceswitch + 2:])

    #compute Pressures (Plist) for rholsit
    Plist = eos.P(rholist * const.Nav, T, xi)

    #Flip Plist and rholist arrays
    Plist = Plist[:][::-1]
    rholist = rholist[:][::-1]
    vlist = 1.0 / rholist

    return vlist, Plist


######################################################################
#                                                                    #
#                      Pressure-Volume Spline                        #
#                                                                    #
######################################################################
def PvsV_spline(vlist, Plist):
    r"""
    Fit arrays of specific volume and pressure values to a cubic Univariate Spline.
    
    Parameters
    ----------
    vlist : numpy.ndarray
        Specific volume array. Length depends on values in rhodict [:math:`m^3`/mol]
    Plist : numpy.ndarray
        Pressure associated with specific volume of system with given temperature and composition [Pa]
    
    Returns
    -------
    Pvspline : obj
        Function object of pressure vs. specific volume
    roots : list
        List of specific volume roots. Subtract a system pressure from the output of Pvsrho to find density of vapor and/or liquid densities.
    extrema : list
        List of specific volume values corresponding to local minima and maxima.
    """

    logger = logging.getLogger(__name__)

    Psmoothed = gaussian_filter1d(Plist, sigma=.5)

    Pvspline = interpolate.InterpolatedUnivariateSpline(vlist, Psmoothed)
    roots = Pvspline.roots().tolist()
    Pvspline = interpolate.InterpolatedUnivariateSpline(vlist, Psmoothed, k=4)
    extrema = Pvspline.derivative().roots().tolist()
    if extrema: 
        if len(extrema) > 2: extrema = extrema[0:2]

    #PvsV_plot(vlist, Plist, Pvspline, markers=extrema)

    return Pvspline, roots, extrema

######################################################################
#                                                                    #
#                      Pressure-Volume Spline                        #
#                                                                    #
######################################################################
def PvsV_plot(vlist, Plist, Pvspline, markers=[]):
    r"""
    Plot pressure vs. specific volume.
    
    Parameters
    ----------
    vlist : numpy.ndarray
        Specific volume array. Length depends on values in rhodict [:math:`m^3`/mol]
    Plist : numpy.ndarray
        Pressure associated with specific volume of system with given temperature and composition [Pa]
    Pvspline : obj
        Function object of pressure vs. specific volume
    markers : list, Optional, default: []
        List of plot markers used in plot
    """

    logger = logging.getLogger(__name__)

    plt.plot(vlist,Plist,label="Orig.")
    plt.plot(vlist,Pvspline(vlist),label="Smoothed")
    plt.plot([vlist[0], vlist[-1]],[0,0],"k")
    for k in range(len(markers)):
        plt.plot([markers[k], markers[k]],[min(Plist),max(Plist)],"k")
    plt.xlabel("Specific Volume [$m^3$/mol]"), plt.ylabel("Pressure [Pa]")
    plt.legend(loc="best")
    plt.tight_layout()
    plt.show()

######################################################################
#                                                                    #
#                              Calc Psat                             #
#                                                                    #
######################################################################
def calc_Psat(T, xi, eos, rhodict={}):
    r"""
    Computes the saturated pressure, gas and liquid densities for a single component system given Temperature and Mie parameters
    T: Saturated Temperature in Kelvin
    minrhofrac: Fraction of maximum hard sphere packing fraction for gas density
    rhoinc: spacing densities for rholist in mol/m^3. Smaller values will generate a more accurate curve at increasing computational cost
    Returns Saturated Pressure in Pa, liquid denisty, and gas density in mol/m^3
    
    Parameters
    ----------
    T : float
        Temperature of the system [K]
    xi : numpy.ndarray
        Mole fraction of each component, sum(xi) should equal 1.0
    eos : obj
        An instance of the defined EOS class to be used in thermodynamic computations.
    rhodict : dict, Optional, default: {}
        Dictionary of options used in calculating pressure vs. mole 

    Returns
    -------
    Psat : float
        Saturation pressure given system information [Pa]
    rhov : float
        Density of vapor at saturation pressure [mol/:math:`m^3`]
    rhol : float
        Density of liquid at saturation pressure [mol/:math:`m^3`]
    """

    logger = logging.getLogger(__name__)

    if np.count_nonzero(xi) != 1:
        if np.count_nonzero(xi>0.1) != 1:
            raise ValueError("Multiple components have compositions greater than 10%, check code for source")
            logger.error("Multiple components have compositions greater than 10%, check code for source")
        else:
            ind = np.where((xi>0.1)==True)[0]
            raise ValueError("Multiple components have compositions greater than 0. Do you mean to obtain the saturation pressure of {} with a mole fraction of {}?".format(eos._beads[ind],xi[ind]))
            logger.error("Multiple components have compositions greater than 0. Do you mean to obtain the saturation pressure of {} with a mole fraction of {}?".format(eos._beads[ind],xi[ind]))

    vlist, Plist = PvsRho(T, xi, eos, **rhodict)
    Pvspline, roots, extrema = PvsV_spline(vlist, Plist)

    tmp = np.argwhere(np.diff(Plist) > 0)

    if not tmp.any():
        logger.warning('Error: One of the components is above its critical point, add an exception to setPsat')
        Psat = np.nan
        roots = [1.0, 1.0, 1.0]

    else:
        Pmin1 = np.argwhere(np.diff(Plist) > 0)[0][0]
        Pmax1 = np.argmax(Plist[Pmin1:]) + Pmin1

        Pmaxsearch = Plist[Pmax1]

        Pminsearch = max(Plist[-1], np.amin(Plist[Pmin1:Pmax1]))

        #search Pressure that gives equal area in maxwell construction
        Psat = minimize_scalar(eq_area,
                               args=(Plist, vlist),
                               bounds=(Pminsearch * 1.0001, Pmaxsearch * .9999),
                               method='bounded')

        #Using computed Psat find the roots in the maxwell construction to give liquid (first root) and vapor (last root) densities
        Pvspline = interpolate.InterpolatedUnivariateSpline(vlist, Plist - Psat.x)
        roots = Pvspline.roots()
        Psat = Psat.x

    #Psat,rholsat,rhogsat
    return Psat, 1.0 / roots[0], 1.0 / roots[2]

######################################################################
#                                                                    #
#                              Eq Area                               #
#                                                                    #
######################################################################
def eq_area(shift, Pv, vlist):
    r"""
    Objective function used to calculate the saturation pressure.
    
    Parameters
    ----------
    shift : float
        Guess in Psat value used to translate the pressure vs. specific volume curve [Pa]
    Pv : numpy.ndarray
        Pressure associated with specific volume of system with given temperature and composition [Pa]
    vlist : numpy.ndarray
        Specific volume array. Length depends on values in rhodict [:math:`m^3`/mol]

    Returns
    -------
    obj_value : float
        Output of objective function, the addition of the positive area between first two roots, and negative area between second and third roots, quantity squared.
    """

    logger = logging.getLogger(__name__)

    Pvspline = interpolate.InterpolatedUnivariateSpline(vlist, Pv - shift)

    roots = Pvspline.roots()

    a = Pvspline.integral(roots[0], roots[1])
    b = Pvspline.integral(roots[1], roots[2])

    return (a + b)**2

######################################################################
#                                                                    #
#                              Calc Rho V Full                       #
#                                                                    #
######################################################################
def calc_rhov(P, T, xi, eos, rhodict={}):
    r"""
    Computes vapor density under system conditions.
    
    Parameters
    ----------
    P : float
        Pressure of the system [Pa]
    T : float
        Temperature of the system [K]
    xi : numpy.ndarray
        Mole fraction of each component, sum(xi) should equal 1.0
    eos : obj
        An instance of the defined EOS class to be used in thermodynamic computations.
    rhodict : dict, Optional, default: {}
        Dictionary of options used in calculating pressure vs. mole 

    Returns
    -------
    rhov : float
        Density of vapor at system pressure [mol/:math:`m^3`]
    flag : int
        A value of 0 is vapor, 1 is liquid, 2 mean a critical fluid, 3 means that neither is true, 4 means we should assume ideal gas
    """

    logger = logging.getLogger(__name__)

    vlist, Plist = PvsRho(T, xi, eos, **rhodict)
    Plist = Plist-P
    Pvspline, roots, extrema = PvsV_spline(vlist, Plist)

    logger.debug("    Find rhov: P {} Pa, roots {} m^3/mol".format(P,roots))

    l_roots = len(roots)
    if l_roots == 0:
        flag = 3
        rho_tmp = np.nan
        logger.info("    The T and yi, {} {}, won't produce a fluid (vapor or liquid) at this pressure".format(T,xi))
        PvsV_plot(vlist, Plist, Pvspline)
    elif l_roots == 1:
        if not len(extrema):
            flag = 2
            rho_tmp = 1.0 / roots[0]
            logger.info("    The T and yi, {} {}, combination produces a critical fluid at this pressure".format(T,xi))
        elif (Pvspline(roots[0])+P) > (Pvspline(max(extrema))+P):
            #logger.debug("Extrema: {}".format(extrema))
            #logger.debug("Roots: {}".format(roots))
            flag = 1
            rho_tmp = 1.0 / roots[0]
            logger.info("    The T and yi, {} {}, combination produces a liquid at this pressure".format(T,xi))
        elif len(extrema) > 1:
            flag = 0
            rho_tmp = 1.0 / roots[0]
            logger.debug("    This T and yi, {} {}, combination produces a vapor at this pressure. Warning! approaching critical fluid".format(T,xi))
    elif l_roots == 2:
        if (Pvspline(roots[0])+P) < 0.:
            flag = 1
            rho_tmp = 1.0 / roots[0]
            logger.info("    This T and xi, {} {}, combination produces a liquid under tension at this pressure".format(T,xi))
        else:
            flag = 4
            rho_tmp = np.nan
            logger.debug("    There should be a third root! Assume ideal gas P: {}".format(P))
            #PvsV_plot(vlist, Plist, Pvspline)
    else: # 3 roots
        rho_tmp = 1.0 / roots[2]
        flag = 0

    if flag in [0,2]: # vapor or critical fluid
        tmp = [rho_tmp*.99, rho_tmp*1.01]
        if (Pdiff(tmp[0],P, T, xi, eos)*Pdiff(tmp[1],P, T, xi, eos))<0:
            rho_tmp = brentq(Pdiff, tmp[0], tmp[1], args=(P, T, xi, eos), rtol=0.0000001)
        else:
            rho_tmp = root(Pdiff, rho_tmp, args=(P, T, xi, eos), method="hybr", tol=0.0000001)

    # Flag: 0 is vapor, 1 is liquid, 2 mean a critical fluid, 3 means that neither is true, 4 means we should assume ideal gas
    return rho_tmp, flag


######################################################################
#                                                                    #
#                              Calc Rho L Full                       #
#                                                                    #
######################################################################
def calc_rhol(P, T, xi, eos, rhodict={}):
    r"""
    Computes liquid density under system conditions.
    
    Parameters
    ----------
    P : float
        Pressure of the system [Pa]
    T : float
        Temperature of the system [K]
    xi : numpy.ndarray
        Mole fraction of each component, sum(xi) should equal 1.0
    eos : obj
        An instance of the defined EOS class to be used in thermodynamic computations.
    rhodict : dict, Optional, default: {}
        Dictionary of options used in calculating pressure vs. mole 

    Returns
    -------
    rhol : float
        Density of liquid at system pressure [mol/:math:`m^3`]
    flag : int
        A value of 0 is vapor, 1 is liquid, 2 mean a critical fluid, 3 means that neither is true
    """

    logger = logging.getLogger(__name__)

    # Get roots and local minima and maxima 
    vlist, Plist = PvsRho(T, xi, eos, **rhodict)
    Pvspline, roots, extrema = PvsV_spline(vlist, Plist-P)

    logger.debug("    Find rhol: P {} Pa, roots {} m^3/mol".format(P,str(roots)))

    # Assess roots, what is the liquid density
    l_roots = len(roots)
    if l_roots == 0: # zero roots
        flag = 3
        rho_tmp = np.nan
        logger.info("    The T and xi, {} {}, won't produce a fluid (vapor or liquid) at this pressure".format(str(T),str(xi)))
        PvsV_plot(vlist, Plist-P, Pvspline)
    elif l_roots == 2: # 2 roots
        if (Pvspline(roots[0])+P) < 0.:
            flag = 1
            rho_tmp = 1.0 / roots[0]
            logger.info("    This T and xi, {} {}, combination produces a liquid under tension at this pressure".format(T,xi))
        else: # There should be three roots, but the values of specific volume don't go far enough to pick up the last one
            flag = 1
            rho_tmp = 1.0 / roots[0]
    elif l_roots == 1: # 1 root
        if not len(extrema):
            flag = 2
            rho_tmp = 1.0 / roots[0]
            logger.info("    The T and xi, {} {}, combination produces a critical fluid at this pressure".format(T,xi))
        elif (Pvspline(roots[0])+P) > (Pvspline(max(extrema))+P):
            flag = 1
            rho_tmp = 1.0 / roots[0]
            logger.debug("    The T and xi, {} {}, combination produces a liquid at this pressure".format(T,xi))
        elif len(extrema) > 1:
            flag = 0
            rho_tmp = 1.0 / roots[0]
            logger.info("    This T and xi, {} {}, combination produces a vapor at this pressure. Warning! approaching critical fluid".format(T,xi))
    else: # 3 roots
        rho_tmp = 1.0 / roots[0]
        flag = 1

    if flag in [1,2]: # liquid or critical fluid
        tmp = [rho_tmp*.99, rho_tmp*1.01]
        if not (Pdiff(tmp[0],P, T, xi, eos)*Pdiff(tmp[1],P, T, xi, eos))<0:
            logger.info("rhomin, rhomax:",tmp)
            PvsV_plot(vlist, Plist-P, Pvspline)
        rho_tmp = brentq(Pdiff, tmp[0], tmp[1], args=(P, T, xi, eos), rtol=0.0000001)

    # Flag: 0 is vapor, 1 is liquid, 2 mean a critical fluid, 3 means that neither is true
    return rho_tmp, flag

######################################################################
#                                                                    #
#                              Calc Pdiff                            #
#                                                                    #
######################################################################
def Pdiff(rho, Pset, T, xi, eos):
    """
    Calculate difference between set point pressure and computed pressure for a given density
    
    Parameters
    ----------
    rho : float
        Density of system [mol/:math:`m^3`]
    Pset : float
        Guess in pressure of the system [Pa]
    T : float
        Temperature of the system [K]
    xi : numpy.ndarray
        Mole fraction of each component, sum(xi) should equal 1.0
    eos : obj
        An instance of the defined EOS class to be used in thermodynamic computations.
    
    Returns
    -------
    Pdiff : float
        Difference in set pressure and predicted pressure given system conditions.
    """

    logger = logging.getLogger(__name__)

    Pguess = eos.P(rho * const.Nav, T, xi)

    return (Pguess - Pset)

######################################################################
#                                                                    #
#                          Calc phi vapor                            #
#                                                                    #
######################################################################
def calc_phiv(P, T, yi, eos, rhodict={}):
    r"""
    Computes vapor fugacity coefficient under system conditions.
    
    Parameters
    ----------
    P : float
        Pressure of the system [Pa]
    T : float
        Temperature of the system [K]
    yi : numpy.ndarray
        Mole fraction of each component, sum(xi) should equal 1.0
    eos : obj
        An instance of the defined EOS class to be used in thermodynamic computations.
    rhodict : dict, Optional, default: {}
        Dictionary of options used in calculating pressure vs. mole 

    Returns
    -------
    phiv : float
        Fugacity coefficient of vapor at system pressure
    rhov : float
        Density of vapor at system pressure [mol/:math:`m^3`]
    flag : int
        Flag identifying the fluid type. A value of 0 is vapor, 1 is liquid, 2 mean a critical fluid, 3 means that neither is true, 4 means ideal gas is assumed
    """

    logger = logging.getLogger(__name__)

    rhov, flagv = calc_rhov(P, T, yi, eos, rhodict)
    if flagv == 4:
        phiv = np.ones_like(yi)
    else:
        muiv = eos.chemicalpotential(P, np.array([rhov]), yi, T)
        phiv = np.exp(muiv)

    return phiv, rhov, flagv

######################################################################
#                                                                    #
#                         Calc phi liquid                            #
#                                                                    #
######################################################################
def calc_phil(P, T, xi, eos, rhodict={}):
    r"""
    Computes liquid fugacity coefficient under system conditions.
    
    Parameters
    ----------
    P : float
        Pressure of the system [Pa]
    T : float
        Temperature of the system [K]
    xi : numpy.ndarray
        Mole fraction of each component, sum(xi) should equal 1.0
    eos : obj
        An instance of the defined EOS class to be used in thermodynamic computations.
    rhodict : dict, Optional, default: {}
        Dictionary of options used in calculating pressure vs. mole 

    Returns
    -------
    phil : float
        Fugacity coefficient of liquid at system pressure
    rhol : float
        Density of liquid at system pressure [mol/:math:`m^3`]
    flag : int
        Flag identifying the fluid type. A value of 0 is vapor, 1 is liquid, 2 mean a critical fluid, 3 means that neither is true.
    """

    logger = logging.getLogger(__name__)

    rhol, flagl = calc_rhol(P, T, xi, eos, rhodict)
    muil = eos.chemicalpotential(P, np.array([rhol]), xi, T)
    phil = np.exp(muil)

    return phil, rhol, flagl

######################################################################
#                                                                    #
#                              Calc P range                          #
#                                                                    #
######################################################################
def calc_Prange_xi(T, xi, yi, eos, rhodict={}, Pmin=1000, zi_opts={}):
    r"""
    Obtain min and max pressure values, where the liquid mole fraction is set and the objective function at each of those values is of opposite sign.
    
    Parameters
    ----------
    T : float
        Temperature of the system [K]
    xi : numpy.ndarray
        Liquid mole fraction of each component, sum(xi) should equal 1.0
    yi : numpy.ndarray
        Vapor mole fraction of each component, sum(xi) should equal 1.0
    eos : obj
        An instance of the defined EOS class to be used in thermodynamic computations.
    rhodict : dict, Optional, default: {}
        Dictionary of options used in calculating pressure vs. mole 
    Pmin : float, Optional, default: 1000.0
        Minimum pressure in pressure range that restricts searched space.
    zi_opts : dict, Optional, default: {}
        Options used to solve the inner loop in the solving algorithm

    Returns
    -------
    Prange : list
        List of min and max pressure range
    """

    logger = logging.getLogger(__name__)

    global yi_global

    # Guess a range from Pmin to the local max of the liquid curve
    vlist, Plist = PvsRho(T, xi, eos, **rhodict)
    Pvspline, roots, extrema = PvsV_spline(vlist, Plist)

    Pmax = max(Pvspline(extrema))
    Parray = [Pmin, Pmax]

    #################### Find Pressure range and Objective Function values

    # Root of min from liquid curve is absolute minimum
    ObjArray = [0, 0]
    yi_range = yi

    ind = 0
    maxiter = 200
    for z in range(maxiter):
        if z == 0:
            # Find Obj Function for Min pressure above
            p = Parray[0]
            phil, rhol, flagl = calc_phil(p, T, xi, eos, rhodict=rhodict)
            yi_range, phiv, flagv = solve_yi_xiT(yi_range, xi, phil, p, T, eos, rhodict=rhodict, **zi_opts)
            ObjArray[0] = (np.sum(xi * phil / phiv) - 1.0)
            logger.info("Minimum pressure: {},  Obj. Func: {}".format(Parray[0],ObjArray[0]))
            
        elif z == 1:
            # Find Obj function for Max Pressure above
            p = Parray[1]
            phil, rhol, flagl = calc_phil(p, T, xi, eos, rhodict=rhodict)
            yi_range, phiv, flagv = solve_yi_xiT(yi_range, xi, phil, p, T, eos, rhodict=rhodict, **zi_opts)
            ObjArray[1] = (np.sum(xi * phil / phiv) - 1.0)
            logger.info("Estimate Maximum pressure: {},  Obj. Func: {}".format(Parray[1],ObjArray[1]))
        else:
            tmp_sum = np.abs(ObjArray[-2] + ObjArray[-1])
            tmp_dif = np.abs(ObjArray[-2] - ObjArray[-1])
            if tmp_dif > tmp_sum:
                logger.info("Got the pressure range!")
                slope = (ObjArray[-1] - ObjArray[-2]) / (Parray[-1] - Parray[-2])
                intercept = ObjArray[-1] - slope * Parray[-1]
                Pguess = -intercept / slope

                #plt.plot(Parray,ObjArray)
                #plt.plot([Pguess,Pguess],[ObjArray[-1],ObjArray[-2]],'k')
                #plt.plot([Parray[0],Parray[-1]],[0,0],'k')
                #plt.ylabel("Obj. Function")
                #plt.xlabel("Pressure / Pa")
                #plt.show()
                break
            elif z == maxiter:
                raise ValueError('A change in sign for the objective function could not be found, inspect progress')
                plt.plot(Parray, ObjArray)
                plt.plot([Parray[0], Parray[-1]], [0, 0], 'k')
                plt.ylabel("Obj. Function")
                plt.xlabel("Pressure / Pa")
                plt.show()
                logger.error('A change in sign for the objective function could not be found')
            else:
                p = 2 * Parray[-1]
                Parray.append(p)
                phil, rhol, flagl = calc_phil(p, T, xi, eos, rhodict=rhodict)
                yi_range, phiv, flagv = solve_yi_xiT(yi_range, xi, phil, p, T, eos, rhodict=rhodict, **zi_opts)
                ObjArray.append(np.sum(xi * phil / phiv) - 1.0)

    Prange = Parray[-2:]
    ObjRange = ObjArray[-2:]
    logger.info("[Pmin, Pmax]: {}, Obj. Values: {}".format(str(Prange),str(ObjRange)))
    logger.info("Initial guess in pressure: {} Pa".format(Pguess))

    yi_global = yi_range

    return Prange, Pguess

######################################################################
#                                                                    #
#                              Calc P range                          #
#                                                                    #
######################################################################
def calc_Prange_yi(T, xi, yi, eos, rhodict={}, Pmin=1000, zi_opts={}):
    r"""
    Obtain min and max pressure values, where the vapor mole fraction is set and the objective function at each of those values is of opposite sign.
    
    Parameters
    ----------
    T : float
        Temperature of the system [K]
    xi : numpy.ndarray
        Liquid mole fraction of each component, sum(xi) should equal 1.0
    yi : numpy.ndarray
        Vapor mole fraction of each component, sum(xi) should equal 1.0
    eos : obj
        An instance of the defined EOS class to be used in thermodynamic computations.
    rhodict : dict, Optional, default: {}
        Dictionary of options used in calculating pressure vs. mole 
    Pmin : float, Optional, default: 1000.0
        Minimum pressure in pressure range that restricts searched space.
    zi_opts : dict, Optional, default: {}
        Options used to solve the inner loop in the solving algorithm

    Returns
    -------
    Prange : list
        List of min and max pressure range
    """

    logger = logging.getLogger(__name__)

    global xi_global

    # Guess a range from Pmin to the local max of the liquid curve
    vlist, Plist = PvsRho(T, yi, eos, **rhodict)
    Pvspline, roots, extrema = PvsV_spline(vlist, Plist)

    # Calculation the highest pressure possbile
    Pmax = max(Pvspline(extrema))
    Parray = [Pmin, Pmax]

    ############################# Test
    pressures = np.linspace(Pmin,Pmax,30)
    pressure2 = np.linspace(pressures[-2],Pmax,20)
    pressures = np.concatenate((pressures,pressure2),axis=0)
    obj_list = []
    for p in pressures:
        phiv, rhov, flagv = calc_phiv(p, T, yi, eos, rhodict=rhodict)
        xi, phil, flagl = solve_xi_yiT(xi, yi, phiv, p, T, eos, rhodict=rhodict, **zi_opts)
        obj_list.append(np.sum(yi * phiv / phil) - 1.0)
    print(pressures)
    print(obj_list)
    plt.plot(pressures,obj_list,".-")
    plt.plot([Pmin,Pmax],[0,0],"k")
    plt.show()

    #################### Find Pressure range and Objective Function values

    ObjArray = [0, 0]
    xi_range = xi

    for j,i in enumerate([0,1,0]):
        p = Parray[i]
        phiv, rhov, flagv = calc_phiv(p, T, yi, eos, rhodict=rhodict)
        xi_range, phil, flagl = solve_xi_yiT(xi_range, yi, phiv, p, T, eos, rhodict=rhodict, **zi_opts)
        ObjArray[i] = (np.sum(yi * phiv / phil) - 1.0)
        if i == 0:
            logger.info("Estimate Minimum pressure: {},  Obj. Func: {}".format(p,ObjArray[i]))
        elif i == 1:
            if ObjArray[i] < 1e-3:
                ObjArray[i] = 0.0
            logger.info("Estimate Maximum pressure: {},  Obj. Func: {}".format(p,ObjArray[i]))
        # Check pressure range
        if j < 2:
            tmp_sum = np.abs(ObjArray[0] + ObjArray[1])
            tmp_dif = np.abs(ObjArray[0] - ObjArray[1])
            if tmp_dif >= tmp_sum:
                logger.info("Got the pressure range!")
                slope = (ObjArray[1] - ObjArray[-2]) / (Parray[1] - Parray[0])
                intercept = ObjArray[1] - slope * Parray[1]
                Pguess = -intercept / slope
                break
            else:
                newPmin = 10
                if Parray[0] != newPmin:
                    Parray[0] = newPmin
                else:
                    raise ValueError("No VLE data may be found given this temperature and vapor composition. If there are no errors in parameter definitions, consider updating the thermo function 'solve_xi_yiT'.")
                    logger.error("No VLE data may be found given this temperature and vapor composition. If there are no errors in parameter definitions, consider updating the thermo function 'solve_xi_yiT'.")
            
    Prange = Parray[-2:]
    ObjRange = ObjArray[-2:]
    logger.info("[Pmin, Pmax]: {}, Obj. Values: {}".format(str(Prange),str(ObjRange)))
    logger.info("Initial guess in pressure: {} Pa".format(Pguess))

    xi_global = xi_range

    return Prange, Pguess


######################################################################
#                                                                    #
#                       Solve Yi for xi and T                        #
#                                                                    #
######################################################################
def solve_yi_xiT(yi, xi, phil, P, T, eos, rhodict={}, maxiter=15, tol=1e-6):
    r"""
    Find vapor mole fraction given pressure, liquid mole fraction, and temperature. Objective function is the sum of the predicted "mole numbers" predicted by the computed fugacity coefficients. Note that by "mole number" we mean that the prediction will only sum to 1 when the correct pressure is chosen in the outer loop. In this inner loop, we seek to find a mole fraction that is converged to reproduce itself in a prediction. If it hasn't, the new "mole numbers" are normalized into mole fractions and used as the next guess.
    In the case that a guess doesn't produce a gas or critical fluid, we use another function to produce a new guess.
    
    Parameters
    ----------
    yi : numpy.ndarray
        Guess in vapor mole fraction of each component, sum(xi) should equal 1.0
    xi : numpy.ndarray
        Liquid mole fraction of each component, sum(xi) should equal 1.0
    phil : float
        Fugacity coefficient of liquid at system pressure
    P : float
        Pressure of the system [Pa]
    T : float
        Temperature of the system [K]
    eos : obj
        An instance of the defined EOS class to be used in thermodynamic computations.
    rhodict : dict, Optional, default: {}
        Dictionary of options used in calculating pressure vs. mole 
    maxiter : int, Optional, default: 15
        Maximum number of iteration for both the outer pressure and inner vapor mole fraction loops
    tol : float, Optional, default: 1e-6
        Tolerance in sum of predicted yi "mole numbers"

    Returns
    -------
    yi : numpy.ndarray
        Vapor mole fraction of each component, sum(xi) should equal 1.0
    phiv : float
        Fugacity coefficient of vapor at system pressure
    flag : int
        Flag identifying the fluid type. A value of 0 is vapor, 1 is liquid, 2 mean a critical fluid, 3 means that neither is true, 4 means ideal gas is assumed
    """

    logger = logging.getLogger(__name__)

    global yi_global

    yi /= np.sum(yi)
    yi_total = np.sum(yi)
    for z in range(maxiter):

        yi /= np.sum(yi)
        logger.info("    yi guess {}".format(yi))

        # Try yi
        phiv, rhov, flagv = calc_phiv(P, T, yi, eos, rhodict=rhodict)
        
        if (any(np.isnan(phiv)) or flagv==1): # If vapor density doesn't exist
            logger.info("    Composition doesn't produce a vapor, let's find one!")
            yinew = find_new_yi(yi_total,P, T, phil, xi, eos, rhodict=rhodict)
            phiv, rhov, flagv = calc_phiv(P, T, yinew, eos, rhodict={})
            if any(np.isnan(yinew)):
                phiv = np.nan
                logger.error("Fugacity coefficient of vapor should not be NaN")

        yinew = xi * phil / phiv
        logger.info("    yi calc {}".format(yinew))
        logger.info("    Old yi_total: {}, New yi_total: {}, Change: {}".format(yi_total,np.sum(yinew),np.sum(yinew)-yi_total)) 

        # Check convergence
        if abs(np.sum(yinew)-yi_total) < tol:
            yi_global = yi
            logger.info("    Found yi")
            break
        else:
            yi = yinew/np.sum(yinew)
            yi_total = np.sum(yinew)

    ## If yi wasn't found in defined number of iterations
    yinew /= np.sum(yinew)

    if z == maxiter - 1:
        logger.warning('    More than {} iterations needed. Error in Smallest Fraction: {} %%'.format(maxiter, (np.abs(yinew[ind_tmp] - yi[ind_tmp]) / yi[ind_tmp])*100))

    ind_tmp = np.where(yi == min(yi))[0]
    logger.info("    Inner Loop Final yi: {}, Final Error on Smallest Fraction: {}".format(yi,np.abs(yinew[ind_tmp] - yi[ind_tmp]) / yi[ind_tmp]*100))

    return yi, phiv, flagv

######################################################################
#                                                                    #
#                       Solve Yi for xi and T                        #
#                                                                    #
######################################################################
def solve_xi_yiT(xi, yi, phiv, P, T, eos, rhodict={}, maxiter=20, tol=1e-6):
    r"""
    Find liquid mole fraction given pressure, vapor mole fraction, and temperature. Objective function is the sum of the predicted "mole numbers" predicted by the computed fugacity coefficients. Note that by "mole number" we mean that the prediction will only sum to 1 when the correct pressure is chosen in the outer loop. In this inner loop, we seek to find a mole fraction that is converged to reproduce itself in a prediction. If it hasn't, the new "mole numbers" are normalized into mole fractions and used as the next guess.
    In the case that a guess doesn't produce a liquid or critical fluid, we use another function to produce a new guess.
    
    Parameters
    ----------
    xi : numpy.ndarray
        Guess in liquid mole fraction of each component, sum(xi) should equal 1.0
    yi : numpy.ndarray
        Vapor mole fraction of each component, sum(xi) should equal 1.0
    phiv : float
        Fugacity coefficient of liquid at system pressure
    P : float
        Pressure of the system [Pa]
    T : float
        Temperature of the system [K]
    eos : obj
        An instance of the defined EOS class to be used in thermodynamic computations.
    rhodict : dict, Optional, default: {}
        Dictionary of options used in calculating pressure vs. mole 
    maxiter : int, Optional, default: 20
        Maximum number of iteration for both the outer pressure and inner vapor mole fraction loops
    tol : float, Optional, default: 1e-6
        Tolerance in sum of predicted xi "mole numbers"

    Returns
    -------
    xi : numpy.ndarray
        Liquid mole fraction of each component, sum(xi) should equal 1.0
    phil : float
        Fugacity coefficient of liquid at system pressure
    flag : int
        Flag identifying the fluid type. A value of 0 is vapor, 1 is liquid, 2 mean a critical fluid, 3 means that neither is true
    """

    logger = logging.getLogger(__name__)

    global xi_global

    xi /= np.sum(xi)
    xi_total = np.sum(xi)
    for z in range(maxiter):

        xi /= np.sum(xi)
        logger.info("    xi guess {}".format(xi))

        # Try xi
        phil, rhol, flagl = calc_phil(P, T, xi, eos, rhodict=rhodict)

        if (any(np.isnan(phil)) or flagl==0): # If liquid density doesn't exist
            raise ValueError("This composition under these system conditions doesn't produce a liquid or critical fluid. This system must be approaching its critical point and has a suitably small pressure. No contingency function has been established.")
            logger.error("This composition under these system conditions doesn't produce a liquid or critical fluid. This system must be approaching its critical point and has a suitably small pressure. No contingency function has been established.")

        xinew = yi * phiv / phil
        logger.info("    xi calc {}".format(xinew))
        logger.info("    Old xi_total: {}, New xi_total: {}, Change: {}".format(xi_total,np.sum(xinew),np.sum(xinew)-xi_total))

        # Check convergence
        if abs(np.sum(xinew)-xi_total) < tol:
            xi_global = xi
            logger.info("    Found xi")
            break
        else:
            xi = xinew/np.sum(xinew)
            xi_total = np.sum(xinew)

    ## If xi wasn't found in defined number of iterations
    xinew /= np.sum(xinew)

    if z == maxiter - 1:
        logger.warning('    More than {} iterations needed. Error in Smallest Fraction: {} %%'.format(maxiter, (np.abs(xinew[ind_tmp] - xi[ind_tmp]) / xi[ind_tmp])*100))

    ind_tmp = np.where(xi == min(xi))[0]
    logger.info("    Inner Loop Final xi: {}, Final Error on Smallest Fraction: {}".format(xi,np.abs(xinew[ind_tmp] - xi[ind_tmp]) / xi[ind_tmp]*100))

    return xi, phil, flagl

######################################################################
#                                                                    #
#                       Find new Yi                                  #
#                                                                    #
######################################################################


def find_new_yi(yi_total,P, T, phil, xi, eos, rhodict={}):
    r"""
    Search vapor mole fraction combinations for a new estimate that produces a vapor density.
    
    Parameters
    ----------
    yi_total : float
        Total "Mole Number" from estimating vapor mole fractions from fugacity coefficients
    P : float
        Pressure of the system [Pa]
    T : float
        Temperature of the system [K]
    phil : float
        Fugacity coefficient of liquid at system pressure
    xi : numpy.ndarray
        Liquid mole fraction of each component, sum(xi) should equal 1.0
    eos : obj
        An instance of the defined EOS class to be used in thermodynamic computations.
    rhodict : dict, Optional, default: {}
        Dictionary of options used in calculating pressure vs. mole 

    Returns
    -------
    yi : numpy.ndarray
        Vapor mole fraction of each component, sum(yi) should equal 1.0
    """

    #    # have three functions, make sum close to zero, mui isn't np.nan, and rho is a vapor
    #    deap.creator.create("FitnessMulti",deap.base.Fitness,weights=(-1.0, -1.0, 0.5))
    #    deap.creator.create("Inividual", list, fitness=deap.creator.FitnessMax)
    #    toolbox = deap.base.Toolbox()
    # # NoteHere, make individuals add up to 1?
    #    toolbox.register("attr_bool", random.randit, 0, 1)
    #    toolbox.register("individual", deap.tools.initRepeat, deap.creator.Individual, toolbox.attr_bool, n=l_yi)
    #    toolbox.register("population", deap.tools.initRepeat, list, toolbox.individual)
    #
    #    def obj_func(individual):
    #        return np.sum(individual)
    #
    #    toolbox.register("evaluate", obj_func)
    #    toolbox.register("mate", tools.cxTwoPoint)
    #    toolbox.register("mutate", tools.mutFlipBit, indpb=0.05)
    #    toolbox.register("select", tools.selTournament, tournsize=3)
    #
    #    population = toolbox.population(n=300)
    #
    #    NGEN=40
    #    for gen in range(NGEN):
    #        offspring = algorithms.varAnd(population, toolbox, cxpb=0.5, mutpb=0.1)
    #        fits = toolbox.map(toolbox.evaluate, offspring)
    #        for fit, ind in zip(fits, offspring):
    #            ind.fitness.values = fit
    #        population = toolbox.select(offspring, k=len(population))
    #    top10 = tools.selBest(population, k=10)

   # # My attempt at using a heuristic approach
   # # Make new random guesses for yi, and test to find a feasible one
   # l_yi = len(xi)
   # Nguess = 10
   # yiguess = eos.chemicalpotential(P, np.array([rhov_tmp]), yi_g_tmp, T)[]
   # rhov_guess = []
   # obj_guess = []
   # for j in range(maxiter):  # iterate until 10 feasible options are found
   #     yi_g_tmp = np.zeros(l_yi)
   #     # Make guesses for yi
   #     yi_g_tmp[0:-1] = np.random.random((1, l_yi - 1))[0]
   #     yi_g_tmp[-1] = 1 - np.sum(yi_g_tmp)
   #     # Test guess
   #     phiv, rhov, flagv = calc_phiv(P, T, yi, eos, rhodict={})
   #     if all(np.isnan(muiv_tmp) == False):

   #         yiguess.append(yi_g_tmp)
   #         rhov_guess.append(rhov_tmp)

   #         phiv = np.exp(muiv_tmp)
   #         obj_tmp = np.sum(xi * phil / phiv) - 1
   #         logger.debug("rhov, muiv, phiv, obj_tmp" % str([rhov_tmp, muiv, phiv, obj_tmp]))

   #         obj_guess.append(np.abs(obj_tmp))

   #     if len(yiguess) == Nguess:
   #         break
   # # Choose the yi value to continue with based on new guesses
   # ind = np.where(obj_guess == min(obj_guess))[0]
   # logger.info("Obj Value: {}, Index: {}".format(obj_guess,ind))
   # yi = yiguess[ind]
   # rhov = rhov_guess[ind]

    logger = logging.getLogger(__name__)

    yi_ext = np.linspace(0,1,20) # Guess for yi
    obj_ext = []
    flag_ext = []
    for yi in yi_ext:
        yi = [yi, 1-yi]

        phiv, rhov, flagv = calc_phiv(P, T, yi, eos, rhodict=rhodict)
        yinew = xi * phil / phiv
        yinew_total_1 = np.sum(yinew)

        obj_ext.append(yinew_total_1 - yi_total)
        flag_ext.append(flagv)
 
    obj_ext = np.array(obj_ext)
    flag_ext = np.array(flag_ext)

    tmp = np.count_nonzero(~np.isnan(obj_ext))
    logger.debug("Number of valid mole fractions: {}".format(tmp))
    if tmp == 0:
        yi_tmp = np.nan
        obj_tmp = np.nan
    else:
        # Remove any NaN
        obj_tmp  =  obj_ext[~np.isnan(obj_ext)]
        yi_tmp   =   yi_ext[~np.isnan(obj_ext)]
        flag_tmp = flag_ext[~np.isnan(obj_ext)]
 
        # Assess vapor values
        ind = [i for i in range(len(flag_tmp)) if flag_tmp[i] not in [1,4]]
        if ind:
            obj_tmp = [obj_tmp[i] for i in ind]
            yi_tmp = [yi_tmp[i] for i in ind]

        ind = np.where(np.abs(obj_tmp)==min(np.abs(obj_tmp)))[0][0]
        obj_tmp = obj_tmp[ind]
        yi_tmp = yi_tmp[ind]


    logger.info("    Found new guess in yi: {}, Obj: {}".format(yi_tmp,obj_tmp))
    yi = yi_tmp
    if type(yi) != list:
        yi = [yi, 1-yi]

    return yi

######################################################################
#                                                                    #
#                              Solve Xi in root finding              #
#                                                                    #
######################################################################
def solve_xi_root(xi0, yi, phiv, P, T, eos, rhodict):
    r"""
    Objective function used to search liquid mole fraction and solve inner loop of dew point calculations.
    
    Parameters
    ----------
    xi : numpy.ndarray
        Guess in liquid mole fraction of each component, sum(xi) should equal 1.0
    yi : numpy.ndarray
        Vapor mole fraction of each component, sum(yi) should equal 1.0
    phiv : float
        Fugacity coefficient of vapor at system pressure
    P : float
        Pressure of the system [Pa]
    T : float
        Temperature of the system [K]
    eos : obj
        An instance of the defined EOS class to be used in thermodynamic computations.
    rhodict : dict, Optional, default: {}
        Dictionary of options used in calculating pressure vs. mole 

    Returns
    -------
    obj_value : list
        List of percent change between guess that is input and the updated version from recalculating with fugacity coefficients.
    """

    logger = logging.getLogger(__name__)

    xi0 /= np.sum(xi0)
    xi = xi0

    phil, rhol, flagl = calc_phil(P, T, xi, eos, rhodict={})
    xinew = yi * phiv / phil
    xinew /= np.sum(xinew)

    logger.info('    xi: {}, xinew: {}, Percent Error: {}'.format(xi,xinew,((xinew - xi)/xi*100)))

    ind_tmp = np.where(xi==min(xi))[0]
    return np.abs(xinew[ind_tmp]-xi[ind_tmp])/xi[ind_tmp]

######################################################################
#                                                                    #
#                       Solve Yi in Root Finding                     #
#                                                                    #
######################################################################

def solve_yi_root(yi0, xi, phil, P, T, eos, rhodict={}):
    r"""
    Objective function used to search vapor mole fraction and solve inner loop of bubble point calculations.
    
    Parameters
    ----------
    yi0 : numpy.ndarray
        Guess in vapor mole fraction of each component, sum(yi) should equal 1.0
    xi : numpy.ndarray
        Liquid mole fraction of each component, sum(xi) should equal 1.0
    phil : float
        Fugacity coefficient of liquid at system pressure
    P : float
        Pressure of the system [Pa]
    T : float
        Temperature of the system [K]
    eos : obj
        An instance of the defined EOS class to be used in thermodynamic computations.
    rhodict : dict, Optional, default: {}
        Dictionary of options used in calculating pressure vs. mole 

    Returns
    -------
    obj_value : list
        List of absolute change between guess that is input and the updated version from recalculating with fugacity coefficients.
    """

    logger = logging.getLogger(__name__)

    yi0 /= np.sum(yi0)
    yi = yi0

    phiv, rhov, flagv = calc_phiv(P, T, yi, eos, rhodict={})
    yinew = xi * phil / phiv
    yinew = yinew / np.sum(yinew)

    logger.info('    yi: {}, yinew: {}, Percent Error: {}'.format(yi,yinew,((yinew - yi)/yi*100)))

    ind_tmp = np.where(yi==min(yi))[0]
    return np.abs(yinew[ind_tmp]-yi[ind_tmp])/yi[ind_tmp]

######################################################################
#                                                                    #
#                              Solve P xT                            #
#                                                                    #
######################################################################
def solve_P_xiT(P, xi, T, eos, rhodict, zi_opts={}):
    r"""
    Objective function used to search pressure values and solve outer loop of P bubble point calculations.
    
    Parameters
    ----------
    P : float
        Guess in pressure of the system [Pa]
    xi : numpy.ndarray
        Liquid mole fraction of each component, sum(xi) should equal 1.0
    T : float
        Temperature of the system [K]
    eos : obj
        An instance of the defined EOS class to be used in thermodynamic computations.
    rhodict : dict, Optional, default: {}
        Dictionary of options used in calculating pressure vs. mole 
    zi_opts : dict, Optional, default: {}
        Options used to solve the inner loop in the solving algorithm
    

    Returns
    -------
    obj_value : float
        :math:`\sum\frac{x_{i}\{phi_l}{\phi_v}-1`
    """

    logger = logging.getLogger(__name__)

    global yi_global

    if P < 0:
        return 10.0

    logger.info("P Guess: {} Pa".format(P))

    #find liquid density
    phil, rhol, flagl = calc_phil(P, T, xi, eos, rhodict={})

    yinew, phiv, flagv = solve_yi_xiT(yi_global, xi, phil, P, T, eos, rhodict=rhodict, **zi_opts)
    yi_global = yi_global / np.sum(yi_global)

    #given final yi recompute
    phiv, rhov, flagv = calc_phiv(P, T, yi_global, eos, rhodict={})

    Pv_test = eos.P(rhov*const.Nav, T, yi_global)
    obj_value = float((np.sum(xi * phil / phiv) - 1.0))
    logger.info('Obj Func: {}, Pset: {}, Pcalc: {}'.format(obj_value, P, Pv_test[0]))

    return obj_value

######################################################################
#                                                                    #
#                              Solve P yT                            #
#                                                                    #
######################################################################
def solve_P_yiT(P, yi, T, eos, rhodict, zi_opts={}):
    r"""
    Objective function used to search pressure values and solve outer loop of P dew point calculations.
    
    Parameters
    ----------
    P : float
        Guess in pressure of the system [Pa]
    yi : numpy.ndarray
        Vapor mole fraction of each component, sum(yi) should equal 1.0
    T : float
        Temperature of the system [K]
    eos : obj
        An instance of the defined EOS class to be used in thermodynamic computations.
    rhodict : dict, Optional, default: {}
        Dictionary of options used in calculating pressure vs. mole 
    zi_opts : dict, Optional, default: {}
        Options used to solve the inner loop in the solving algorithm

    Returns
    -------
    obj_value : list
        :math:`\sum\frac{y_{i}\{phi_v}{\phi_l}-1`
    """

    logger = logging.getLogger(__name__)

    global xi_global

    if P < 0:
        return 10.0

    #find liquid density
    phiv, rhov, flagv = calc_phiv(P, T, yi, eos, rhodict={})

    xi_global, phil, flagl = solve_xi_yiT(xi_global, yi, phiv, P, T, eos, rhodict=rhodict, **zi_opts)
    xi_global = xi_global / np.sum(xi_global)

    #given final yi recompute
    phil, rhol, flagl = calc_phil(P, T, xi_global, eos, rhodict={})

    Pv_test = eos.P(rhov*const.Nav, T, xi_global)
    obj_value = (np.sum(xi_global * phil / phiv) - 1.0)
    logger.info('    Obj Func: {}, Pset: {}, Pcalc: {}'.format(obj_value, P, Pv_test[0]))

    return obj_value

######################################################################
#                                                                    #
#                   Set Psat for Critical Components                 #
#                                                                    #
######################################################################
def setPsat(ind, eos):
    r"""
    Generate dummy value for component saturation pressure if it is above its critical point.
    
    Parameters
    ----------
    ind : int
        Index of bead that is above critical point
    eos : obj
        An instance of the defined EOS class to be used in thermodynamic computations.

    Returns
    -------
    Psat : float
        Dummy value of saturation pressure [Pa]
    NaNbead : str
        Bead name of the component that is above it's critical point
    """

    logger = logging.getLogger(__name__)

    for j in range(np.size(eos._nui[ind])):
        if eos._nui[ind][j] > 0.0 and eos._beads[j] == "CO2":
            Psat = 10377000.0
        elif eos._nui[ind][j] > 0.0 and eos._beads[j] == "N2":
            Psat = 7377000.0
        elif eos._nui[ind][j] > 0.0 and ("CH4" in eos._beads[j]):
            Psat = 6377000.0
        elif eos._nui[ind][j] > 0.0 and ("CH3CH3" in eos._beads[j]):
            Psat = 7377000.0
        elif eos._nui[ind][j] > 0.0:
            #Psat = np.nan
            Psat = 7377000.0
            NaNbead = eos._beads[j]
            logger.warning("Bead, {}, is above its critical point. Psat is assumed to be {}. To add an exception go to thermodynamics.calc.setPsat".format(NaNbead,Psat))

    if "NaNbead" not in list(locals().keys()):
       NaNbead = "No NaNbead"
       logger.info("No beads above their critical point")

    return Psat, NaNbead 

######################################################################
#                                                                    #
#                              Calc yT phase                         #
#                                                                    #
######################################################################
def calc_yT_phase(yi, T, eos, rhodict={}, zi_opts={}, Pguess=-1, meth="broyden1", pressure_opts={}):
    r"""
    Calculate dew point mole fraction and pressure given system vapor mole fraction and temperature.
    
    Parameters
    ----------
    yi : numpy.ndarray
        Vapor mole fraction of each component, sum(yi) should equal 1.0
    T : float
        Temperature of the system [K]
    eos : obj
        An instance of the defined EOS class to be used in thermodynamic computations.
    rhodict : dict, Optional, default: {}
        Dictionary of options used in calculating pressure vs. mole 
    zi_opts : dict, Optional, default: {}
        Options used to solve the inner loop in the solving algorithm
    Pguess : float, Optional, default: -1
        Guess the system pressure at the dew point. A negative value will force an estimation based on the saturation pressure of each component.
    meth : str, Optional, default: "broyden1"
        Choose the method used to solve the dew point calculation
    pressure_opts : dict, Optional, default: {}
        Options used in the given method, "meth", to solve the outer loop in the solving algorithm

    Returns
    -------
    P : float
        Pressure of the system [Pa]
    xi : numpy.ndarray
        Mole fraction of each component, sum(xi) should equal 1.0
    flagl : int
        Flag identifying the fluid type for the liquid mole fractions, expected is liquid, 1. A value of 0 is vapor, 1 is liquid, 2 mean a critical fluid, 3 means that neither is true
    flagv : int
        Flag identifying the fluid type for the vapor mole fractions, expected is vapor or 0. A value of 0 is vapor, 1 is liquid, 2 mean a critical fluid, 3 means that neither is true, 4 means ideal gas is assumed
    """

    logger = logging.getLogger(__name__)

    global xi_global

    # Estimate pure component vapor pressures
    Psat = np.zeros_like(yi)
    for i in range(np.size(yi)):
        yi_tmp = np.zeros_like(yi)
        yi_tmp[i] = 1.0
        Psat[i], rholsat, rhogsat = calc_Psat(T, yi_tmp, eos, rhodict)
        if np.isnan(Psat[i]):
            Psat[i], NaNbead = setPsat(i, eos)
            if np.isnan(Psat[i]):
                raise ValueError("Component, {}, is beyond it's critical point at {} K. Add an exception to setPsat".format(NaNbead,T))
                logger.error("Component, {}, is beyond it's critical point at {} K. Add an exception to setPsat".format(NaNbead,T))

    # Estimate initial pressure
    if Pguess < 0:
        P=1.0/np.sum(yi/Psat)
    else:
        P = Pguess

    # Estimate initial xi
    if ("xi_global" not in globals() or any(np.isnan(xi_global))):
        xi_global = P * (yi / Psat)
        xi_global /= np.sum(xi_global)
        xi_global = copy.deepcopy(xi_global)
    xi = xi_global 

    #Prange, Pguess = calc_Prange_yi(T, xi, yi, eos, rhodict, zi_opts=zi_opts)
    #logger.info("Given Pguess: {}, Suggested: {}".format(P, Pguess))
    #P = Pguess

    #################### Root Finding without Boundaries ###################
    if meth in ['broyden1', 'broyden2']:
        outer_dict = {'fatol': 1e-5, 'maxiter': 25, 'jac_options': {'reduction_method': 'simple'}}
        for key, value in pressure_opts.items():
            outer_dict[key] = value
        logger.debug("Using the method, {}, with the following options:\n{}".format(meth,outer_dict))
        Pfinal = root(solve_P_yiT, P, args=(yi, T, eos, rhodict, zi_opts), method=meth, options=outer_dict)
    elif meth in ['hybr_broyden1', 'hybr_broyden2']:
        outer_dict = {'fatol': 1e-5, 'maxiter': 25, 'jac_options': {'reduction_method': 'simple'}}
        for key, value in pressure_opts.items():
            outer_dict[key] = value
        Pfinal = root(solve_P_yiT, P, args=(yi, T, eos, rhodict, zi_opts), method="hybr")
        Pfinal = root(solve_P_yiT, Pfinal.x, args=(yi, T, eos, rhodict, zi_opts), method=meth, options=outer_dict)
    elif meth == 'anderson':
        outer_dict = {'fatol': 1e-5, 'maxiter': 25}
        for key, value in pressure_opts.items():
            outer_dict[key] = value
        logger.debug("Using the method, {}, with the following options:\n{}".format(meth,outer_dict))
        Pfinal = root(solve_P_yiT, P, args=(yi, T, eos, rhodict, zi_opts), method=meth, options=outer_dict)
    elif meth in ['hybr', 'lm', 'linearmixing', 'diagbroyden', 'excitingmixing', 'krylov', 'df-sane']:
        outer_dict = {}
        for key, value in pressure_opts.items():
            outer_dict[key] = value
        logger.debug("Using the method, {}, with the following options:\n{}".format(meth,outer_dict))
        Pfinal = root(solve_P_yiT, P, args=(yi, T, eos, rhodict, zi_opts), method=meth, options=outer_dict)

#################### Minimization Methods with Boundaries ###################
    elif meth in ["TNC", "L-BFGS-B", "SLSQP"]:
        outer_dict = {}
        for key, value in pressure_opts.items():
            outer_dict[key] = value
        logger.debug("Using the method, {}, with the following options:\n{}".format(meth,outer_dict))
        if len(Prange) == 2:
            Pfinal = minimize(solve_P_yiT, P, args=(yi, T, eos, rhodict, zi_opts), method=meth, bounds=[tuple(Prange)], options=outer_dict)
        else:
            Pfinal = minimize(solve_P_yiT, P, args=(yi, T, eos, rhodict, zi_opts), method=meth, options=outer_dict)

#################### Root Finding with Boundaries ###################
    elif meth == "brent":
        outer_dict = {"rtol":1e-7}
        for key, value in pressure_opts.items():
            if key in ["xtol","rtol","maxiter","full_output","disp"]:
                outer_dict[key] = value
        logger.debug("Using the method, {}, with the following options:\n{}".format(meth,outer_dict))
        P = brentq(solve_P_yiT, Prange[0], Prange[1], args=(yi, T, eos, rhodict, zi_opts), **outer_dict)

    #Given final P estimate
    if meth != "brent":
        P = Pfinal.x

    #find vapor density and fugacity
    phiv, rhov, flagv = calc_phiv(P, T, yi, eos, rhodict={})
    if "tol" in zi_opts:
        if zi_opts["tol"] > 1e-10:
            zi_opts["tol"] = 1e-10

    xi, phil, flagl = solve_xi_yiT(xi_global, yi, phiv, P, T, eos, rhodict, **zi_opts)
    xi_global = xi
    obj = solve_P_yiT(P, yi, T, eos, rhodict=rhodict)

    return P, xi, flagl, flagv, obj

######################################################################
#                                                                    #
#                              Calc xT phase                         #
#                                                                    #
######################################################################
def calc_xT_phase(xi, T, eos, rhodict={}, zi_opts={}, Pguess=-1, meth="broyden1", pressure_opts={}):
    r"""
    Calculate bubble point mole fraction and pressure given system liquid mole fraction and temperature.
    
    Parameters
    ----------
    xi : numpy.ndarray
        Liquid mole fraction of each component, sum(xi) should equal 1.0
    T : float
        Temperature of the system [K]
    eos : obj
        An instance of the defined EOS class to be used in thermodynamic computations.
    rhodict : dict, Optional, default: {}
        Dictionary of options used in calculating pressure vs. mole 
    zi_opts : dict, Optional, default: {}
        Options used to solve the inner loop in the solving algorithm
    Pguess : float, Optional, default: -1
        Guess the system pressure at the dew point. A negative value will force an estimation based on the saturation pressure of each component.
    meth : str, Optional, default: "broyden1"
        Choose the method used to solve the dew point calculation
    pressure_opts : dict, Optional, default: {}
        Options used in the given method, "meth", to solve the outer loop in the solving algorithm

    Returns
    -------
    P : float
        Pressure of the system [Pa]
    yi : numpy.ndarray
        Mole fraction of each component, sum(yi) should equal 1.0
    flagv : int
        Flag identifying the fluid type for the vapor mole fractions, expected is vapor or 0. A value of 0 is vapor, 1 is liquid, 2 mean a critical fluid, 3 means that neither is true, 4 means ideal gas is assumed
    flagl : int
        Flag identifying the fluid type for the liquid mole fractions, expected is liquid, 1. A value of 0 is vapor, 1 is liquid, 2 mean a critical fluid, 3 means that neither is true
    """

    logger = logging.getLogger(__name__)

    global yi_global

    Psat = np.zeros_like(xi)
    for i in range(np.size(xi)):
        xi_tmp = np.zeros_like(xi)
        xi_tmp[i] = 1.0
        Psat[i], rholsat, rhogsat = calc_Psat(T, xi_tmp, eos, rhodict)
        if np.isnan(Psat[i]):
            Psat[i], NaNbead = setPsat(i, eos)
            if np.isnan(Psat[i]):
                logger.error("Component, {}, is beyond it's critical point. Add an exception to setPsat".format(NaNbead))

    # Estimate initial pressure
    if Pguess < 0:
        P=1.0/np.sum(xi/Psat)
    else:
        P = Pguess

    if ("yi_global" not in globals() or any(np.isnan(yi_global))):
        logger.info("Guess yi in calc_xT_phase with Psat")
        yi_global = xi * Psat / P
        yi_global /= np.sum(yi_global)
        yi_global = copy.deepcopy(yi_global)
    yi = yi_global

#    logger.info("Initial: P: {}, yi: {}".format(Pguess,str(yi)))
#    Pguess, yi = bubblepoint_guess(Pguess, yi, xi, T, phil, eos, rhodict)
#    logger.info("Updated: P: {}, yi: {}".format(Pguess,str(yi)))

    Prange, Pguess = calc_Prange_xi(T, xi, yi, eos, rhodict, zi_opts=zi_opts)
    logger.info("Given Pguess: {}, Suggested: {}".format(P, Pguess))
    P = Pguess

    #################### Root Finding without Boundaries ###################
    if meth in ['broyden1', 'broyden2']:
        outer_dict = {'fatol': 1e-5, 'maxiter': 25, 'jac_options': {'reduction_method': 'simple'}}
        for key, value in pressure_opts.items():
            outer_dict[key] = value
        logger.debug("Using the method, {}, with the following options:\n{}".format(meth,outer_dict))
        Pfinal = root(solve_P_xiT, P, args=(xi, T, eos, rhodict, zi_opts), method=meth, options=outer_dict)
    elif meth in ['hybr_broyden1', 'hybr_broyden2']:
        outer_dict = {'fatol': 1e-5, 'maxiter': 25, 'jac_options': {'reduction_method': 'simple'}}
        for key, value in pressure_opts.items():
            outer_dict[key] = value
        Pfinal = root(solve_P_xiT, P, args=(xi, T, eos, rhodict, zi_opts), method="hybr")
        Pfinal = root(solve_P_xiT, Pfinal.x, args=(xi, T, eos, rhodict, zi_opts), method=meth, options=outer_dict)
    elif meth == 'anderson':
        outer_dict = {'fatol': 1e-5, 'maxiter': 25}
        for key, value in pressure_opts.items():
            outer_dict[key] = value
        logger.debug("Using the method, {}, with the following options:\n{}".format(meth,outer_dict))
        Pfinal = root(solve_P_xiT, P, args=(xi, T, eos, rhodict, zi_opts), method=meth, options=outer_dict)
    elif meth in ['hybr', 'lm', 'linearmixing', 'diagbroyden', 'excitingmixing', 'krylov', 'df-sane']:
        outer_dict = {}
        for key, value in pressure_opts.items():
            outer_dict[key] = value
        logger.debug("Using the method, {}, with the following options:\n{}".format(meth,outer_dict))
        Pfinal = root(solve_P_xiT, P, args=(xi, T, eos, rhodict, zi_opts), method=meth, options=outer_dict)

#################### Minimization Methods with Boundaries ###################
    elif meth in ["TNC", "L-BFGS-B", "SLSQP"]:
        outer_dict = {}
        for key, value in pressure_opts.items():
            outer_dict[key] = value
        logger.debug("Using the method, {}, with the following options:\n{}".format(meth,outer_dict))
        if len(Prange) == 2:
            Pfinal = minimize(solve_P_xiT, P, args=(xi, T, eos, rhodict, zi_opts), method=meth, bounds=[tuple(Prange)], options=outer_dict)
        else:
            Pfinal = minimize(solve_P_xiT, P, args=(xi, T, eos, rhodict, zi_opts), method=meth, options=outer_dict)

#################### Root Finding with Boundaries ###################
    elif meth == "brent":
        outer_dict = {"rtol":1e-7}
        for key, value in pressure_opts.items():
            if key in ["xtol","rtol","maxiter","full_output","disp"]:
                outer_dict[key] = value
        logger.debug("Using the method, {}, with the following options:\n{}".format(meth,outer_dict))
        P = brentq(solve_P_xiT, Prange[0], Prange[1], args=(xi, T, eos, rhodict, zi_opts), **outer_dict)

    #Given final P estimate
    if meth != "brent":
        P = Pfinal.x

    #find liquid density and fugacity
    phil, rhol, flagl = calc_phil(P, T, xi, eos, rhodict={})
    if "tol" in zi_opts:
        if zi_opts["tol"] > 1e-10:
            zi_opts["tol"] = 1e-10

    yi, phiv, flagv = solve_yi_xiT(yi_global, xi, phil, P, T, eos, rhodict, **zi_opts)
    yi_global = yi
    obj = solve_P_xiT(P, xi, T, eos, rhodict=rhodict)

    return P, yi_global, flagv, flagl, obj

######################################################################
#                                                                    #
#                              Calc PT phase                         #
#                                                                    #
######################################################################
def calc_PT_phase(xi, T, eos, rhodict={}):
    r"""
    **Not Complete**
    Calculate the PT phase diagram given liquid mole fraction and temperature
    
    Parameters
    ----------
    xi : numpy.ndarray
        Liquid mole fraction of each component, sum(xi) should equal 1.0
    T : float
        Temperature of the system [K]
    eos : obj
        An instance of the defined EOS class to be used in thermodynamic computations.
    rhodict : dict, Optional, default: {}
        Dictionary of options used in calculating pressure vs. mole 

    Returns
    -------
    P : float
        Pressure of the system [Pa]
    yi : numpy.ndarray
        Mole fraction of each component, sum(yi) should equal 1.0
    """

    logger = logging.getLogger(__name__)

    Psat = np.zeros_like(xi)
    for i in range(np.size(xi)):
        xi_tmp = np.zeros_like(xi)
        xi_tmp[i] = 1.0
        Psat[i], rholsat, rhogsat = calc_Psat(T, xi_tmp, eos, rhodict)
        if np.isnan(Psat[i]):
            Psat[i], NaNbead = setPsat(i, eos)
            if np.isnan(Psat[i]):
                logger.error("Component, {}, is beyond it's critical point. Add an exception to setPsat".format(NaNbead))

    zi = np.array([0.5, 0.5])

    #estimate ki
    ki = Psat / P

    #estimate beta (not thermodynamic) vapor frac
    beta = (1.0 - np.sum(ki * zi)) / np.prod(ki - 1.0)


######################################################################
#                                                                    #
#                              Calc dadT                             #
#                                                                    #
######################################################################
def calc_dadT(rho, T, xi, eos, rhodict={}):
    r"""
    Calculate the derivative of the Helmholtz energy with respect to temperature, :math:`\frac{dA}{dT}`, give a list of density values and system conditions.
    
    Parameters
    ----------
    rho : numpy.ndarray
        Density array. Length depends on values in rhodict [mol/:math:`m^3`]
    T : float
        Temperature of the system [K]
    xi : numpy.ndarray
        Liquid mole fraction of each component, sum(xi) should equal 1.0
    eos : obj
        An instance of the defined EOS class to be used in thermodynamic computations.
    rhodict : dict, Optional, default: {}
        Dictionary of options used in calculating pressure vs. mole 

    Returns
    -------
    dadT : numpy.ndarray
        Array of derivative values of Helmholtz energy with respect to temperature
    """

    logger = logging.getLogger(__name__)

    step = np.sqrt(np.finfo(float).eps) * T * 1000.0
    nrho = np.size(rho)

    #computer rho+step and rho-step for better a bit better performance
    Ap = calchelmholtz.calc_A(np.array([rho]), xi, T + step, eos)
    Am = calchelmholtz.calc_A(np.array([rho]), xi, T - step, eos)

    return (Ap - Am) / (2.0 * step)
