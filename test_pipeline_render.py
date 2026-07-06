import ezdxf
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
from ezdxf.addons.drawing import Frontend, RenderContext
from ezdxf.addons.drawing.config import Configuration, BackgroundPolicy, ColorPolicy
import matplotlib.pyplot as plt

doc = ezdxf.readfile('i:/ai-2d-checker/storage/uploads/3346a8b4a97294124a69e89b056c7879226b782a25753deedcaea10adf055493.dxf')
layout_to_render = doc.layout('ICADSX Layout')

fig = plt.figure(figsize=(24, 18), dpi=100)
ax = fig.add_axes([0, 0, 1, 1])
ax.set_axis_off()
ax.set_aspect('equal', 'box')

ctx = RenderContext(doc)
ctx.set_current_layout(layout_to_render)
out = MatplotlibBackend(ax)
Frontend(ctx, out).draw_layout(layout_to_render, finalize=True)

xmin, xmax = ax.get_xlim()
ymin, ymax = ax.get_ylim()

print(f"Render Bounds: xmin={xmin}, ymin={ymin}, xmax={xmax}, ymax={ymax}")
