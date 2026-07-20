import matplotlib.pyplot as plt
import numpy as np

# Create mock data
def lam(t, t_c, t_f, t_F2, k_c, k_f, lam_c, lam_F):
    lams = np.zeros(t.shape)
    mask = t <= t_c
    lams[mask] = lam_c
    mask = (t >= t_c) & (t < t_f)
    lams[mask] = (lam_c - 1)*np.exp(-k_c*(t[mask] - t_c)) + 1
    mask = (t >= t_f) & (t <= t_F2)
    lams[mask] = lam_F
    mask = t > t_F2
    lams[mask] = (lam_F - 1)*np.exp(-k_f*(t[mask] - t_F2)) + 1
    return lams

ts = np.linspace(0, 6000, 6000)

t_f = 1700
t_F2 = 1701
lam_F = 100000
lam_c = 1000
t_c = 0.1

lams1 = lam(ts, t_c, t_f, t_F2, 0.1, 0.1, lam_c, lam_F)
lams2 = lam(ts, t_c, t_f, t_F2, 0.01, 0.01, lam_c, lam_F)
lams3 = lam(ts, t_c, t_f, t_F2, 0.005, 0.005, lam_c, lam_F)

# Initialize the plot
fig, ax = plt.subplots(figsize=(10, 5), layout="tight")

# 1. plot the decay models
ax.semilogy(ts, lams1, color='black', label='k = 0.1')
ax.semilogy(ts, lams2, color='blue', label='k = 0.01', linestyle=':')
ax.semilogy(ts, lams3, color='green', label='k = 0.005', linestyle='--')

# 2. Add vertical lines at t = 0
ax.axvline(x=0, color='gray', linestyle='--')

# 3. Shade the region between the lines
# 'alpha' controls transparency (0 = fully transparent, 1 = solid)
ax.axvspan(t_f, t_F2, color='red', alpha=0.2, label='Flood period')

# Add legend and display
ax.legend()

plt.xlabel('Time (yr)')
plt.ylabel(r'$\lambda(t)$')

plt.ylim([0.97, 1e5 + 1000])

plt.savefig('general_model_plot.png', dpi=300)