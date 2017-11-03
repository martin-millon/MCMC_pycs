import numpy as np
import pycs
import pycs.regdiff
import copy
import time
import multiprocessing


def mcmc_metropolis(theta, lcs, fit_vector, spline, gaussian_step=[0.05, 0.02], knotstep=None, niter=1000,
                    burntime=100, savefile=None, nlcs=0, recompute_spline=False, para=True, rdm_walk='gaussian', max_core = 16):
    theta_save = []
    chi2_save = []
    chi2_current = compute_chi2(theta, lcs, fit_vector, spline, knotstep=knotstep, nlcs=nlcs,
                                recompute_spline=recompute_spline, max_core = max_core)
    t = time.time()

    for i in range(niter):
        t_now = time.time() - t
        print "time : ", t_now

        if rdm_walk == 'gaussian':
            theta_new = make_random_step_gaussian(theta, gaussian_step)
        elif rdm_walk == 'exp':
            theta_new = make_random_step_exp(theta, gaussian_step)

        if not prior(theta_new):
            continue

        print theta_new
        chi2_new = compute_chi2(theta_new, lcs, fit_vector, spline, knotstep=knotstep, nlcs=nlcs,
                                recompute_spline=recompute_spline, para=para, max_core = max_core)
        ratio = np.exp((-chi2_new + chi2_current) / 2.0);

        if np.random.rand() < ratio:
            theta = copy.deepcopy(theta_new)
            chi2_current = copy.deepcopy(chi2_new)

        if i > burntime:
            theta_save.append(theta)
            chi2_save.append(chi2_current)

        if savefile != None:
            data = np.asarray([theta[0], theta[1], chi2_current])
            data = np.reshape(data, (1, 3))
            np.savetxt(savefile, data, delimiter=',')


    return theta_save, chi2_save


def prior(theta):
    if -4.0 < theta[0] < -1.0 and 0 < theta[1] < 0.5:
        return True
    else:
        return False


def make_random_step_gaussian(theta, sigma_step):
    return theta + sigma_step * np.random.randn(2)


def make_random_step_exp(theta, sigma_step):
    sign = np.random.random()
    print sign
    if sign > 0.5:
        print "step proposed : ", np.asarray(theta) - [theta[0] + sigma_step[0] * np.random.randn(),theta[1] + np.random.exponential(scale=sigma_step[1])]
        return [theta[0] + sigma_step[0] * np.random.randn(), theta[1] + np.random.exponential(scale=sigma_step[1])]
    else:
        print "step proposed : ",np.asarray(theta) - [theta[0] + sigma_step[0] * np.random.randn(), theta[1] - np.random.exponential(scale=sigma_step[1])]
        return [theta[0] + sigma_step[0] * np.random.randn(), theta[1] - np.random.exponential(scale=sigma_step[1])]


def make_mocks(theta, lcs, spline, ncurve=20, verbose=False, knotstep=None, recompute_spline=True, nlcs=0,
               display=False):
    mocklcs = []
    mockrls = []
    stat = []
    zruns = []
    sigmas = []
    nruns = []

    for i in range(ncurve):

        mocklcs.append(pycs.sim.draw.draw([lcs[nlcs]], spline, tweakml=lambda x: pycs.sim.twk.tweakml(x, beta=theta[0],
                                                                                                      sigma=theta[1],
                                                                                                      fmin=1 / 300.0,
                                                                                                      fmax=None,
                                                                                                      psplot=False),
                                          shotnoise="magerrs", keeptweakedml=False))

        if recompute_spline:
            if knotstep == None:
                print "Error : you must give a knotstep to recompute the spline"
            spline_on_mock = pycs.spl.topopt.opt_fine(mocklcs[i], nit=5, knotstep=knotstep, verbose=False)
            mockrls.append(pycs.gen.stat.subtract(mocklcs[i], spline_on_mock))
        else:
            mockrls.append(pycs.gen.stat.subtract(mocklcs[i], spline))

        if recompute_spline and display:
            pycs.gen.lc.display([lcs[nlcs]], [spline_on_mock], showdelays=True)
            pycs.gen.stat.plotresiduals([mockrls[i]])

        stat.append(pycs.gen.stat.mapresistats(mockrls[i]))
        zruns.append(stat[i][nlcs]['zruns'])
        sigmas.append(stat[i][nlcs]['std'])
        nruns.append(stat[i][nlcs]['nruns'])

    if verbose:
        print 'Mean zruns (simu): ', np.mean(zruns), '+/-', np.std(zruns)
        print 'Mean sigmas (simu): ', np.mean(sigmas), '+/-', np.std(sigmas)
        print 'Mean nruns (simu): ', np.mean(nruns), '+/-', np.std(nruns)

    return [np.mean(zruns), np.mean(sigmas)], [np.std(zruns), np.std(sigmas)]


