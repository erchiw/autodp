"""
'mechanism_zoo' module implements popular DP mechanisms with their privacy guarantees

"""
import math
from scipy import special
import numpy as np
from autodp.autodp_core import Mechanism
from autodp import rdp_bank, dp_bank, fdp_bank, utils, cdf_bank,phi_bank
from autodp import transformer_zoo
from scipy.stats import norm
from scipy.optimize import minimize_scalar


# Example of a specific mechanism that inherits the Mechanism class
class GaussianMechanism(Mechanism):
    """
    The example of Gaussian mechanism with different characterizations.
    """
    def __init__(self, sigma, coeff=None, name='Gaussian',
                 RDP_off=False, approxDP_off=False, fdp_off=True,
                 use_basic_RDP_to_approxDP_conversion=False,
                 use_fDP_based_RDP_to_approxDP_conversion=False, phi_off=True):
        """
        sigma: the std of the noise divide by the l2 sensitivity.
        coeff: the number of composition
        RDP_off: if False, then we characterize the mechanism using RDP.
        fdp_off: if False, then we characterize the mechanism using fdp.
        phi_off: if False, then we characterize the mechanism using phi-function.
        """
        Mechanism.__init__(self)

        self.name = name # When composing
        self.params = {'sigma': sigma} # This will be useful for the Calibrator
        # TODO: should a generic unspecified mechanism have a name and a param dictionary?

        self.delta0 = 0

        if not phi_off:
            """
            Apply phi function to analyze Gaussian mechanism.
            the CDF of privacy loss R.V. is computed using an integration (see details in cdf_bank) through Levy Theorem.
            If self.exactPhi = True, the algorithm provides an exact characteristion.
            """
            self.exactPhi = True
            phi = lambda x: phi_bank.phi_gaussian({'sigma': sigma}, x)
            self.phi_p_lower = self.phi_q_lower = self.phi_p_upper = self.phi_q_upper = phi
            cdf = lambda x: cdf_bank.cdf_approx(phi, x)

            self.cdf = (cdf, cdf)
            # self.cdf tracks the cdf of log(p/q) and the cdf of log(q/p).
            self.propagate_updates((cdf, cdf), 'cdf_not_sym', take_log=True)


            """
            Moreover, we know the closed-form expression of the CDF of the privacy loss RV
               privacy loss RV distribution l=log(p/q) ~ N(1/2\sigma^2, 1/sigma^2)
            We can also use the following closed-form cdf directly.
            """
            #sigma = sigma*1.0/np.sqrt(coeff)
            #mean = 1.0 / (2.0 * sigma ** 2)
            #std = 1.0 / (sigma)
            #cdf = lambda x: norm.cdf((x - mean) / std)
            #self.propagate_updates(cdf, 'cdf', take_log=True)


        if not RDP_off:
            new_rdp = lambda x: rdp_bank.RDP_gaussian({'sigma': sigma}, x)
            if use_fDP_based_RDP_to_approxDP_conversion:
                # This setting is slightly more complex, which involves converting RDP to fDP,
                # then to eps-delta-DP via the duality
                self.propagate_updates(new_rdp, 'RDP', fDP_based_conversion=True)
            elif use_basic_RDP_to_approxDP_conversion:
                self.propagate_updates(new_rdp, 'RDP', BBGHS_conversion=False)
            else:
                # This is the default setting with fast computation of RDP to approx-DP
                self.propagate_updates(new_rdp, 'RDP')

        if not approxDP_off: # Direct implementation of approxDP
            new_approxdp = lambda x: dp_bank.get_eps_ana_gaussian(sigma, x)
            self.propagate_updates(new_approxdp,'approxDP_func')

        if not fdp_off: # Direct implementation of fDP
            fun1 = lambda x: fdp_bank.log_one_minus_fdp_gaussian({'sigma': sigma}, x)
            fun2 = lambda x: fdp_bank.log_neg_fdp_grad_gaussian({'sigma': sigma}, x)
            self.propagate_updates([fun1,fun2],'fDP_and_grad_log')
            # overwrite the fdp computation with the direct computation
            self.fdp = lambda x: fdp_bank.fDP_gaussian({'sigma': sigma}, x)

        # the fDP of gaussian mechanism is equivalent to analytical calibration of approxdp,
        # so it should have been automatically handled numerically above


        # Discussion:  Sometimes delta as a function of eps has a closed-form solution
        # while eps as a function of delta does not
        # Shall we represent delta as a function of eps instead?


