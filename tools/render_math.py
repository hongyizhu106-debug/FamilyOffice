import matplotlib.pyplot as plt
import os

formulas = {
    "def": r"$\int f(x) dx = F(x) + C$",
    "power": r"$\int x^n dx = \frac{x^{n+1}}{n+1} + C \quad (n \neq -1)$",
    "power_inv": r"$\int \frac{1}{x} dx = \ln|x| + C$",
    "exp": r"$\int e^x dx = e^x + C$",
    "trig_sin": r"$\int \sin x dx = -\cos x + C$",
    "trig_cos": r"$\int \cos x dx = \sin x + C$",
    "constant": r"$\int k \cdot f(x) dx = k \int f(x) dx$",
    "sum": r"$\int [f(x) \pm g(x)] dx = \int f(x) dx \pm \int g(x) dx$",
    "parts": r"$\int u dv = uv - \int v du$"
}

out_dir = r"C:\Users\Admin\.gemini\antigravity\brain\d3f86542-da4b-4443-b4de-22581e2fb728"

for name, eq in formulas.items():
    fig = plt.figure(figsize=(6, 1.5))
    fig.text(0.5, 0.5, eq, fontsize=30, ha='center', va='center', math_fontfamily='cm')
    plt.axis('off')
    plt.savefig(os.path.join(out_dir, f"{name}.png"), bbox_inches='tight', pad_inches=0.1, dpi=300, transparent=True)
    plt.close(fig)