def make_mocks_para(theta, lcs, spline, ncurve=20, verbose=False, knotstep=None, recompute_spline=True, nlcs=0,
                    display=False, max_core = 16):
    stat = []
    zruns = []
    sigmas = []
    nruns = []

    pool = multiprocessing.Pool(processes = max_core)
    job_kwarg = {'knotstep': knotstep, 'recompute_spline': recompute_spline, 'nlcs': nlcs}
    job_args = [(theta, lcs, spline, job_kwarg) for j in range(ncurve)]

    stat_out = pool.map(fct_para_aux, job_args)
    pool.close()
    pool.join()

    for i in range(len(stat_out)):
        zruns.append(stat_out[i][0]['zruns'])
        sigmas.append(stat_out[i][0]['std'])
        nruns.append(stat_out[i][0]['nruns'])

    if verbose:
        print 'Mean zruns (simu): ', np.mean(zruns), '+/-', np.std(zruns)
        print 'Mean sigmas (simu): ', np.mean(sigmas), '+/-', np.std(sigmas)
        print 'Mean nruns (simu): ', np.mean(nruns), '+/-', np.std(nruns)

    return [np.mean(zruns), np.mean(sigmas)], [np.std(zruns), np.std(sigmas)]


def compute_chi2(theta, lcs, fit_vector, spline, nlcs=0, knotstep=40, recompute_spline=False, para=True, max_core = 16):
    chi2 = 0.0
    if para:
        out, error = make_mocks_para(theta, lcs, spline, nlcs=nlcs, recompute_spline=recompute_spline,
                                     knotstep=knotstep, max_core = max_core)
    else:
        out, error = make_mocks(theta, lcs, spline, nlcs=nlcs, recompute_spline=recompute_spline, knotstep=knotstep)

    for i in range(len(out)):
        chi2 += (fit_vector[i] - out[i]) ** 2 / error[i] ** 2
    return chi2


def fct_para(theta, lcs, spline, knotstep=None, recompute_spline=True, nlcs=0):
    mocklcs = pycs.sim.draw.draw([lcs[nlcs]], spline, tweakml=lambda x: pycs.sim.twk.tweakml(x, beta=theta[0],
                                                                                             sigma=theta[1],
                                                                                             fmin=1 / 300.0, fmax=None,
                                                                                             psplot=False),
                                 shotnoise="magerrs", keeptweakedml=False)

    if recompute_spline:
        if knotstep == None:
            print "Error : you must give a knotstep to recompute the spline"
        spline_on_mock = pycs.spl.topopt.opt_fine(mocklcs, nit=5, knotstep=knotstep, verbose=False)
        mockrls = pycs.gen.stat.subtract(mocklcs, spline_on_mock)
    else:
        mockrls = pycs.gen.stat.subtract(mocklcs, spline)

    stat = pycs.gen.stat.mapresistats(mockrls)
    return stat


def fct_para_aux(args):
    kwargs = args[-1]
    args = args[0:-1]
    return fct_para(*args, **kwargs)