class ExactGaussianMechanism(Mechanism):
    """
    The Gaussian mechanism to use in practice with tight direct computation of everything
    """
    def __init__(self, sigma=None, name='Gaussian'):
        # the sigma parameter is the std of the noise divide by the l2 sensitivity
        Mechanism.__init__(self)

        self.name = name # When composing
        self.params = {'sigma': sigma} # This will be useful for the Calibrator
        self.delta0 = 0
        if sigma is not None:
            new_rdp = lambda x: rdp_bank.RDP_gaussian({'sigma': sigma}, x)
            self.propagate_updates(new_rdp, 'RDP')
            # Overwrite the approxDP and fDP with their direct computation
            self.approxDP = lambda x: dp_bank.get_eps_ana_gaussian(sigma, x)
            self.fDP = lambda x: fdp_bank.fDP_gaussian({'sigma': sigma}, x)


class LaplaceMechanism(Mechanism):
    """
    The Laplace Mechanism that support RDP and phi-function based characterization.
    """
    def __init__(self, b=None, name='Laplace', RDP_off=False, phi_off=True):
        """
        b: the ratio of the scale parameter and L1 sensitivity.
        RDP_off: if False, then we characterize the mechanism using RDP.
        fdp_off: if False, then we characterize the mechanism using fdp.
        phi_off: if False, then we characterize the mechanism using phi-function.
        """
        Mechanism.__init__(self)

        self.name = name
        self.params = {'b': b} # This will be useful for the Calibrator

        self.delta0 = 0
        if not phi_off:

            phi = lambda x: phi_bank.phi_laplace(self.params, x)
            cdf = lambda x: cdf_bank.cdf_approx(phi, x)
            self.exactPhi = True
            self.phi_p_lower = self.phi_q_lower = self.phi_p_upper = self.phi_q_upper = phi
            self.cdf = cdf
            self.propagate_updates(cdf, 'cdf', take_log=True)

        if not RDP_off:
            new_rdp = lambda x: rdp_bank.RDP_laplace({'b': b}, x)
            self.propagate_updates(new_rdp, 'RDP')



class RandresponseMechanism(Mechanism):

    """
    The randomized response mechanism that supports RDP and phi-function based characterization.
    TODO: assert when p is None.
    """
    def __init__(self, p=None, RDP_off=False, phi_off=True, name='Randresponse'):
        """
        p: the Bernoulli probability p of outputting the truth.
        """
        Mechanism.__init__(self)

        self.name = name
        self.params = {'p': p}  # This will be useful for the Calibrator
        self.delta0 = 0

        if not RDP_off:
            new_rdp = lambda x: rdp_bank.RDP_randresponse({'p': p}, x)
            self.propagate_updates(new_rdp, 'RDP')

        if not phi_off:
            phi = lambda x: phi_bank.phi_rr({'p': p}, x)
            cdf = lambda x: cdf_bank.cdf_approx(phi, x)
            self.exactPhi = True
            self.phi_p_lower = self.phi_q_lower = self.phi_p_upper = self.phi_q_upper = phi
            self.cdf = cdf
            self.propagate_updates(cdf, 'cdf', take_log=True)

class PureDP_Mechanism(Mechanism):
    def __init__(self, eps, name='PureDP'):
        # the eps parameter is the pure DP parameter of this mechanism
        Mechanism.__init__(self)

        self.name = name # Used for generating new names when composing
        self.params = {'eps': eps} #

        self.propagate_updates(eps, 'pureDP')

        # ------- I verified that the following options give the same results ----
        # def new_rdp(x):
        #     return rdp_bank.RDP_pureDP({'eps': eps}, x)
        #
        # if use_basic_RDP_to_approxDP_conversion:
        #     self.propagate_updates(new_rdp, 'RDP', BBGHS_conversion=False)
        # else:


        #     self.propagate_updates(new_rdp, 'RDP')



class SubsampleGaussianMechanism(Mechanism):
    """
    This one is used as an example for RDP-based calibrator with subsampled Gaussian mechanism.
    In calibration, users need to specify the sampling probability `prob` and the number of composition `coeff'.
    In the general mechanism design (not for calibrator usage), the initialization in mechanism does not take in the coeff parameter.
    """
    def __init__(self,params,name='SubsampleGaussian'):
        Mechanism.__init__(self)
        self.name=name
        self.params={'prob':params['prob'],'sigma':params['sigma'],'coeff':params['coeff']}
        # create such a mechanism as in previously
        subsample = transformer_zoo.AmplificationBySampling()  # by default this is using poisson sampling
        mech = GaussianMechanism(sigma=params['sigma'])

        # Create subsampled Gaussian mechanism
        SubsampledGaussian_mech = subsample(mech, params['prob'], improved_bound_flag=True)

        # Now run this for niter iterations
        compose = transformer_zoo.Composition()
        mech = compose([SubsampledGaussian_mech], [params['coeff']])

        # Now we get it and let's extract the RDP function and assign it to the current mech being constructed
        rdp_total = mech.RenyiDP
        self.propagate_updates(rdp_total, type_of_update='RDP')


