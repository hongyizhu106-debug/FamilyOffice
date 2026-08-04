import matplotlib.pyplot as plt
import numpy as np
import os

out_dir = r"C:\Users\Admin\.gemini\antigravity\brain\d3f86542-da4b-4443-b4de-22581e2fb728"

# 1. Concave vs Convex (A3)
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8, 3))

x = np.linspace(-2, 2, 100)
# Convex (U-shaped)
ax1.plot(x, x**2, 'b-', lw=2)
ax1.set_title("Convex (U-shape)\n$f''(x) > 0$", fontsize=12)
ax1.axis('off')

# Concave (Dome-shaped)
ax2.plot(x, -x**2, 'r-', lw=2)
ax2.set_title("Concave (Dome-shape)\n$f''(x) < 0$", fontsize=12)
ax2.axis('off')

plt.tight_layout()
plt.savefig(os.path.join(out_dir, "a3_concave_convex.png"), dpi=300, transparent=True)
plt.close(fig)

# 2. Partial Derivatives (A5)
fig = plt.figure(figsize=(6, 2))
eq = r"$\frac{\partial f}{\partial x}$ means: Treat $y$ as a constant, and take derivative of $x$!"
fig.text(0.5, 0.5, eq, fontsize=16, ha='center', va='center')
plt.axis('off')
plt.savefig(os.path.join(out_dir, "a5_partial.png"), bbox_inches='tight', dpi=300, transparent=True)
plt.close(fig)

# 3. Multivariate Optimization (A6)
fig = plt.figure(figsize=(6, 2))
eq = r"Set all partial derivatives to 0: $\quad \frac{\partial f}{\partial x} = 0 \quad$ and $\quad \frac{\partial f}{\partial y} = 0$"
fig.text(0.5, 0.5, eq, fontsize=16, ha='center', va='center')
plt.axis('off')
plt.savefig(os.path.join(out_dir, "a6_optimisation.png"), bbox_inches='tight', dpi=300, transparent=True)
plt.close(fig)
