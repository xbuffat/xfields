import time

import numpy as np

from xline.particles import Particles
from xobjects import ContextCpu, ContextCupy, ContextPyopencl
import xtrack as xt

###################
# Choose context #
###################

context = ContextCpu(omp_num_threads=0) # no omp
#context = ContextCpu(omp_num_threads=1) # omp
#context = ContextCpu(omp_num_threads=48) # omp
context = ContextCupy(default_block_size=256)
context = ContextPyopencl('0.0')

print(repr(context))

#################################
# Generate particles and probes #
#################################

n_macroparticles_b1 = int(1e6)
bunch_intensity_b1 = 2.5e11
sigma_x_b1 = 3e-3
sigma_y_b1 = 2e-3
mean_x_b1 = 1.3e-3
mean_y_b1 = -1.2e-3

n_macroparticles_b2 = int(1e6)
bunch_intensity_b2 = 3e11
sigma_x_b2 = 1.7e-3
sigma_y_b2 = 2.1e-3
mean_x_b2 = -1e-3
mean_y_b2 = 1.4e-3

sigma_z = 30e-2
p0c = 25.92e9
mass = Particles.pmass,
theta_probes = 30 * np.pi/180
r_max_probes = 2e-2
z_probes = 1.2*sigma_z
n_probes = 1000

from xfields.test_support.temp_makepart import generate_particles_object
print('Generate particles b1...')
(particles_b1_pyst, r_probes, _, _, _
        ) =  generate_particles_object(
                            n_macroparticles_b1,
                            bunch_intensity_b1,
                            sigma_x_b1,
                            sigma_y_b1,
                            sigma_z,
                            p0c,
                            mass,
                            n_probes,
                            r_max_probes,
                            z_probes,
                            theta_probes)
part_dict_b1 = xt.pyparticles_to_xtrack_dict(particles_b1_pyst)
particles_b1 = xt.Particles(_context=context, **part_dict_b1)

particles_b1.x += mean_x_b1
particles_b1.y += mean_y_b1

print('Generate particles b2...')
(particles_b2_pyst, r_probes, _, _, _
        ) =  generate_particles_object(
                            n_macroparticles_b2,
                            bunch_intensity_b2,
                            sigma_x_b2,
                            sigma_y_b2,
                            sigma_z,
                            p0c,
                            mass,
                            n_probes,
                            r_max_probes,
                            z_probes,
                            theta_probes)
part_dict_b2 = xt.pyparticles_to_xtrack_dict(particles_b2_pyst)
particles_b2 = xt.Particles(_context=context, **part_dict_b2)

particles_b2.x += mean_x_b2
particles_b2.y += mean_y_b2

#############
# Beam-beam #
#############

from xfields import BeamBeamBiGaussian2D, mean_and_std
print('build bb elements...')
bbeam_b1 = BeamBeamBiGaussian2D(
            _context=context,
            n_particles=bunch_intensity_b2,
            q0 = particles_b2.q0,
            beta0=particles_b2_pyst.beta0,
            sigma_x=None, # needs to be specified only for weak-strong
            sigma_y=None, # needs to be specified only for weak-strong
            mean_x=None, # needs to be specified only for weak-strong
            mean_y=None, # needs to be specified only for weak-strong
            min_sigma_diff=1e-10)

bbeam_b2 = BeamBeamBiGaussian2D(
            _context=context,
            n_particles=bunch_intensity_b1,
            q0 = particles_b1.q0,
            beta0=particles_b1_pyst.beta0,
            sigma_x=None, # needs to be specified only for weak-strong
            sigma_y=None, # needs to be specified only for weak-strong
            mean_x=None, # needs to be specified only for weak-strong
            mean_y=None, # needs to be specified only for weak-strong
            min_sigma_diff=1e-10)

# Measure beam properties
mean_x_meas, sigma_x_meas = mean_and_std(particles_b2.x)
mean_y_meas, sigma_y_meas = mean_and_std(particles_b2.y)
# Update bb lens
bbeam_b1.update(sigma_x=sigma_x_meas, mean_x=mean_x_meas,
                sigma_y=sigma_y_meas, mean_y=mean_y_meas)
#Track
print('Track...')
bbeam_b1.track(particles_b1)

#########################
# Compare against xline #
#########################

print('Check against xline...')
p2np = context.nparray_from_context_array
x_probes = p2np(particles_b1.x[:n_probes])
y_probes = p2np(particles_b1.y[:n_probes])
z_probes = p2np(particles_b1.zeta[:n_probes])

from xline.elements import BeamBeam4D
bb_b1_pyst= BeamBeam4D(
        charge = bunch_intensity_b2,
        sigma_x=sigma_x_b2,
        sigma_y=sigma_y_b2,
        x_bb=mean_x_b2,
        y_bb=mean_y_b2,
        beta_r=np.float64(particles_b2_pyst.beta0))

p_pyst = Particles(p0c=p0c,
        mass=mass,
        x=x_probes.copy(),
        y=y_probes.copy(),
        zeta=z_probes.copy())

bb_b1_pyst.track(p_pyst)

assert np.allclose(p_pyst.px,
    p2np(particles_b1.px[:n_probes]),
    atol=2e-2*np.max(np.abs(p_pyst.px)))
assert np.allclose(p_pyst.py,
    p2np(particles_b1.py[:n_probes]),
    atol=2e-2*np.max(np.abs(p_pyst.px)))

import matplotlib.pyplot as plt
plt.close('all')
plt.figure()
plt.subplot(211)
plt.plot(r_probes, p_pyst.px, color='red')
plt.plot(r_probes, p2np(particles_b1.px[:n_probes]), color='blue',
        linestyle='--')
plt.subplot(212)
plt.plot(r_probes, p_pyst.py, color='red')
plt.plot(r_probes, p2np(particles_b1.py[:n_probes]), color='blue',
        linestyle='--')

###########
# Time it #
###########
print('Time')
n_rep = 5

for _ in range(n_rep):
    t1 = time.time()
    bbeam_b1.track(particles_b1)
    context.synchronize()
    t2 = time.time()
    print(f'Time: {(t2-t1)*1e3:.2f} ms')
plt.show()