class ComposedGaussianMechanism(Mechanism):
    """
    This one is used as an example for calibrator with composed Gaussian mechanism
    """
    def __init__(self,params,name='SubsampleGaussian'):
        Mechanism.__init__(self)
        self.name=name
        self.params={'sigma':params['sigma'],'coeff':params['coeff']}
        # create such a mechanism as in previously

        mech = GaussianMechanism(sigma=params['sigma'])
        # Now run this for coeff iterations
        compose = transformer_zoo.Composition()
        mech = compose([mech], [params['coeff']])

        # Now we get it and let's extract the RDP function and assign it to the current mech being constructed
        rdp_total = mech.RenyiDP
        self.propagate_updates(rdp_total, type_of_update='RDP')



class NoisyScreenMechanism(Mechanism):
    """
    The data-dependent RDP of ``Noisy Screening" (Theorem 7 in Private-kNN (CPVR-20))
    This mechanism is also used in Figure 2(a) in NIPS-20
    """
    def __init__(self,params,name='NoisyScreen'):
        Mechanism.__init__(self)
        self.name=name
        self.params={'logp':params['logp'],'logq':params['logq']}
        # create such a mechanism as in previously

        new_rdp = lambda x: rdp_bank.RDP_noisy_screen({'logp': params['logp'], 'logq': params['logq']}, x)
        self.propagate_updates(new_rdp, 'RDP')


class GaussianSVT_Mechanism(Mechanism):
    """
    Gaussian SVT  proposed by NeurIPS-20
    parameters k and sigma
    k is the maximum length before the algorithm stops
    rdp_c_1 = True indicates we use RDP-based Gaussian-SVT with c=1, else c>1

    """
    def __init__(self,params,name='GaussianSVT', rdp_c_1=True):
        Mechanism.__init__(self)
        self.name=name
        if rdp_c_1 == True:
            self.name = name + 'c_1'
            self.params = {'sigma': params['sigma'], 'k': params['k'], 'margin':params['margin']}
            new_rdp = lambda x: rdp_bank.RDP_gaussian_svt_c1(self.params, x)
        else:
            self.name = name + 'c>1'
            self.params = {'sigma':params['sigma'],'k':params['k'], 'c':params['c']}
            new_rdp = lambda x: rdp_bank.RDP_gaussian_svt_cgreater1(self.params, x)
        self.propagate_updates(new_rdp, 'RDP')

class LaplaceSVT_Mechanism(Mechanism):
    """
    Laplace SVT (c>=1) used in NeurIPS-20
    parameters k and sigma
    k is the maximum length before the algorithm stops
    We provide the RDP implementation and pure-DP implementation
    """
    def __init__(self,params,name='GaussianSVT'):
        Mechanism.__init__(self)
        self.name=name
        self.params={'b':params['b'],'k':params['k'], 'c':params['c']}

        new_rdp = lambda x: rdp_bank.RDP_svt_laplace(self.params, x)
        self.propagate_updates(new_rdp, 'RDP')


class StageWiseMechanism(Mechanism):
    """
    The StageWise generalized SVT is proposed by Zhu et.al., NeurIPS-20
    used for Sparse vector technique with Gaussian Noise

    c is the number of tops (composition)
    k is the maximum limit for each chunk, e.g., the algorithm restarts whenever it encounters a top or reaches k limit.
    """
    def __init__(self, params=None,approxDP_off=False, name='StageWiseMechanism'):
        # the sigma parameter is the std of the noise divide by the l2 sensitivity
        Mechanism.__init__(self)

        self.name = name # When composing
        self.params = {'sigma': params['sigma'], 'k':params['k'], 'c':params['c']}
        self.delta0 = 0

        if not approxDP_off:  # Direct implementation of approxDP
            new_approxdp = lambda x: dp_bank.get_generalized_gaussian(params, x)
            self.propagate_updates(new_approxdp, 'approxDP_func')



# # Example 1: Short implementation of noisy gradient descent mechanism as a composition of GMs
# class NoisyGD_mech(GaussianMechanism):
#     def __init__(self,sigma_list,name='NoisyGD'):
#         GaussianMechanism.__init__(self, sigma=np.sqrt(np.sum(sigma_list)),name=name)
#         self.params = {'sigma_list':sigma_list}
#
# # The user could log sigma_list and then just declare a NoisyGD_mech object.
# mech = NoisyGD_mech(sigma_list)
# mech.get_approxDP(delta=1e-6)
#
#
# # Example 2: Implementing NoisySGD from basic building blocks
# subsample = Transformers.Subsample(prob=0.01)
# mech = Mechanisms.GaussianMechanism(sigma=5.0)
# # Create subsampled Gaussian mechanism
# SubsampledGaussian_mech = subsample(mech)
#
# # Now run this for 100 iterations
# compose = Transformers.Composition()
# NoisySGD_mech = compose(mechanism_list = [SubsampledGaussian_mech],coeffs_list=[100])
#
#
# # Example 3: You could also package this together by defining a NoisySGD mechanism
# class NoisySGD_mech(Mechanism):
#     def __init__(self,prob,sigma,niter,name='NoisySGD'):
#         Mechanism.__init__()
#         self.name=name
#         self.params={'prob':prob,'sigma':sigma,'niter':niter}
#
#         rdp = rdp_bank.subsampled_gaussian({'prob':params['prob'],'sigma':params['sigma']})
#         self.propagate_updates(rdp,type_of_update='RDP')
#
#
# # Example 4: Online decision. Hetereogenous sigma decided online
# # (maybe as a function of computed eps)
# # Alternatively if we want to do it via composition, so we can make online decision about
# # the sigma in the sigma_list
#
# delta = 1e-6
# online_sgd = Mechanisms.SubsampledGaussian_mech(prob=prob,sigma=sigma)
# compose = Transformers.Composition()
# for i in range(niter):
#     eps = online_ngd.get_approxDP(delta)
#     #determine the next prob, sigma
#     prob, sigma = func(eps)
#     mech_cur = Mechanisms.SubsampledGaussian_mech(prob=prob, sigma=sigma)
#     online_ngd = compose([online_ngd, mech_cur])
#
# # The above is quite general and can be viewed as a privacy accountant


class SubSampleGaussian_phi(Mechanism):
    """
    This mechanism supports the phi-function based characterization for both Poisson subsample Gaussian
    mechanism and the Subset Gaussian mechanism.
    For details of phi-function based characterization, see https://arxiv.org/pdf/2106.08567.pdf Algorithm 2
    """
    def __init__(self, sigma, gamma, coeff=1, name='Subsample_Gaussian_phi', lower_bound = False, upper_bound=False):
        """
        sigma: the std of the noise divide by the l2 sensitivity.
        gamma: the sampling probability.
        lower_bound: if the lower_bound is True, the privacy cost (delta(epsilon) or delta(epsilon)) is a valid lower bound
        of the true privacy guarantee besides negligible errors induced by trunction.
        upper_bound: if the upper_bound is True, the privacy cost (delta(epsilon) or delta(epsilon)) is a valid upper bound
        of the true privacy guarantee besides negligible errors induced by trunction.
        """
        Mechanism.__init__(self)

        self.name = name  # When composing
        self.params = {'sigma': sigma,'gamma':gamma}  # This will be useful for the Calibrator
        # TODO: should a generic unspecified mechanism have a name and a param dictionary?

        self.delta0 = 0
        if lower_bound:
            # phi_p denotes the approximated phi-function of the privacy loss R.V. log(p/q).
            # phi_q denotes the approximated phi-function of the privacy loss R.V. log(q/p).
            self.exactPhi = False
            phi_p = lambda x: phi_bank.phi_subsample_gaussian_p(self.params, x,  phi_min = True)
            phi_q = lambda x: phi_bank.phi_subsample_gaussian_q(self.params, x,  phi_min = True)
            self.phi_p_lower = phi_p
            self.phi_q_lower = phi_q
        elif upper_bound:
            self.exactPhi = False
            phi_p = lambda x: phi_bank.phi_subsample_gaussian_p(self.params, x, phi_max=True)
            phi_q = lambda x: phi_bank.phi_subsample_gaussian_q(self.params, x, phi_max=True)
            self.phi_p_upper = phi_p
            self.phi_q_upper = phi_q
        else:
            # The following phi_p and phi_q is for Double quadrature method.
            # Double quadrature method approximates phi-function using Gaussian quadrature directly.
            self.exactPhi = False
            phi_p = lambda x: phi_bank.phi_subsample_gaussian_p(self.params, x)
            phi_q = lambda x: phi_bank.phi_subsample_gaussian_q(self.params, x)
            self.phi_p_lower = self.phi_p_upper = phi_p
            self.phi_q_lower = self.phi_q_lower = phi_q

        # cdf_p approximates the cdf of the privacy loss R.V. log(p/q)
        cdf_p = lambda x: cdf_bank.cdf_approx(phi_p, x)
        cdf_q = lambda x: cdf_bank.cdf_approx(phi_q, x)
        self.cdf = (cdf_p, cdf_q)
        self.propagate_updates((cdf_p,cdf_q), 'cdf_not_sym', take_log=True)







